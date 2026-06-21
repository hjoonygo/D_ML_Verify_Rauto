# -*- coding: utf-8 -*-
# [FILE] test.py  (SpTrd_Fib_V0_5 - PP-ST Pullback + Regime Filter skeleton, 36mo BTC)
# CODE LENGTH: approx 400 lines | INTERNAL VER: SpTrdFib_v0.5 | full output, no omission
#
# [PURPOSE / 목적] 검증완료된 PP-ST Pullback v1.0(=InfraA_V4_stg1)에, 36개월 장세분석에서
#   발견한 약점 1개(2025Q1 조정장 숏 -28%)를 막는 '장세 필터 골격'을 추가한 v0.5(미완성) 버전.
#   v0.5인 이유: 필터 효과는 PC 검증 전이라 신뢰도 가설(15%). 동작 정합성만 컨테이너 확인.
#
# [발전 내용 - 기존 v1.0 대비]
#   (1) R=1 고정 (R2/R3는 알파 죽음 확정 -> 제거)
#   (2) ★장세필터 추가: 급한 V자 반전 구간에선 숏 진입 차단(또는 추세 더 강할때만).
#       측정: 'recent_drop'(최근 K봉 급락폭)이 임계 초과 = 급V자 의심 -> 숏 보류.
#       필터 ON/OFF 칸을 둬서 순효과만 비교(고정진입 사상).
#   (3) trend_flip 빈틈 기록용 사유 분해는 v1.0과 동일 유지.
#
# [GRID - 장세필터 효과 검증]
#   F0_nofilter   : 필터 OFF (= v1.0 C1 재현 기준선)
#   F1_short_vguard : 급V자 구간 숏 차단
#   F2_short_strong : 숏은 추세강도(밴드폭) 충분할때만
#   F3_long_only_bear: 하락장에선 롱만(숏 전면 차단) - 극단 비교
#   각칸: 거래/승률/누적R/PF/파산참고/평균보유봉/trend_flip/sl + train/test 분리.
#
# [비용/사이징 - v1.0 동일] 왕복8bp + 펀딩8h이산. 레버1배. 파산은 참고표기, 판정=누적R/PF.
# [미래참조] 장세필터도 '확정된 과거 K봉'만 사용(미래 안봄). 피벗 좌LEFT/우RIGHT 확정.
# [PATH] D:\ML\verify\SpTrd_Fib_V0_5\ , 데이터 상위, 결과 CSV 이 하위폴더.
# [DATA] ..\Merged_Data_with_Regime_Features.csv (OHLC만 사용)
# [OUTPUT] spfib_summary.csv + spfib_trades.csv(F1 거래별)
#
# [FUNCTIONS In/Out]
#   find_data/load_data ; resample_tf ; pivots_lr ; compute_atr ; pivot_supertrend
#   recent_drop(close,i,k)->float          최근 k봉 누적 급락폭(숏 V가드용, 과거만)
#   band_strength(...)->float              추세강도(밴드폭/가격) (숏 강도필터용)
#   run_strategy(df_tf,right,filter_mode)->trades
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
RIGHT = 1               # R=1 고정 (R2/R3 알파 죽음, 36mo 확정)
COST = 0.0004
FUND_8H = 0.0001
FIB = (0.3, 0.5, 0.6)
SL_PCT = 1.0
ATR_FACTOR = 3.0
ATR_PERIOD = 10
LEVERAGE = 1.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
TF_MIN = 7 * 60         # 7h 메인

# 장세필터 파라미터 (미래참조 없게 '과거 K봉'만)
VGUARD_K = 6            # 숏 진입 직전 K봉
VGUARD_DROP = 0.08      # 그 사이 8% 이상 급락했으면 'V자 반전 위험' -> 숏 보류
STRENGTH_MIN = 0.05     # 밴드폭/가격 5% 이상이어야 추세 강함(숏 강도필터)

