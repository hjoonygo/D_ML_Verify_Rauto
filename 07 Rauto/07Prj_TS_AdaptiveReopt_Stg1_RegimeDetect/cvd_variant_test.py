# -*- coding: utf-8 -*-
# [cvd_variant_test.py] CVD 변형 비교 — 현재(롤7h) vs 다른 윈도우 vs 누적/연속CVD vs 정규화.
#   질문: '연속/누적 CVD'로 바꾸면 흡수신호 IC·CPCV가 오르나? 검증 led36_king 무수정 재가중.
#   absorption = -side*z(variant). IC(spearman, vs R) + 평균중립 사이징 CPCV 표준6.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"; LED = os.path.join(STG17, "led36_king.csv")
LEV = 22.0; SLIP = 0.0005; GAIN = 0.40; W_LO = 0.55; W_HI = 1.45


def build_variants():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'volume', 'taker_buy_volume'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.sort_values('timestamp').set_index('timestamp')
    net = 2.0 * df['taker_buy_volume'] - df['volume']     # 분당 순테이커
    V = {}
    V['cvd_7h(현재)'] = net.rolling(420, min_periods=200).sum()
    V['cvd_3h'] = net.rolling(180, min_periods=90).sum()
    V['cvd_14h'] = net.rolling(840, min_periods=400).sum()
    V['cvd_24h'] = net.rolling(1440, min_periods=700).sum()
    cum = net.cumsum()                                    # 누적(연속) CVD = 무한누적
    V['cvd_누적raw'] = cum
    V['cvd_누적-detrend'] = cum - cum.rolling(1440, min_periods=700).mean()   # 24h 추세제거 연속CVD
    V['taker_imb_7h'] = net.rolling(420, min_periods=200).sum() / df['volume'].rolling(420, min_periods=200).sum()
    return pd.DataFrame(V)


def cpcv(R, exp, C=0.0008, ng=6):
    r = (np.asarray(R) + 0.0004 - C) * exp
    g = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv]); rr.append(np.prod(1 + r[idx]) - 1)
    return np.percentile(rr, 25) * 100, min(rr) * 100


def main():
    f = build_variants()
    led = pd.read_csv(LED, parse_dates=['entry_t', 'exit_t'])
    for c in ('entry_t', 'exit_t'): led[c] = pd.to_datetime(led[c], utc=True).dt.tz_convert(None)
    led = led.sort_values('entry_t').reset_index(drop=True)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=420)
    led = pd.merge_asof(led.sort_values('dt'), f.sort_index(), left_on='dt', right_index=True, direction='backward').sort_values('entry_t').reset_index(drop=True)

    print(f"거래 {len(led)} | 비교: absorption=-side*z(variant) IC(vs R) + 평균중립 사이징 CPCV(8bp)")
    print(f"{'CVD 변형':>18} {'IC(흡수)':>9} {'전표본%':>9} {'MDD%':>7} {'CPCV p25':>9} {'최악':>8}")
    # 베이스(가중1)
    base_exp = led['size_pct'].values / 100 * LEV
    bp25, bw = cpcv(led['R'].values, base_exp)
    print(f"{'(off=가중없음)':>18} {'-':>9} {'-':>9} {'-':>7} {bp25:>+8.0f}% {bw:>+7.0f}%")
    for col in f.columns:
        ab = (-led['side'] * led[col]).astype(float)
        ic = ab.corr(led['R'], method='spearman')
        z = np.nan_to_num((ab - ab.mean()) / (ab.std() + 1e-9))
        w = np.clip(1.0 + GAIN * z, W_LO, W_HI); w = w / w.mean()
        # 전표본
        a = PE.PaperAccount(10000.0); ps = []
        for i, (_, r) in enumerate(led.iterrows()):
            R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
            a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']) * w[i], leverage=LEV), ts=None, price=100.0)
            ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
        ps = np.array(ps); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
        ret = (eq[-1] / 10000 - 1) * 100; mdd = ((eq / pk - 1).min()) * 100
        p25, wo = cpcv(led['R'].values, led['size_pct'].values * w / 100 * LEV)
        mark = " ★현재" if '현재' in col else ""
        print(f"{col:>18} {ic:>+9.3f} {ret:>+8.0f}% {mdd:>6.1f}% {p25:>+8.0f}% {wo:>+7.0f}%{mark}")
    print("\n[기준] IC↑(절대값) + CPCV p25/최악↑ 이면 그 변형이 현재(롤7h)보다 우수. 비슷/하락이면 교체 무의미.")


if __name__ == "__main__":
    main()
