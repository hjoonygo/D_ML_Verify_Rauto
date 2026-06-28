# -*- coding: utf-8 -*-
# [portfolio_tradelevel_cpcv.py] (A) 2단계 — 거래레벨 CPCV로 표본 보강.
#   동기: portfolio_cpcv_oos.py 는 '월복리 36표본'(얇음)으로 CPCV. REV 스트림은 거래 515건 = 거래단위로 충분.
#   거래레벨에서 reversion 엣지가 CPCV 표준6(15경로) OOS로 살아남는지 직접 확인(월단위 결과 보강).
#   §15.1 재사용: exit_seq(portfolio_cpcv_oos) + TS엔진 + V.build. 거래 ledger 캐시.
import sys, os, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
import vol_sizing_compare as V
from portfolio_cpcv_oos import exit_seq, DATA, TF

HERE = os.path.dirname(os.path.abspath(__file__))
TS_LED = os.path.join(HERE, "ledger_ts.csv"); REV_LED = os.path.join(HERE, "ledger_rev.csv")


def _p(*a): print(*a, flush=True)


def gen_ledgers():
    if os.path.exists(TS_LED) and os.path.exists(REV_LED):
        _p("[캐시] 거래 ledger 로드")
        return pd.read_csv(TS_LED, parse_dates=["et"]), pd.read_csv(REV_LED, parse_dates=["et"])
    _p("[생성] 거래 ledger 생성 중(1m, 느림)…")
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    doi = pd.to_numeric(d["oi_zscore_24h"], errors="coerce")
    df7h = TS.resample_tf(d[["open", "high", "low", "close"]], TF); sig = TS.compute_signals(df7h)
    tstr = TS.run_strategy(df7h, sig, 0, "none", 0.8, gate_mode="er", gate_er=0.45, split_mode="A", split_n=3, fib=(0.3, 0.5, 0.6))
    atrp = sig["atr"] / df7h["close"].values; er = sig["er"]; oi7 = doi.reindex(df7h.index, method="ffill").values; idx7 = df7h.index
    ts_e = []
    for tr in tstr:
        ei = idx7.get_loc(tr["entry_t"])
        if er[ei] < 0.40: continue
        ts_e.append(dict(et=pd.Timestamp(tr["entry_t"]), et_fill=pd.Timestamp(tr["entry_t"]) + pd.Timedelta(minutes=TF),
            side=int(tr["side"]), entry=float(tr["entry"]), atr_pct=float(atrp[ei]) if atrp[ei] > 0 else 0.02,
            oi_z=float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0))
    TSL_ = exit_seq(d, ts_e)
    d2, S, oi_int = V.build(V.find_data()); oimap = dict(zip(list(S.index), list(oi_int)))
    rev_e = []
    for t, row in S.iterrows():
        if row["side"] == 0: continue
        tn = t.tz_localize(None) if t.tz is not None else t
        rev_e.append(dict(et=tn, et_fill=tn, side=int(row["side"]), entry=float(row["open8"]),
            atr_pct=float(row["atr_pct"]), oi_z=float(oimap.get(t, 0.0))))
    REV = exit_seq(d, rev_e)
    TSL_.to_csv(TS_LED, index=False, encoding="utf-8-sig"); REV.to_csv(REV_LED, index=False, encoding="utf-8-sig")
    _p(f"[생성완료] TS {len(TSL_)}거래 / REV {len(REV)}거래")
    return TSL_, REV


def cpcv_trade(r, label):
    """거래레벨 CPCV 표준6: 시간순 6그룹, 2그룹 test×15경로. test Sharpe·평균수익 분포."""
    r = np.asarray(r, dtype=float); n = len(r)
    if n < 30:
        _p(f"  {label:<10} 거래 {n}건 — 거래레벨 CPCV 표본부족(참고만)"); return None
    g6 = np.array_split(np.arange(n), 6); shp = []; mret = []; tots = []
    for c in itertools.combinations(range(6), 2):
        te = np.concatenate([g6[k] for k in c]); rr = r[te]
        shp.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0.0)
        mret.append(rr.mean() * 100); tots.append(((1 + rr).prod() - 1) * 100)
    shp = np.array(shp); mret = np.array(mret); tots = np.array(tots)
    full_sh = r.mean() / r.std() * np.sqrt(n / 3) if r.std() > 0 else 0
    _p(f"  {label:<10} n={n:<4} 승률 {100*(r>0).mean():4.0f}%  full거래Sharpe {full_sh:+.2f}  거래평균 {r.mean()*100:+.3f}%")
    _p(f"  {'':<10} CPCV15경로: Sharpe p25 {np.percentile(shp,25):+.2f}·중앙 {np.median(shp):+.2f}·최악 {shp.min():+.2f}·음수 {100*(shp<0).mean():.0f}%"
       f" | 거래평균 p25 {np.percentile(mret,25):+.3f}%")
    return dict(n=n, full_sh=full_sh, p25_sh=np.percentile(shp, 25), worst_sh=shp.min(), neg=100*(shp < 0).mean())


def yearly(led, label):
    led = led.copy(); led["y"] = pd.to_datetime(led["et"]).dt.year
    _p(f"\n[{label} 연도별 거래] " + "  ".join(
        f"{y}:{len(g)}건 승{100*(g.ret>0).mean():.0f}% 평균{g.ret.mean()*100:+.2f}%" for y, g in led.groupby("y")))


def main():
    TSL_, REV = gen_ledgers()
    _p(f"\n[거래레벨 CPCV 표준6 — reversion 엣지 OOS 직접확인]")
    _p(f"  ※ ret = 사이징(sat×soi) 반영·비용8bp·1m 실체결. (월블렌드 가중 전 원천 거래수익)")
    cpcv_trade(REV["ret"].values, "REV(주력)")
    cpcv_trade(TSL_["ret"].values, "TS(보조)")
    # 풀 결합(동일가중 proxy — 블렌드는 월20/80, 거래레벨은 참고)
    pool = pd.concat([REV[["et", "ret"]], TSL_[["et", "ret"]]]).sort_values("et")
    cpcv_trade(pool["ret"].values, "POOL")
    yearly(REV, "REV"); yearly(TSL_, "TS")
    _p(f"\n[판정] REV 거래레벨 CPCV Sharpe p25>0 AND 음수경로 낮음 = 월단위(p25+18.7%) 보강 = reversion 엣지 거래레벨서도 실재.")
    _p(f"[정직] TS는 34거래로 거래레벨 CPCV 표본부족(월단위·디버시파이어 역할로만 신뢰). POOL은 동일가중 proxy(실제 블렌드는 월20/80).")


if __name__ == "__main__":
    main()
