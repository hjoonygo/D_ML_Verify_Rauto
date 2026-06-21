# -*- coding: utf-8 -*-
# [파일명] test.py  (인프라알파 MTF 끝검증판)
# 코드길이: 약 300줄, 내부버전명: V2_mtf_endcheck_fillgrid, 로직 축약/생략 없이 전체 출력
#
# [목적] "버그(타이트손절·먼TP·타임아웃부활)를 고치고 가장 비관적 체결가정을 걸어도
#         MTF(60분 OB) 청산엔진이 진짜 알파를 내는가"를 9개 시나리오로 판정한다.
#         알파엔진 Exec_Fibo_v3 은 원본 그대로(바이트 동일) 재사용. 손절정책·체결가정은
#         이 하네스가 통제한다. 본전방어(BEP) 없음=피보 트레일링만(사장님 결정).
#
# [축] ① 체결가정(낙관 opt / 보수 con)  ② 손잡이(TP당기기 / SL넓히기)  ③ 기준선(MTF60 / v2 1분)
#
# [9 시나리오]  (fib_ext=0.5 고정, RR_MIN/게이트/자금모델 고정)
#   S1 cur_opt      : TP=60분OB, SL=60bp고정, 타임아웃ON, 낙관   (현행 8.8% 재현 sanity)
#   S2 cur_con      : 위와 동일, 보수                          (★Q3: 8.8% 낙관편향?)
#   S3 tp13_opt     : TP=1·3분OB, SL=60bp고정, 타임아웃OFF, 낙관 (TP손잡이 단독)
#   S4 tp13_con     : 위와 동일, 보수                          (TP손잡이 보수 생존?)
#   S5 slob100_con  : TP=60분OB, SL=60분OB연동·클램프100bp, 보수 (SL손잡이 단독)
#   S6 slob200_con  : 〃 클램프200bp, 보수
#   S7 slob300_con  : 〃 클램프300bp(v2값), 보수               (의문4: 300bp 이식 유효?)
#   S8 combo_con    : TP=1·3분OB + SL=60분OB연동200bp, 보수      (두 손잡이 결합 best-guess)
#   S9 v2base_con   : TP=1분OB, SL=60bp고정, 타임아웃OFF, 보수   (★MTF가 v2 1분보다 나은가)
#
# [속도가속] (1)TF별 pivot 전체 1회 사전계산 후 9개 config가 공유 (2)nearest는 confirm
#   단조증가 성질로 searchsorted 유효프리픽스 컷 후 numpy 마스크 (3)빈구간 점프
#   (4)1차익절 전 데이터윈도우는 최근 60봉만 슬라이스. 반드시 컨테이너 스모크 통과본.
#
# [경로] 하위폴더 D:\ML\verify\<zip명>\ 에서 실행. 데이터는 상위 D:\ML\verify.
#        결과 CSV는 하위폴더에 저장(테스트 산출물). check.py가 ..\00WorkHstr 로 분석 기록.
#
# [★결과 전량 파일] V2_summary.csv + V2_diag.csv + V2_yearly.csv + V2_trades_*.csv. 복붙 불필요.
#
# [함수 In/Out]
#   load_data(path) -> df(OHLC+regime)
#   prep_pivots(df) -> dict pv[tf] + TP1·3합집합 (사전계산 1회)
#   nearest_above/below(price, ts64, conf, top, bot) -> (top,bottom) or None  (searchsorted컷)
#   entry_gate(price, ts64, hp..., lp...) -> dict(pass, sl_price, tp_price, sl_dist, tp_dist, rr, fail)
#   wait_entry(...) -> (e_idx, gate) or (None, 사유)   대기 4h
#   simulate_one(...) -> (rows, pnl, why)   하네스 손절정책 + 체결가정 + Exec_Fibo_v3 청산
#   run_cfg(cfg) -> (trades, cap_curve, bankrupt, diag)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ob_mtf import resample_tf, precompute_tf_pivots
from Exec_Fibo_v3 import Exec_Fibo_v3   # 알파엔진(원본 그대로). 1차익절 트리거 + Phase2 피보락인.