CELLS = [
    ('F0_nofilter', 'off'),
    ('F1_short_vguard', 'vguard'),
    ('F2_short_strong', 'strong'),
    ('F3_long_only_bear', 'longonly'),
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
    n = len(high); ph_conf = {}; pl_conf = {}
    if n < left + right + 1:
        return ph_conf, pl_conf
    from numpy.lib.stride_tricks import sliding_window_view
    win = left + right + 1
    hwin = sliding_window_view(high, win); lwin = sliding_window_view(low, win)
    centers = np.arange(left, n - right)
    hmax = hwin.max(axis=1); lmin = lwin.min(axis=1)
    hc = high[left:n - right]; lc = low[left:n - right]
    is_ph = (hc == hmax) & ((hwin == hmax[:, None]).sum(axis=1) == 1)
    is_pl = (lc == lmin) & ((lwin == lmin[:, None]).sum(axis=1) == 1)
    for k in np.where(is_ph)[0]:
        c = centers[k]; ph_conf[c + right] = (c, float(high[c]))
    for k in np.where(is_pl)[0]:
        c = centers[k]; pl_conf[c + right] = (c, float(low[c]))
    return ph_conf, pl_conf


def compute_atr(high, low, close, Pd):
    n = len(close); tr = np.zeros(n)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atr = np.zeros(n)
    if n > Pd:
        atr[Pd] = tr[1:Pd + 1].mean()
        for i in range(Pd + 1, n):
            atr[i] = (atr[i - 1] * (Pd - 1) + tr[i]) / Pd
    return atr


def pivot_supertrend(df_tf):
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close); atr = compute_atr(high, low, close, ATR_PERIOD)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, LEFT)
    center = np.full(n, np.nan); cur = np.nan
    for i in range(n):
        lastpp = np.nan
        if i in ph_conf: lastpp = ph_conf[i][1]
        elif i in pl_conf: lastpp = pl_conf[i][1]
        if not np.isnan(lastpp):
            cur = lastpp if np.isnan(cur) else (cur * 2 + lastpp) / 3
        center[i] = cur
    Up = center - ATR_FACTOR * atr; Dn = center + ATR_FACTOR * atr
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
    return Trend, center, atr, Up, Dn


def recent_drop(close, i, k):
    """진입 직전 k봉 사이 최대 급락폭(고점대비). 과거 봉만 사용(미래참조 없음).
    반환: (구간최고 - 현재) / 구간최고. 클수록 급락."""
    lo = max(0, i - k)
    window = close[lo:i + 1]
    if len(window) < 2:
        return 0.0
    peak = window.max()
    return (peak - close[i]) / peak if peak > 0 else 0.0


def run_strategy(df_tf, right, filter_mode):
    """PP-ST Pullback + 장세필터. filter_mode:
    off=필터없음 / vguard=급V자 숏차단 / strong=숏 강도충분시만 / longonly=숏전면차단."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend, center, atr, Up, Dn = pivot_supertrend(df_tf)
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
            if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                px = close[i]; R = pos * (px - entry_price) / entry_price * LEVERAGE
                fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                               'entry': entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                               'bars': i - entry_i, 'fund': fp, 'year': idx[i].year})
                pos = 0; sl = np.nan; pb = 0; continue
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                for px in ticks:
                    if pos == 1 and px <= sl: hit = True; break
                    if pos == -1 and px >= sl: hit = True; break
                if hit:
                    R = pos * (sl - entry_price) / entry_price * LEVERAGE
                    fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                    trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                                   'entry': entry_price, 'exit': sl, 'R': R, 'reason': 'sl',
                                   'bars': i - entry_i, 'fund': fp, 'year': idx[i].year})
                    pos = 0; sl = np.nan; pb = 0; continue

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

        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            # ★장세필터: 숏 진입 조건 보강 (미래참조 없게 과거봉만)
            if se:
                if filter_mode == 'longonly':
                    se = False
                elif filter_mode == 'vguard':
                    # 급V자(최근 K봉 급락) 직후엔 반등위험 -> 숏 보류
                    if recent_drop(close, i, VGUARD_K) >= VGUARD_DROP:
                        se = False
                elif filter_mode == 'strong':
                    # 추세강도(밴드폭/가격) 충분할때만 숏
                    bw = (Dn[i] - Up[i]) / close[i] if close[i] > 0 else 0
                    if not (bw >= STRENGTH_MIN):
                        se = False
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
    print("[SpTrd_Fib_V0_5] PP-ST Pullback + Regime Filter(skeleton) - 36mo BTC 7h")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")
    df_tf = resample_tf(df1m, TF_MIN)
    print(f"[7h] {len(df_tf)}bars")

    summary = []; f1_trades = None
    for lab, fmode in CELLS:
        trades = run_strategy(df_tf, RIGHT, fmode)
        mAll = agg(trades, lab); summary.append(mAll)
        print(f"  [{lab:18s}] 거래{mAll.get('거래수')} 승률{mAll.get('승률_pct')}% "
              f"누적R{mAll.get('누적R_pct')}% PF{mAll.get('PF')} "
              f"flip{mAll.get('trend_flip')}/sl{mAll.get('sl')} 파산{mAll.get('파산_참고')}")
        if lab == 'F1_short_vguard':
            f1_trades = trades
            summary.append(agg(trades, 'F1_train', TRAIN_YEARS))
            summary.append(agg(trades, 'F1_test', TEST_YEARS))

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "spfib_summary.csv"), index=False, encoding='utf-8-sig')
    if f1_trades:
        td = [{'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
               'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
               'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
               'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars']}
              for t in f1_trades]
        pd.DataFrame(td).to_csv(os.path.join(HERE, "spfib_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] spfib_summary.csv + spfib_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
