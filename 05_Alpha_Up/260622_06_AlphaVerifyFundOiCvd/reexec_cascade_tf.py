# -*- coding: utf-8 -*-
# [reexec_cascade_tf.py] 캡틴 아이디어: 7h→1h→15m→1m 계층(coarse→fine) 캐스케이드로
#   '청산 sl이 보유기간 [entry_t,exit_t]에 실제 거래됐나·어디서'를 빠르게 판정.
#   · 겹치는 coarse봉만 파고듦(효율). coarse는 겹치는데 어느 fine봉에도 sl 없으면=갭(price가 그 안서 점프).
#   · 1m봉에 sl이 들어가면 = 깨끗한 체결(그 시점·sl가에 청산 성립) → exit_px=sl 유지(P&L 정상).
#   · 보유기간 어느 1m에도 sl 없으면 = 진짜 갭 → 실체결 불가, 청산봉서 최선가(관대)로 교정.
#   ★이게 내 직전 '청산봉 일괄 가격'(-100%)보다 정확: sl이 보유중 거래됐으면 그건 정상체결.
#   원본 +11397% 앵커 재현 + 캐스케이드 vs 브루트포스 일치 검증 후 진짜수익 산출.
import os, sys, time
import numpy as np, pandas as pd
STG = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(STG, "bots"), STG):
    if p not in sys.path: sys.path.insert(0, p)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action as A, Side
LED = os.path.join(STG, "led36_king.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 22.0
ANCHOR = pd.Timestamp("2023-05-01 00:00:00", tz="UTC")


def _p(*a): print(*a, flush=True)


def resample_hl(m1, rule, origin):
    g = m1.resample(rule, origin=origin)
    return pd.DataFrame({"high": g["high"].max(), "low": g["low"].min()}).dropna()


def main():
    L = pd.read_csv(LED)
    L["entry_t"] = pd.to_datetime(L["entry_t"], utc=True)
    L["exit_t"] = pd.to_datetime(L["exit_t"], utc=True)
    m1 = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low"])
    m1["t"] = pd.to_datetime(m1["timestamp"], utc=True, format="ISO8601")
    m1 = m1.set_index("t").sort_index()[["open", "high", "low"]]
    # 계층 TF (7h는 봇 그리드 ANCHOR 정렬, 나머지 epoch)
    tf7 = resample_hl(m1, "420min", ANCHOR)
    tf1h = resample_hl(m1, "60min", ANCHOR)
    tf15 = resample_hl(m1, "15min", ANCHOR)
    _p(f"1m {len(m1)} | 7h {len(tf7)} | 1h {len(tf1h)} | 15m {len(tf15)}")

    def overlaps(df, t0, t1, sl):
        w = df.loc[t0:t1]
        return w[(w["low"] <= sl) & (w["high"] >= sl)]

    def cascade(sl, t0, t1):
        """캡틴 캐스케이드: 7h겹침→1h→15m→1m. 1m서 겹치는 첫 시각 반환, 없으면 None(갭)."""
        for b7s in overlaps(tf7, t0, t1, sl).index:
            b7e = min(t1, b7s + pd.Timedelta(minutes=420) - pd.Timedelta(minutes=1))
            for b1s in overlaps(tf1h, max(t0, b7s), b7e, sl).index:
                b1e = min(b7e, b1s + pd.Timedelta(minutes=60) - pd.Timedelta(minutes=1))
                for b15s in overlaps(tf15, max(t0, b1s), b1e, sl).index:
                    b15e = min(b1e, b15s + pd.Timedelta(minutes=15) - pd.Timedelta(minutes=1))
                    hit = overlaps(m1, max(t0, b15s), b15e, sl)
                    if len(hit): return hit.index[0]
        return None

    def brute(sl, t0, t1):
        h = overlaps(m1, t0, t1, sl)
        return h.index[0] if len(h) else None

    # 검증: 캐스케이드 == 브루트포스 (앞 60거래)
    t0 = time.time(); mism = 0
    for _, r in L.head(60).iterrows():
        if r.reason != "sl_intrabar": continue
        c = cascade(r.exit_px, r.entry_t, r.exit_t); b = brute(r.exit_px, r.entry_t, r.exit_t)
        if (c is None) != (b is None): mism += 1
    _p(f"[검증] 캐스케이드 vs 브루트포스 60거래 불일치(존재여부): {mism} (0이어야 정상)")

    # 전 거래 분류 + 실체결
    clean = gap = 0; rows = []
    for _, r in L.iterrows():
        sl, side, ent = float(r.exit_px), int(r.side), float(r.entry_px)
        reason = r.reason
        real = sl
        if reason == "sl_intrabar":
            hit = cascade(sl, r.entry_t, r.exit_t)
            if hit is not None:
                clean += 1                          # 보유중 sl 실거래=깨끗한 체결
            else:
                gap += 1                            # 진짜 갭=청산봉 최선가(관대)
                eb = m1.loc[r.exit_t] if r.exit_t in m1.index else None
                if eb is not None:
                    real = (min(sl, eb["high"]) if side == 1 else max(sl, eb["low"]))
        R_real = float(r.R) + side * (real - sl) / ent * LEV
        final_r = side * (real - ent) / ent
        rows.append(dict(side=side, R=float(r.R), R_real=R_real, reason=reason,
                         mae=float(r.mae), mae_real=min(float(r.mae), final_r),
                         size_pct=float(r.size_pct), fund=float(r.fund), year=int(r.year)))
    D = pd.DataFrame(rows)
    _p(f"[분류] sl_intrabar {clean+gap}건 → 깨끗한체결(보유중 sl실거래) {clean} / 진짜갭 {gap}  | 소요 {time.time()-t0:.0f}s")

    def runbt(rcol, maecol):
        acct = PE.PaperAccount()
        for _, r in D.iterrows():
            acct.open(Signal(A.ENTER, side=Side(int(r.side)), size_pct=r.size_pct, leverage=LEV), ts=None, price=100.0)
            R = r[rcol] - (0.0005 if r.reason in ("sl", "sl_intrabar") else 0.0)
            acct.resolve_replay(R=R, mae=r[maecol], fund=r.fund)
        return acct.metrics()[:2]

    o_ret, o_mdd = runbt("R", "mae")
    r_ret, r_mdd = runbt("R_real", "mae_real")
    _p("=" * 72)
    _p(f"[원본 앵커]      sl체결:        {o_ret:+.0f}% / MDD {o_mdd:.1f}%")
    _p(f"[캡틴 캐스케이드] 깨끗한건 sl·갭만 교정: {r_ret:+.0f}% / MDD {r_mdd:.1f}%  ← 더 정확")
    _p("=" * 72)
    for y in sorted(D.year.unique()):
        s = D[D.year == y]
        _p(f"  {int(y)}: R합 {s.R.sum():+.2f} → {s.R_real.sum():+.2f} ({len(s)}거래)")
    D.to_csv(os.path.join(HERE, "champion_cascade_reexec.csv"), index=False, encoding="utf-8-sig")
    _p("[정직] 갭만 교정(관대=청산봉 최선가)=여전히 상한. 깨끗한 체결은 sl 인정(보유중 실거래).")


if __name__ == "__main__":
    main()