# ---- 고정 상수(모든 시나리오 공통) ----
SL_GATE = 0.0032; TP_GATE = 0.0048; SL_CLAMP_GATE = 0.0100; TP_CLAMP = 0.01618
RR_MIN = 1.5
WAIT_MIN = 240               # 대기 진입 4시간(사장님 지시)
LEVERAGE = 5; START_CAP = 10000.0; RISK_PCT = 0.07; LIQ_MOVE = 0.20
COST = 0.0004; FUNDING_DAILY = 0.0001; MIN_CAP = 100.0
W_TF = 3                     # pivot 윈도우(좌우 3봉)
REGIME_COL = 'feat_struct_8'
MAX_HOLD_BARS = 60 * 24 * 120
FIB_EXT = 0.5                # 락인 비율 고정(보고서: 비율차 미미, TF분리 후 재확인 대상)
HARD_SL_FIXED = 0.0060       # 60bp 고정 손절(=fib_sl_roe 3%/lev5). 원본 1분 시절 값.
TF_TP_SMALL = (1, 3)         # 'TP 1·3분' = 1분·3분 지지OB 합집합
OB_TF_BIG = 60               # 상위 TF(SL/일반 TP)

# ---- 9개 시나리오 정의 ----
# tp_mode: 'big'(60분) / 'small'(1·3분) / 'v2'(1분)
# sl_mode: 'fixed'(60bp) / 'ob'(60분 저항OB연동, clamp=값)
# fill   : 'opt'(낙관) / 'con'(보수)
# timeout: 1차익절 전 4H 강제청산 여부
CONFIGS = [
    dict(sid='S1_cur_opt',    tp_mode='big',   sl_mode='fixed', clamp=None,   fill='opt', timeout=True),
    dict(sid='S2_cur_con',    tp_mode='big',   sl_mode='fixed', clamp=None,   fill='con', timeout=True),
    dict(sid='S3_tp13_opt',   tp_mode='small', sl_mode='fixed', clamp=None,   fill='opt', timeout=False),
    dict(sid='S4_tp13_con',   tp_mode='small', sl_mode='fixed', clamp=None,   fill='con', timeout=False),
    dict(sid='S5_slob100_con',tp_mode='big',   sl_mode='ob',    clamp=0.0100, fill='con', timeout=False),
    dict(sid='S6_slob200_con',tp_mode='big',   sl_mode='ob',    clamp=0.0200, fill='con', timeout=False),
    dict(sid='S7_slob300_con',tp_mode='big',   sl_mode='ob',    clamp=0.0300, fill='con', timeout=False),
    dict(sid='S8_combo_con',  tp_mode='small', sl_mode='ob',    clamp=0.0200, fill='con', timeout=False),
    dict(sid='S9_v2base_con', tp_mode='v2',    sl_mode='fixed', clamp=None,   fill='con', timeout=False),
]


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 데이터 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def _sorted_union(arrs):
    """여러 (confirm,top,bot) 묶음을 confirm 오름차순으로 합집합 정렬(searchsorted 위해 단조)."""
    conf = np.concatenate([a[0] for a in arrs]) if arrs else np.array([], dtype='datetime64[ns]')
    top = np.concatenate([a[1] for a in arrs]) if arrs else np.array([], dtype=float)
    bot = np.concatenate([a[2] for a in arrs]) if arrs else np.array([], dtype=float)
    if len(conf) == 0:
        return conf, top, bot
    order = np.argsort(conf, kind='mergesort')
    return conf[order], top[order], bot[order]


def prep_pivots(df):
    """TF별 pivot 1회 사전계산 후 공유. 반환 dict:
       pv['SL_big']=(conf,top,bot) 60분 저항OB / pv['TP_big']=지지OB 60분
       pv['TP_small']=1·3분 지지OB 합집합 / pv['SL_v2'],pv['TP_v2']=1분."""
    pv = {}
    cache = {}
    for tf in sorted(set([OB_TF_BIG, *TF_TP_SMALL])):
        df_tf = resample_tf(df, tf)
        hpc, lpc, hpt, hpb, lpt, lpb = precompute_tf_pivots(df_tf, W_TF, tf)
        cache[tf] = dict(hp=(hpc, hpt, hpb), lp=(lpc, lpt, lpb))
    pv['SL_big'] = cache[OB_TF_BIG]['hp']
    pv['TP_big'] = cache[OB_TF_BIG]['lp']
    pv['TP_small'] = _sorted_union([cache[tf]['lp'] for tf in TF_TP_SMALL])
    pv['SL_v2'] = cache[1]['hp']
    pv['TP_v2'] = cache[1]['lp']
    return pv


