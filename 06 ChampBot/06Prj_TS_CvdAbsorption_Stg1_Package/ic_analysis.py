# -*- coding: utf-8 -*-
# [ic_analysis.py] 레버2: IC(정보계수) + 팩터 다중공선성 측정.
#   우리 게이트/사이징 피처가 서로 중복인지(|Spearman|>0.7), 각 피처가 forward 7H수익을
#   실제로 예측하는지(IC)를 측정. 신호엔진(compute_signals) 무수정 사용 — 측정 전용.
#   피처: er, adx, chop, atrcmp, bandw (7H 신호엔진) + atr_ratio·feat_struct(4H) + oi_zscore.
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import regime_feature_extractor as RFE

DATA = r"D:\ML\Verify\Merged_Data.csv"


def main():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    print(f"data {len(df)} rows {df.index[0]}~{df.index[-1]}")

    # ── 7H 결정그리드: 신호엔진 피처 ──
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], E.TF_MIN)
    sig = E.compute_signals(df7)
    F = pd.DataFrame(index=df7.index)
    for k in ('er', 'adx', 'chop', 'atrcmp', 'bandw'):
        F[k] = np.asarray(sig[k], dtype=float)
    F['trend'] = np.asarray(sig['Trend'], dtype=float)

    # ── 4H 피처: atr_ratio, feat_struct_8 → 7H로 asof(확정 직전값) ──
    ohlc = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    d4 = df.resample('4h', label='right', closed='right').agg(ohlc).dropna()
    d4 = RFE.compute_continuous_metrics(d4)
    st = RFE.smc_structure(d4, 8)
    d4 = pd.concat([d4, st], axis=1)
    fmap = {'uptrend': 1.0, 'range': 0.0, 'downtrend': -1.0}
    atr_ratio_4 = d4['atr_ratio'].shift(1)            # 확정 직전 4H봉만(라이브 동일)
    feat_num_4 = d4['feat_struct_8'].map(fmap).shift(1)
    F['atr_ratio'] = atr_ratio_4.reindex(F.index, method='ffill')
    F['feat_struct'] = feat_num_4.reindex(F.index, method='ffill')

    # ── oi_zscore_24h → 7H asof ──
    oiz = df['oi_zscore_24h'].dropna()
    F['oi_zscore'] = oiz.reindex(F.index, method='ffill')

    # ── forward 7H 수익 ──
    fwd = df7['close'].shift(-1) / df7['close'] - 1.0
    F['_fwd'] = fwd.values
    F['_fwd_abs'] = fwd.abs().values

    F = F.dropna()
    print(f"7H bars (warmup 제거 후) {len(F)}\n")

    feats = ['er', 'adx', 'chop', 'atrcmp', 'bandw', 'atr_ratio', 'oi_zscore', 'feat_struct', 'trend']

    # ── (1) 다중공선성: Spearman 상관행렬 ──
    corr = F[feats].corr(method='spearman')
    print("=== (1) 팩터 상호상관 (Spearman) — |ρ|>0.7 = 중복의심 ===")
    print(corr.round(2).to_string())
    print("\n[중복쌍 |ρ|>=0.7]")
    pairs = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            r = corr.iloc[i, j]
            if abs(r) >= 0.7:
                pairs.append((feats[i], feats[j], round(float(r), 3)))
    for a, b, r in sorted(pairs, key=lambda x: -abs(x[2])):
        print(f"   {a:12s} ~ {b:12s} ρ={r:+.3f}  ← 중복")
    if not pairs: print("   (없음 — 모두 |ρ|<0.7, 독립적)")

    # ── (2) IC: forward 수익 예측력 ──
    print("\n=== (2) IC (Spearman, 피처 vs forward 7H수익) ===")
    print(f"{'feature':12s} {'IC(signed)':>12s} {'IC(|ret|=변동성)':>16s}")
    ic_rows = []
    for f in feats:
        ic_s = F[f].corr(F['_fwd'], method='spearman')
        ic_a = F[f].corr(F['_fwd_abs'], method='spearman')
        ic_rows.append((f, ic_s, ic_a))
        print(f"{f:12s} {ic_s:>+12.4f} {ic_a:>+16.4f}")
    print("\n해설: IC(signed)=방향예측, IC(|ret|)=변동성(장세강도)예측. |IC|>0.03이면 약하게 유효(7H 단봉기준).")

    # 저장
    corr.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ic_corr_matrix.csv"), encoding="utf-8-sig")
    pd.DataFrame(ic_rows, columns=['feature', 'ic_signed', 'ic_absret']).to_csv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ic_table.csv"), index=False, encoding="utf-8-sig")
    print("\n저장: ic_corr_matrix.csv, ic_table.csv")


if __name__ == "__main__":
    main()
