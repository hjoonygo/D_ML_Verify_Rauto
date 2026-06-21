# -*- coding: utf-8 -*-
# [FILE] test.py  (PP_ST_Pullback_V1_stg1 - Pivot SuperTrend Pullback, 36mo BTC, TFxR grid)
# CODE LENGTH: approx 360 lines | INTERNAL VER: pp_st_v1 | full output, no omission
#
# [PURPOSE / 목적] TradingView 전략 PP_SuperTrend_Pullback(Pine 114줄)을 Python으로 충실 변환,
#   BTC 36개월 1분봉으로 알파(추세추종 청산엔진) 여부를 확정한다. 컨테이너 스모크 통과본.
#   원본 = LonesomeTheBlue "Pivot Point SuperTrend"(MPL2.0) 진입을 눌림목(HH-HL/LL-LH)으로 교체.
#
# [핵심 로직 - 사용자 승인 완료]
#   진입: 추세방향(PP-ST 밴드) AND 이봉에서 새피벗(롱=새PL/숏=새PH) 확정 AND 반대편 피벗 존재.
#         봉마감 종가 즉시 체결(TF무관). pyramiding=0(보유중 신규진입 무시).
#   청산: TP 없음. ①추세전환 전량청산 ②피보 단조 트레일링 손절 터치.
#   피보 트레일: 보유중 새피벗 확정봉에서만 손절선을 (1차0.3/2차0.5/3차+0.6) 자리로 단조 갱신.
#   미래참조: 피벗은 좌LEFT/우RIGHT 확정(발생봉+RIGHT 이후에만 사용). 진입은 확정 후에만.
#
# [해법A - 사용자 승인] 좌 LEFT=4 고정, 우 RIGHT={1,2,3} 비교 (확정지연 vs 휩소 맞교환).
#
# [GRID - TF x RIGHT x 방향]  (사용자: 7h 메인, 6/8h 인접, 4/12h 대조, 롱숏분해, 학습검증분리)
#   C1 7h  R1 롱숏   C2 6h R1 롱숏   C3 8h R1 롱숏
#   C4 7h  R1 롱만   C5 7h R1 숏만
#   C6 4h  R1 롱숏   C7 12h R1 롱숏
#   C8 7h  R1 롱숏 (train 23~24 / test 25~26 분리)
#   + 7h에서 R2/R3 추가 비교(C9 7h R2, C10 7h R3)
#   각칸: 거래/승률/누적R/PF/파산/최저자본/평균보유봉/청산사유분해 + 펀딩총액.
#
# [비용/사이징 - 사용자 승인] 왕복 8bp(COST=0.0004) + 펀딩 8h이산(FUND_8H=0.0001). 레버 1배.
#   파산판정은 참고표기. 핵심판정=누적R/PF (사이징 착시 회피).
#
# [SPEED] TF 리샘플 1회, 피벗/추세/ATR 벡터·1패스. 거래만 기록.
# [PATH] D:\ML\verify\PP_ST_Pullback_V1_stg1\ 실행, 데이터 상위 D:\ML\verify\, 결과 CSV 이 하위폴더.
# [DATA] ..\Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close 만 사용. regime 불필요)
# [OUTPUT] pp_summary.csv(칸×train/test/all) + pp_trades.csv(C1 7h R1 거래별)
#
# [FUNCTIONS In/Out]
#   find_data()->path ; load_data(path)->df1m(OHLC)
#   resample_tf(df1m,tf_min)->df_tf
#   pivots_lr(high,low,left,right)->(ph_conf,pl_conf)   확정봉->(발생봉,값)
#   compute_atr(h,l,c,Pd)->atr[]
#   pivot_supertrend(df_tf)->(Trend[],center[],atr[])   원본 PP-ST 추세방향
#   run_strategy(df_tf,right,allow_long,allow_short,lev)->trades[]
#   agg(trades,label,years)->dict
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

LEFT = 4
COST = 0.0004        # 왕복 8bp
FUND_8H = 0.0001     # 8h당 0.01% (0.03%/일)
FIB = (0.3, 0.5, 0.6)
SL_PCT = 1.0
ATR_FACTOR = 3.0
ATR_PERIOD = 10
LEVERAGE = 1.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]