def nearest_above(price, ts64, conf, top, bot):
    """진입가 위 가장 가까운 저항 OB(SL용). 확정시각<=ts 인 것만(미래참조 가드).
       conf 단조증가 -> searchsorted 로 유효프리픽스 컷(속도가속). bottom>price 중 bottom 최소."""
    k = np.searchsorted(conf, ts64, side='right')
    if k == 0:
        return None
    b = bot[:k]; t = top[:k]
    m = b > price
    if not m.any():
        return None
    bb = b[m]; tt = t[m]
    j = np.argmin(bb)
    return (float(tt[j]), float(bb[j]))


def nearest_below(price, ts64, conf, top, bot):
    """진입가 아래 가장 가까운 지지 OB(TP용). top<price 중 top 최대."""
    k = np.searchsorted(conf, ts64, side='right')
    if k == 0:
        return None
    t = top[:k]; b = bot[:k]
    m = t < price
    if not m.any():
        return None
    tt = t[m]; bb = b[m]
    j = np.argmax(tt)
    return (float(tt[j]), float(bb[j]))


def entry_gate(price, ts64, sl_arr, tp_arr):
    """게이트(원본 의미 유지). 숏: TP=아래지지OB, SL=위저항OB. RR/게이트는 OB거리로 판정."""
    res = {'pass': False, 'fail': None, 'sl_price': None, 'tp_price': None,
           'sl_dist': None, 'tp_dist': None, 'rr': None}
    tp = nearest_below(price, ts64, *tp_arr)
    sl = nearest_above(price, ts64, *sl_arr)
    if tp is None: res['fail'] = 'no_tp_ob'; return res
    tp_price = tp[0]; tp_dist = (price - tp_price) / price
    res['tp_price'] = tp_price; res['tp_dist'] = tp_dist
    if sl is None: res['fail'] = 'no_sl_ob'; return res
    sl_price = sl[0]; sl_dist = (sl_price - price) / price
    res['sl_price'] = sl_price; res['sl_dist'] = sl_dist
    if sl_dist < SL_GATE: res['fail'] = 'sl_gate'; return res
    if sl_dist > SL_CLAMP_GATE: sl_eff = SL_CLAMP_GATE; tp_req = TP_CLAMP
    else: sl_eff = sl_dist; tp_req = TP_GATE
    res['sl_dist'] = sl_eff
    if tp_dist < tp_req: res['fail'] = 'tp_gate'; return res
    rr = tp_dist / max(sl_eff, 1e-8); res['rr'] = rr
    if rr < RR_MIN: res['fail'] = 'rr_gate'; return res
    res['pass'] = True
    return res


def wait_entry(c, idxv, t0, sl_arr, tp_arr, diag):
    """대기 진입 4h: t0 게이트검사, 미달이면 매분 재검사, 통과시 그 시점 진입."""
    g = entry_gate(c[t0], idxv[t0], sl_arr, tp_arr)
    diag['checked'] += 1
    if g['sl_dist'] is not None: diag['sl_dist'].append(g['sl_dist'])
    if g['tp_dist'] is not None: diag['tp_dist'].append(g['tp_dist'])
    if g['rr'] is not None: diag['rr'].append(g['rr'])
    if g['pass']:
        return t0, g
    n = len(c)
    for k in range(1, WAIT_MIN + 1):
        t = t0 + k
        if t >= n: return None, 'wait_no_data'
        g = entry_gate(c[t], idxv[t], sl_arr, tp_arr)
        if g['pass']:
            diag['wait_success'] += 1
            if g['sl_dist'] is not None: diag['sl_dist'].append(g['sl_dist'])
            if g['tp_dist'] is not None: diag['tp_dist'].append(g['tp_dist'])
            if g['rr'] is not None: diag['rr'].append(g['rr'])
            return t, g
    diag['wait_timeout'] += 1
    return None, 'wait_timeout'


def _ticks(o_, h_, l_, c_, fill):
    """체결가정. con(보수)=항상 O->H->L->C (숏에 불리한 고가 먼저). opt(낙관)=캔들방향 기반."""
    if fill == 'con':
        return (o_, h_, l_, c_)
    return (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)


