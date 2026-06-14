# -*- coding: utf-8 -*-
# [파일명] measure_M2_sweep_reversal.py
# 코드길이: 약 170줄 | 내부버전: M2_sweep_reversal_v1
# [가설 H2] 유동성 스윕→반전: 직전 스윙고/저점을 살짝 뚫었다 도로 닫히면 반대로 반전하는가.
# [정의] 피벗 right=1·left=1(프랙탈). 베어스윕: high[j]>SH & close[j]<SH (불리시 SL 대칭).
#        반전 = i+1..i+H 안에 반대방향 R*ATR_1m 먼저 도달. baseline = 임의봉의 같은 R*ATR 도달.
# [lookahead 차단] 스윙은 직전봉(j-1)을 현재봉(j)으로 '확정'해야 SH/SL 채택(인과적).
#        신호=close[j], 측정=j+1부터. shift(-) 미사용.
# [함수 In/Out]
#   run(df, sample) -> (events_df, baseline_df)
import os, sys, time
import numpy as np
import pandas as pd
import po3_common as pc

HS = [30, 60, 120]
RS = [1.0, 1.5, 2.0]
SAMPLE = 5     # baseline 표본(매 5봉). 스윕 이벤트는 희소하므로 전수 스캔.


def run(df, sample=SAMPLE):
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    atr = pc.atr_1m(df, 14)
    yr = df["year"].to_numpy()
    ts = df["timestamp"]
    smc8 = df["label_smc_8"].to_numpy(object)
    smc5 = df["label_smc_5"].to_numpy(object)
    smc12 = df["label_smc_12"].to_numpy(object)
    fs8 = df["feat_struct_8"].to_numpy(object)
    N = len(df)
    Hmax = max(HS)
    end = N - Hmax - 1

    ev = []
    last_SH = last_SL = None
    for j in range(2, end):
        # (1) 직전봉 j-1을 현재봉 j로 스윙 확정 (인과적: high[j]/low[j]까지만 사용)
        if h[j - 1] > h[j - 2] and h[j - 1] > h[j]:
            last_SH = h[j - 1]
        if l[j - 1] < l[j - 2] and l[j - 1] < l[j]:
            last_SL = l[j - 1]
        ai = atr[j]
        if not np.isfinite(ai) or ai <= 0:
            continue
        ci = c[j]
        fl_all = l[j + 1:j + 1 + Hmax]
        fh_all = h[j + 1:j + 1 + Hmax]
        cl_all = c[j + 1:j + 1 + Hmax]
        # (2) 베어 스윕: 위로 뚫었다 도로 닫힘
        bear = last_SH is not None and h[j] > last_SH and ci < last_SH
        bull = last_SL is not None and l[j] < last_SL and ci > last_SL
        for (cond, side, swept) in ((bear, "bear", last_SH), (bull, "bull", last_SL)):
            if not cond:
                continue
            for R in RS:
                for H in HS:
                    fl = fl_all[:H]
                    fh = fh_all[:H]
                    cH = cl_all[H - 1]
                    if side == "bear":          # 반전 = 하락
                        rev = bool((fl <= ci - R * ai).any())
                        fwd = (ci - cH) / ci
                    else:                        # 반전 = 상승
                        rev = bool((fh >= ci + R * ai).any())
                        fwd = (cH - ci) / ci
                    ev.append((ts.iat[j], smc8[j], fs8[j], smc5[j], smc12[j], side, R, H,
                               int(rev), round(fwd, 6), round(fwd - 2 * pc.COST_ONEWAY, 6),
                               round(float(swept), 2), int(yr[j])))

    ev_cols = ["ts", "regime", "regime_feat", "regime_smc5", "regime_smc12",
               "dir", "R", "H", "reversed", "fwd_ret", "fwd_ret_cost", "swept_extreme", "year"]
    ev_df = pd.DataFrame.from_records(ev, columns=ev_cols)

    # (3) baseline — 임의봉(매 sample봉) 동일 R*ATR 도달율 (레짐×방향×R×H 집계)
    agg = {}
    for i in range(2, end, sample):
        ai = atr[i]
        if not np.isfinite(ai) or ai <= 0:
            continue
        ci = c[i]
        fl_all = l[i + 1:i + 1 + Hmax]
        fh_all = h[i + 1:i + 1 + Hmax]
        cl_all = c[i + 1:i + 1 + Hmax]
        g8, gf, y = smc8[i], fs8[i], int(yr[i])
        for R in RS:
            for H in HS:
                fl = fl_all[:H]
                fh = fh_all[:H]
                cH = cl_all[H - 1]
                for side in ("bear", "bull"):
                    if side == "bear":
                        reach = (fl <= ci - R * ai).any()
                        fwd = (ci - cH) / ci
                    else:
                        reach = (fh >= ci + R * ai).any()
                        fwd = (cH - ci) / ci
                    k = (g8, gf, y, side, R, H)
                    a = agg.get(k)
                    if a is None:
                        a = [0, 0, 0.0]
                        agg[k] = a
                    a[0] += 1
                    a[1] += int(bool(reach))
                    a[2] += fwd
    brows = [(k[0], k[1], k[2], k[3], k[4], k[5], n, reach, round(sf, 6))
             for k, (n, reach, sf) in agg.items()]
    bcols = ["regime", "regime_feat", "year", "dir", "R", "H", "n", "reach_n", "sum_fwd"]
    base_df = pd.DataFrame.from_records(brows, columns=bcols)
    return ev_df, base_df


def main():
    t0 = time.time()
    nrows = 60000 if "--quick" in sys.argv else None
    if nrows:
        print("[QUICK] 앞 60,000행 사전실행")
    df = pc.load_1m(nrows=nrows)
    print(f"[M2] 데이터 {len(df):,}행 | {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    ev_df, base_df = run(df)
    od = pc.ensure_out()
    fp1 = os.path.join(od, "measure_M2_sweep_reversal.csv")
    fp2 = os.path.join(od, "measure_M2_baseline.csv")
    ev_df.to_csv(fp1, index=False, encoding="utf-8-sig")
    base_df.to_csv(fp2, index=False, encoding="utf-8-sig")
    nev = len(ev_df) // (len(HS) * len(RS)) if len(ev_df) else 0
    print(f"[M2] 스윕이벤트 {nev:,}건(×R×H={len(ev_df):,}행) | baseline {len(base_df):,}행 | {time.time()-t0:.1f}s")
    if len(ev_df):
        pv = ev_df.groupby(["dir", "R", "H"])["reversed"].mean().round(3)
        print(pv.to_string())


if __name__ == "__main__":
    main()
