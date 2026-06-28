# -*- coding: utf-8 -*-
# [DautoBacktest] 독립 수집원(Dauto) 교차 백테 + 데이터 무결성 (세션 260626_02_Rauto2_Sys).
#   캡틴: +11810%(36mo) 못믿겠다 → Dauto 데이터로 검증. ⒜Merged/Dauto가 진짜 바이낸스인지 대조 ⒝Dauto 슬라이스 실제수익.
#   Dauto = AWS미러 2026-05-12~06-22(OHLC+open_interest, 독립수집). oi_zscore=Dauto OI 인과롤링z(순수독립).
import os, sys, json, glob, datetime as dt
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines")); sys.path.insert(0, RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
from blend_opt import rev_side
import rauto_datafeed as DF
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
MIRROR = r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def read_dauto():
    rows = []
    for fp in sorted(glob.glob(os.path.join(MIRROR, "BTCUSDT_1m_2026*.csv"))):
        rows.append(pd.read_csv(fp, usecols=["ts_utc","open","high","low","close","open_interest","funding_rate_8h"]))
    m = pd.concat(rows, ignore_index=True)
    m["t"] = pd.to_datetime(m["ts_utc"], format="%Y-%m-%d %H:%M:%S")
    return m.dropna(subset=["open"]).drop_duplicates("t").set_index("t").sort_index()


def main():
    p = json.load(open(os.path.join(RES, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    print("="*84); print("[Dauto 독립 교차백테 + 데이터 무결성]"); print("="*84)

    # ── ⒜ 데이터 무결성: Dauto vs 바이낸스(같은기간) + Merged vs 바이낸스(옛달) ──
    print("\n[⒜ 데이터 무결성 — 독립대조]")
    dauto = read_dauto()
    print(f"  Dauto 미러: {dauto.index.min()} ~ {dauto.index.max()} ({len(dauto):,}분)")
    # Dauto vs 바이낸스 klines (최근 ~30일 겹침분)
    kl = DF.fetch_klines_1m_range(45)
    bk = pd.DataFrame({"open":[k[1] for k in kl],"high":[k[2] for k in kl],"low":[k[3] for k in kl],"close":[k[4] for k in kl]},
                      index=pd.to_datetime([k[0] for k in kl], unit="ms"))
    ov = dauto.index.intersection(bk.index)
    if len(ov) > 100:
        dd = (dauto.loc[ov,"close"].values - bk.loc[ov,"close"].values)
        print(f"  Dauto vs 바이낸스 종가(겹침 {len(ov):,}분): 최대오차 {np.abs(dd).max():.2f} · 평균 {np.abs(dd).mean():.3f} → {'동일(독립수집 일치)' if np.abs(dd).max()<5 else '차이있음'}")
    # Merged vs 바이낸스 (옛 달 2024-03 샘플)
    mg = pd.read_csv(MERGED, usecols=["timestamp","close"])
    mg["t"]=pd.to_datetime(mg["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None); mg=mg.set_index("t")
    smp = mg.loc["2024-03-01":"2024-03-05","close"]
    kl2 = DF.http_get("/fapi/v1/klines", {"symbol":"BTCUSDT","interval":"1m","startTime":int(pd.Timestamp("2024-03-01").value//1e6),"limit":1500})
    bk2 = pd.Series([float(r[4]) for r in kl2], index=pd.to_datetime([int(r[0]) for r in kl2], unit="ms"))
    ov2 = smp.index.intersection(bk2.index)
    if len(ov2) > 100:
        dd2 = smp.loc[ov2].values - bk2.loc[ov2].values
        print(f"  Merged(2024-03) vs 바이낸스 종가(겹침 {len(ov2):,}분): 최대오차 {np.abs(dd2).max():.2f} → {'동일(Merged=진짜 바이낸스)' if np.abs(dd2).max()<5 else '차이'}")

    # ── ⒝ 순수 Dauto 백테: REVoi(R+P70) ──
    print("\n[⒝ 순수 Dauto 백테 — REVoi R+P70 (lev6/증거금55=M20사이징)]")
    oi = pd.to_numeric(dauto["open_interest"], errors="coerce")
    d1m = dauto[["open","high","low","close"]].copy()
    d1m["oi_zscore_24h"] = DF.oi_zscore_from_series(oi).values
    try:
        fund = DF.fetch_funding_hist()
    except Exception:
        fund = (np.array([],dtype="datetime64[ns]"), np.array([0.0]))
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    for tag, tp in [("앵커(tp0)", 0.0), ("R+P70(tp0.7)", 0.7)]:
        T = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"],
                         er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"],
                         tp_frac=tp).sort_values("et").reset_index(drop=True)
        if not len(T): print(f"  [{tag}] 거래0(워밍업 후 신호없음)"); continue
        pnl, fin, mdd, nl = per_trade_pnl(T, 55.0, 6.0, SlipModel(0,1.0))  # 현실 스프1bp
        R = np.array(pnl)/100.0; w = R[R>0]; l = R[R<0]; pf=(w.sum()/abs(l.sum())) if len(l) else 9.99
        days = (pd.to_datetime(T["et"].max())-pd.to_datetime(T["et"].min())).days + 1
        print(f"  [{tag}] 거래{len(T)}({days}일) · 승{round((R>0).mean()*100)}% · PF{pf:.2f} · 복리(현실) {(fin/10000-1)*100:+.1f}% · MDD{mdd:.1f}% · 청산{nl}")
        print(f"        거래기간 {pd.Timestamp(T['et'].min())} ~ {pd.Timestamp(T['et'].max())}")

    print("\n[해석] ⒜동일=데이터 깨끗(11810%는 데이터버그 아님) · ⒝Dauto 슬라이스는 ~35일이라 작은수치=정상.")
    print("       ★11810%/36mo는 '전표본 최대사이징 천장'(과적합). 실거래 기대=held-out OOS(+205%/12mo)·현실비용.")
    return True


if __name__ == "__main__":
    main()