def _row(entry, price, size, et, xt, reduced, reason, net):
    return dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                연도=et.year, 진입가=round(entry, 2), 청산가=round(price, 2), 명목=round(size, 2),
                청산사유=reason, 순수익=round(net, 2), 손실률pct=round((price - entry) / entry * 100, 3),
                구분='REDUCE' if '분할' in reason else 'CLOSE')


def simulate_one(exec_eng, df, o, h, l, c, idx, e_idx, gate, capital, cfg, tp_target):
    """하네스가 손절정책·체결가정 통제. 1차익절·Phase2피보는 Exec_Fibo_v3(원본).
       엔진 내부 Phase1 하드손절은 fib_sl_roe 거대값으로 비활성 -> 하네스가 SL 소유."""
    entry = c[e_idx]
    # 하네스 Phase1 보호선(=실제 손절): fixed=60bp / ob=min(60분저항OB, entry*(1+clamp))
    if cfg['sl_mode'] == 'fixed':
        stop_price = entry * (1 + HARD_SL_FIXED)
    else:
        ob_sl = gate['sl_price']
        stop_price = min(ob_sl, entry * (1 + cfg['clamp']))
    sl_dist_eff = (stop_price - entry) / entry          # ★실제 손절거리로 사이징(불일치 노출/측정)
    risk_amt = capital * RISK_PCT
    notional = min(risk_amt / max(sl_dist_eff, 1e-8), capital * 2)
    liq_price = entry * (1 + LIQ_MOVE)

    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'ob_initialized': True, 'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False,
          'fib_stop': None, 'bearish_obs': [], 'lh_price': entry, 'floor_init': None, 'reduced_once': False,
          'bullish_obs': [{'top': tp_target * 1.0002, 'bottom': tp_target, 'mean': tp_target}],
          'init_sl_price': stop_price, 'df_1m': None}
    first_i = e_idx + 1; w0 = max(0, first_i - 60 + 1)
    bs['df_1m'] = df.iloc[w0:first_i + 1]
    # fib_sl_roe 거대값 -> 엔진 내부 하드손절 비활성(하네스가 SL 처리). sl_mode=3 -> Phase2 floor=init_sl_price.
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': 15.0, 'fib_sl_roe': 999999.0,
              'innovation1': True, 'sl_mode': 3, 'fib_ext_pct': FIB_EXT}

    size = notional; reduced = False; pnl_total = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); rows = []
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        for price in _ticks(o_, h_, l_, c_, cfg['fill']):
            # 1) 강제청산
            if price >= liq_price:
                loss = size * ((entry - liq_price) / entry); fee = size * COST * 2
                pnl_total += loss - fee
                rows.append(_row(entry, liq_price, size, idx[e_idx], idx[i], reduced, '강제청산(-20%)', loss - fee))
                return rows, pnl_total, '강제청산'
            # 2) 하네스 Phase1 하드손절(1차익절 전만). 보수체결이면 고가 먼저라 손절이 먼저 잡힘.
            if not reduced and price >= stop_price:
                loss = size * ((entry - price) / entry); fee = size * COST * 2
                pnl_total += loss - fee
                tag = '하드손절60bp' if cfg['sl_mode'] == 'fixed' else f"하드손절OB({int(cfg['clamp']*10000)}bp상한)"
                rows.append(_row(entry, price, size, idx[e_idx], idx[i], reduced, tag, loss - fee))
                return rows, pnl_total, 'hard_sl'
            # 3) 알파엔진: 1차익절(REDUCE) / Phase2 피보락인(CLOSE)
            sig = exec_eng.check_exit(price, bs, params); act = sig.get('action') if sig else None
            if act == 'REDUCE_SHORT' and not reduced:
                amt = size * 0.5; pnl = amt * ((entry - price) / entry); fee = amt * COST * 2
                pnl_total += pnl - fee
                rows.append(_row(entry, price, amt, idx[e_idx], idx[i], False, '1차OB분할익절', pnl - fee))
                size *= 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                pnl = size * ((entry - price) / entry); fee = size * COST * 2
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400; funding = size * FUNDING_DAILY * dur
                pnl_total += pnl - fee - funding
                rows.append(_row(entry, price, size, idx[e_idx], idx[i], reduced, sig['reason'][:30], pnl - fee - funding))
                return rows, pnl_total, 'close'
        # 4) 타임아웃(현행 config만): 1차익절 전 4H 강제청산
        if cfg['timeout'] and (i - e_idx) >= 240 and not reduced:
            price = c_; pnl = size * ((entry - price) / entry); fee = size * COST * 2
            pnl_total += pnl - fee
            rows.append(_row(entry, price, size, idx[e_idx], idx[i], reduced, 'timeout_4h', pnl - fee))
            return rows, pnl_total, 'timeout'
    price = c[end_idx - 1]; pnl = size * ((entry - price) / entry); pnl_total += pnl - size * COST * 2
    rows.append(_row(entry, price, size, idx[e_idx], idx[end_idx - 1], reduced, 'max_hold', pnl))
    return rows, pnl_total, 'max_hold'