# (라벨, TF분, RIGHT, 롱허용, 숏허용, 비고)
CELLS = [
    ('C1_7h_R1_LS', 7 * 60, 1, True, True, 'main'),
    ('C2_6h_R1_LS', 6 * 60, 1, True, True, 'adj'),
    ('C3_8h_R1_LS', 8 * 60, 1, True, True, 'adj'),
    ('C4_7h_R1_L',  7 * 60, 1, True, False, 'long_only'),
    ('C5_7h_R1_S',  7 * 60, 1, False, True, 'short_only'),
    ('C6_4h_R1_LS', 4 * 60, 1, True, True, 'contrast_short'),
    ('C7_12h_R1_LS', 12 * 60, 1, True, True, 'contrast_long'),
    ('C9_7h_R2_LS', 7 * 60, 2, True, True, 'right2'),
    ('C10_7h_R3_LS', 7 * 60, 3, True, True, 'right3'),
]


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def pivots_lr(high, low, left, right):
    """좌left/우right 피벗. 중심이 윈도 유일 최대/최소면 피벗.
    확정봉 = 발생봉 + right (그 봉 마감돼야 우측 확정). 미래참조 차단.
    반환: ph_conf{확정봉:(발생봉,값)}, pl_conf{확정봉:(발생봉,값)} (벡터화)."""
    n = len(high)
    ph_conf = {}; pl_conf = {}
    if n < left + right + 1:
        return ph_conf, pl_conf
    from numpy.lib.stride_tricks import sliding_window_view
    win = left + right + 1
    hwin = sliding_window_view(high, win)   # (n-win+1, win)
    lwin = sliding_window_view(low, win)
    centers = np.arange(left, n - right)    # 중심 인덱스
    hmax = hwin.max(axis=1); lmin = lwin.min(axis=1)
    # 중심값
    hc = high[left:n - right]; lc = low[left:n - right]
    # 유일 최대/최소 판정
    is_ph = (hc == hmax) & ((hwin == hmax[:, None]).sum(axis=1) == 1)
    is_pl = (lc == lmin) & ((lwin == lmin[:, None]).sum(axis=1) == 1)
    for k in np.where(is_ph)[0]:
        c = centers[k]; ph_conf[c + right] = (c, float(high[c]))
    for k in np.where(is_pl)[0]:
        c = centers[k]; pl_conf[c + right] = (c, float(low[c]))
    return ph_conf, pl_conf


def compute_atr(high, low, close, Pd):
    n = len(close); tr = np.zeros(n)
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])])
    atr = np.zeros(n)
    if n > Pd:
        atr[Pd] = tr[1:Pd + 1].mean()
        for i in range(Pd + 1, n):
            atr[i] = (atr[i - 1] * (Pd - 1) + tr[i]) / Pd
    return atr


def pivot_supertrend(df_tf):
    """원본 PP-ST 추세방향. center=확정피벗 평활(c*2+pp)/3, 밴드=center±Factor*ATR.
    Trend: close>TDown[1]->1, close<TUp[1]->-1, else 유지. 봉마감 기준."""
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close)
    atr = compute_atr(high, low, close, ATR_PERIOD)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, LEFT)   # center용은 원본대로 좌우 prd
    center = np.full(n, np.nan); cur = np.nan
    for i in range(n):
        lastpp = np.nan
        if i in ph_conf: lastpp = ph_conf[i][1]
        elif i in pl_conf: lastpp = pl_conf[i][1]
        if not np.isnan(lastpp):
            cur = lastpp if np.isnan(cur) else (cur * 2 + lastpp) / 3
        center[i] = cur
    Up = center - ATR_FACTOR * atr
    Dn = center + ATR_FACTOR * atr
    TUp = np.full(n, np.nan); TDown = np.full(n, np.nan); Trend = np.zeros(n, dtype=int)
    for i in range(n):
        if i == 0 or np.isnan(Up[i]) or np.isnan(Dn[i]):
            TUp[i] = Up[i] if not np.isnan(Up[i]) else -1e18
            TDown[i] = Dn[i] if not np.isnan(Dn[i]) else 1e18
            Trend[i] = 1; continue
        TUp[i] = max(Up[i], TUp[i - 1]) if close[i - 1] > TUp[i - 1] else Up[i]
        TDown[i] = min(Dn[i], TDown[i - 1]) if close[i - 1] < TDown[i - 1] else Dn[i]
        if close[i] > TDown[i - 1]: Trend[i] = 1
        elif close[i] < TUp[i - 1]: Trend[i] = -1
        else: Trend[i] = Trend[i - 1] if Trend[i - 1] != 0 else 1
    return Trend, center, atr