def _tp_target_arrs(cfg, pv):
    """1차익절 '목표' OB 배열. 진입 게이트(품질/RR)는 모든 시나리오 공통 60분.
       당기기 계열만 익절목표를 가까운 1·3분/1분 지지OB로 사용."""
    if cfg['tp_mode'] == 'small':
        return pv['TP_small']
    if cfg['tp_mode'] == 'v2':
        return pv['TP_v2']
    return None  # big: 게이트 60분 TP를 그대로 익절목표로


def run_cfg(cfg, df, o, h, l, c, idx, idxv, down_idx, pv):
    sl_arr = pv['SL_big']; tp_arr = pv['TP_big']   # 진입 게이트는 모든 시나리오 공통(60분)
    tp_tgt_arr = _tp_target_arrs(cfg, pv)           # 1차익절 목표만 분리
    exec_eng = Exec_Fibo_v3()
    cap = START_CAP; cap_curve = [cap]; trades = []; bankrupt = False
    diag = {'sl_dist': [], 'tp_dist': [], 'rr': [], 'pass': 0, 'checked': 0,
            'wait_success': 0, 'wait_timeout': 0, 'fib_cnt': 0}
    n = len(c); cur = 0
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        t0 = int(down_idx[dptr])
        if t0 >= n - 1: break
        if cap <= MIN_CAP: bankrupt = True; break
        e_idx, gate = wait_entry(c, idxv, t0, sl_arr, tp_arr, diag)
        if e_idx is not None:
            diag['pass'] += 1
            # 1차익절 목표가 결정: 당기기 계열은 진입가 아래 가까운 1·3분/1분 지지OB.
            # 없으면 게이트 60분 TP로 폴백.
            tp_target = gate['tp_price']
            if tp_tgt_arr is not None:
                r = nearest_below(c[e_idx], idxv[e_idx], *tp_tgt_arr)
                if r is not None and r[0] < c[e_idx]:
                    tp_target = r[0]
            rows, pnl, why = simulate_one(exec_eng, df, o, h, l, c, idx, e_idx, gate, cap, cfg, tp_target)
            if any('락인' in str(r['청산사유']) or 'Fibonacci' in str(r['청산사유']) for r in rows):
                diag['fib_cnt'] += 1
            cap += pnl; cap_curve.append(cap)
            for r in rows: r['거래후자본'] = round(cap, 2)
            trades.extend(rows)
            last_x = pd.to_datetime(rows[-1]['청산시간']); x_idx = idx.searchsorted(last_x)
            cur = max(int(x_idx) + 1, e_idx + 1)
        else:
            # wait_entry가 t0~t0+WAIT_MIN 을 모두 검사해 전부 실패 -> 그 구간은 진입 불가가
            # 입증됨. 재검사 말고 건너뛴다(결과 불변, 속도가속). no_data면 자연히 종료.
            cur = t0 + WAIT_MIN + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return trades, cap_curve, bankrupt, diag


def _pf(net_arr):
    g = net_arr
    if (g < 0).any():
        return round(g[g > 0].sum() / abs(g[g < 0].sum()), 3)
    return 9.99


def main():
    print("[V2 끝검증] 9시나리오: 체결(낙관/보수) x 손잡이(TP당기기/SL넓히기) x 기준선(MTF/v2)")
    data = find_data(); print(f"[데이터] {data}")
    df = load_data(data)
    o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    idx = df.index; idxv = idx.values
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
    print(f"[로드] {len(df):,}행 하락장 {len(down_idx):,}봉. pivot 사전계산 중...")
    pv = prep_pivots(df)
    print(f"[pivot] SL60분 {len(pv['SL_big'][0])}개 / TP1·3분 {len(pv['TP_small'][0])}개 / v2-1분 {len(pv['TP_v2'][0])}개\n")

    summary = []; diag_rows = []; yearly = []
    for cfg in CONFIGS:
        trades, curve, bankrupt, diag = run_cfg(cfg, df, o, h, l, c, idx, idxv, down_idx, pv)
        sid = cfg['sid']
        pd.DataFrame(trades).to_csv(os.path.join(HERE, f"V2_trades_{sid}.csv"), index=False, encoding='utf-8-sig')
        curve = np.array(curve)
        sl = np.array(diag['sl_dist']); tp = np.array(diag['tp_dist']); rr = np.array(diag['rr'])
        diag_rows.append(dict(시나리오=sid, 검사수=diag['checked'], 진입=diag['pass'],
                              대기성공=diag['wait_success'], 대기타임아웃=diag['wait_timeout'],
                              피보발동=diag['fib_cnt'],
                              SL중앙bp=round(np.median(sl) * 10000, 1) if len(sl) else 0,
                              TP중앙bp=round(np.median(tp) * 10000, 1) if len(tp) else 0,
                              RR중앙=round(np.median(rr), 2) if len(rr) else 0))
        if len(trades):
            d = pd.DataFrame(trades)
            g = d.groupby('진입시간')['순수익'].sum().values
            mdd = (curve - np.maximum.accumulate(curve)).min()
            # 하드손절 평균 손실%(사이징 불일치 노출)
            hs = d[d['청산사유'].str.contains('하드손절', na=False)]
            hs_avg = round(hs['손실률pct'].mean(), 2) if len(hs) else 0.0
            # 청산사유 분포
            vc = d['청산사유'].apply(lambda s: '하드손절' if '하드손절' in s else
                                  ('피보락인' if ('락인' in s or 'Fibonacci' in s) else
                                   ('1차익절' if '분할' in s else
                                    ('타임아웃' if 'timeout' in s else
                                     ('강제청산' if '강제' in s else 'maxhold/SL보호')))))
            dist = vc.value_counts().to_dict()
            row = dict(시나리오=sid, 진입수=len(g), PF=_pf(g), 승률=round((g > 0).mean() * 100, 1),
                       최종자본=round(curve[-1]), 수익률=f"{(curve[-1] / START_CAP - 1) * 100:.0f}%",
                       최저자본=round(curve.min()), MDD=round(mdd), 파산='YES' if bankrupt else 'NO',
                       하드손절건=int(dist.get('하드손절', 0)), 피보건=int(dist.get('피보락인', 0)),
                       하드손절평균손실pct=hs_avg)
            # 연도별 PF(보수 config 중심으로 표본운 점검)
            for yr, sub in d.groupby('연도'):
                gy = sub.groupby('진입시간')['순수익'].sum().values
                if len(gy):
                    yearly.append(dict(시나리오=sid, 연도=int(yr), 진입수=len(gy),
                                       PF=_pf(gy), 순익=int(round(gy.sum()))))
        else:
            row = dict(시나리오=sid, 진입수=0, PF=0, 승률=0, 최종자본=int(START_CAP), 수익률='0%',
                       최저자본=int(START_CAP), MDD=0, 파산='NO', 하드손절건=0, 피보건=0, 하드손절평균손실pct=0.0)
        summary.append(row)
        print(f"  [{sid}] 진입{row['진입수']} 하드손절{row['하드손절건']}(평균{row['하드손절평균손실pct']}%) "
              f"피보{row['피보건']} -> PF={row['PF']} 자본{row['수익률']} 파산{row['파산']}")

    pd.DataFrame(diag_rows).to_csv(os.path.join(HERE, "V2_diag.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "V2_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(yearly).to_csv(os.path.join(HERE, "V2_yearly.csv"), index=False, encoding='utf-8-sig')
    print("\n[저장] V2_summary.csv + V2_diag.csv + V2_yearly.csv + V2_trades_*.csv — 전량 파일")


if __name__ == "__main__":
    main()