def run_strategy(df_tf, right, allow_long, allow_short, lev=LEVERAGE):
    """전략 실행. 봉마감 즉시 체결. 좌LEFT/우right 진입피벗. 피보 단조 트레일."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend, _, _ = pivot_supertrend(df_tf)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, right)
    eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')

    def n_fund(a, b):
        return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

    lastPH = np.nan; lastPL = np.nan
    pos = 0; entry_price = np.nan; entry_i = -1; sl = np.nan; pb = 0
    trades = []
    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]

        if pos != 0:
            # 추세전환 전량청산
            if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                px = close[i]; R = pos * (px - entry_price) / entry_price * lev
                fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                               'entry': entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                               'bars': i - entry_i, 'fund': fp, 'year': idx[i].year})
                pos = 0; sl = np.nan; pb = 0; continue
            # 손절 터치 (진입봉 이후 4틱)
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                for px in ticks:
                    if pos == 1 and px <= sl: hit = True; break
                    if pos == -1 and px >= sl: hit = True; break
                if hit:
                    R = pos * (sl - entry_price) / entry_price * lev
                    fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                    trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                                   'entry': entry_price, 'exit': sl, 'R': R, 'reason': 'sl',
                                   'bars': i - entry_i, 'fund': fp, 'year': idx[i].year})
                    pos = 0; sl = np.nan; pb = 0; continue

        # 피보 단조 트레일 (보유중 새피벗 확정봉)
        if pos == 1 and new_pl:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1])
                sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL)
                sl = cand if np.isnan(sl) else min(sl, cand)

        # 진입 (flat, 봉마감 종가)
        if pos == 0:
            le = allow_long and Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = allow_short and Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if le:
                pos = 1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 - SL_PCT / 100)
            elif se:
                pos = -1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 + SL_PCT / 100)
    return trades


def agg(trades, label, years=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return {'칸': label, '거래수': 0}
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    gp = wins.sum(); gl = -losses.sum(); pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL; mincap = min(mincap, cap)
        if cap <= MIN_CAP: bankrupt = True; break
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    return {'칸': label, '거래수': len(trades),
            '승률_pct': round(len(wins) / len(trades) * 100, 1),
            '누적R_pct': round(R.sum() * 100, 2), '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3), '파산_참고': 'YES' if bankrupt else 'NO',
            '최저자본': round(mincap, 0), '평균보유봉': round(np.mean([t['bars'] for t in trades]), 1),
            'trend_flip': reasons.get('trend_flip', 0), 'sl': reasons.get('sl', 0),
            '펀딩총_pct': round(float(sum(t['fund'] for t in trades)) * 100, 3)}


def main():
    print("[PP_ST_Pullback_V1_stg1] Pivot SuperTrend Pullback - 36mo BTC, TFxR grid")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")

    summary = []; c1_trades = None
    tf_cache = {}
    for lab, tf, right, aL, aS, note in CELLS:
        if tf not in tf_cache:
            tf_cache[tf] = resample_tf(df1m, tf)
        df_tf = tf_cache[tf]
        trades = run_strategy(df_tf, right, aL, aS)
        mAll = agg(trades, lab); summary.append(mAll)
        print(f"  [{lab:14s}] 거래{mAll.get('거래수')} 승률{mAll.get('승률_pct')}% "
              f"누적R{mAll.get('누적R_pct')}% PF{mAll.get('PF')} "
              f"flip{mAll.get('trend_flip')}/sl{mAll.get('sl')} 보유{mAll.get('평균보유봉')}봉")
        if lab == 'C1_7h_R1_LS':
            c1_trades = trades
            # C8: 학습/검증 분리
            summary.append(agg(trades, 'C8_7h_R1_train', TRAIN_YEARS))
            summary.append(agg(trades, 'C8_7h_R1_test', TEST_YEARS))

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "pp_summary.csv"), index=False, encoding='utf-8-sig')
    if c1_trades:
        td = [{'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
               'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
               'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
               'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars']}
              for t in c1_trades]
        pd.DataFrame(td).to_csv(os.path.join(HERE, "pp_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] pp_summary.csv + pp_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
