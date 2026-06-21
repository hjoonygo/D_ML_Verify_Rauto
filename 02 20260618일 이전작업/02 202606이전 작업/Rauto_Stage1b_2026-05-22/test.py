# -*- coding: utf-8 -*-
# [파일명] test.py  (Stage1b)
# 코드길이: 약 320줄, 내부버전명: Stage1b_gate_compound_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] Stage1의 두 오류를 고쳐 알파 검증:
#   오류1 수정: 단일 OB TP -> ★검증청산엔진(Exec_Dynamic_TS) 그대로 재사용 = 다중OB 계단익절 복원
#   오류2 수정: 자금모델을 복리 + 거래당 위험7% + 강제청산(-20%가격) + 파산정지로 현실화
#   진입: v9 게이트(SL>=32bp, TP>=48bp, RR>=1.5, SL>100bp 클램프)로 OB有 자리만.
#   * MTF(상위TF OB)는 다음 단계. 여기선 OB도 1분봉(검증엔진과 동일조건).
#
# [자금모델 — 사용자 결정]
#   시작자본 10,000$. 복리(거래후 자본 갱신).
#   거래당 위험 = 자본 × 7%. 명목 = 위험허용액 / SL거리. (SL 맞으면 자본 7% 손실로 균등)
#   증거금 = 명목/레버. 명목>자본×레버면 클램프. 자본<=최소금액이면 파산정지.
#   강제청산: 숏 청산가=진입가×1.20 (SL 미작동시 최후 안전망).
#
# [그리드] RR_MIN {1.5, 2.0} × 본전스탑 {ON, OFF} = 4 config
#   본전스탑: 1차OB 도달 분할익절 후 잔량 SL을 최초진입가-16bp(숏)로. OFF면 검증엔진 기본.
#
# [★결과 전량 파일저장] S1b_trades_*.csv + S1b_summary.csv. 화면 복붙 불필요.
# [경로규칙] 하위폴더 실행, 데이터는 상위 D:\ML\verify. check.py가 ..\00WorkHstr\ 로.
#
# [함수 In/Out]
#   load_data / precompute_pivots(ob_fast)
#   entry_gate(side,price,e_idx,hp,lp,h,l,rr_min) -> dict(pass,sl_price,tp_price,sl_dist,...)
#   simulate_one(...) -> (거래행리스트, 최종손익, 청산사유) : 검증엔진 check_exit로 청산
#   run_config(...) -> 거래 전체 + 자본곡선 + 파산여부
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ob_fast import precompute_pivots, nearest_above, nearest_below
from Exec_Dynamic_TS_GridD_v1 import Exec_Dynamic_TS_GridD_v1   # ★검증 청산엔진(다중OB 계단익절)

# ---- 게이트 상수(보고서 v9) ----
SL_GATE = 0.0032; TP_GATE = 0.0048; SL_CLAMP = 0.0100; TP_CLAMP = 0.01618
BEP_BP = 0.0016
LEVERAGE = 5
START_CAP = 10000.0
RISK_PCT = 0.07            # 거래당 위험 7%
LIQ_MOVE = 0.20            # 강제청산 가격역행 20%
COST = 0.0004             # 편도 수수료(왕복은 *2)
FUNDING_DAILY = 0.0001
MIN_CAP = 100.0           # 파산 임계
OB_W = 5
REGIME_COL = 'feat_struct_8'
MAX_HOLD_BARS = 60*24*120

CONFIGS = [
    (1.5, True,  'rr15_bepON'),
    (1.5, False, 'rr15_bepOFF'),
    (2.0, True,  'rr20_bepON'),
    (2.0, False, 'rr20_bepOFF'),
]


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    if REGIME_COL in head.columns:
        cols.append(REGIME_COL)
    else:
        raise KeyError(f"{REGIME_COL} 없음")
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def entry_gate(side, price, e_idx, hp, lp, h, l, rr_min):
    res = {'pass': False, 'fail': None, 'sl_price': None, 'tp_price': None, 'sl_dist': None, 'rr': None}
    tp_ob = nearest_below(price, e_idx, lp, h, l, OB_W)   # 숏 TP = 아래 지지OB
    sl_ob = nearest_above(price, e_idx, hp, h, l, OB_W)   # 숏 SL = 위 저항OB
    if tp_ob is None:
        res['fail'] = 'no_tp_ob'; return res
    tp_price = float(tp_ob[0]); tp_dist = (price - tp_price)/price
    if sl_ob is None:
        res['fail'] = 'no_sl_ob'; return res
    sl_price = float(sl_ob[0]); sl_dist = (sl_price - price)/price
    res.update(sl_price=sl_price, tp_price=tp_price, sl_dist=sl_dist)
    if sl_dist < SL_GATE:
        res['fail'] = 'sl_gate'; return res
    if sl_dist > SL_CLAMP:
        sl_eff = SL_CLAMP; tp_req = TP_CLAMP
    else:
        sl_eff = sl_dist; tp_req = TP_GATE
    res['sl_dist'] = sl_eff
    if tp_dist < tp_req:
        res['fail'] = 'tp_gate'; return res
    rr = tp_dist/max(sl_eff, 1e-8); res['rr'] = rr
    if rr < rr_min:
        res['fail'] = 'rr_gate'; return res
    res['pass'] = True
    return res


def simulate_one(exec_eng, df, o, h, l, c, idx, e_idx, gate, capital, bep_on, split_ratio=0.5):
    """검증청산엔진으로 청산 추적. 복리 수량(위험7%) + 강제청산. SHORT 전용."""
    entry = c[e_idx]
    sl_dist = gate['sl_dist']
    # --- 복리 수량: SL 맞으면 자본 7% 손실 ---
    risk_amt = capital * RISK_PCT
    notional = risk_amt / sl_dist               # SL거리에 반비례
    notional = min(notional, capital * LEVERAGE)  # 증거금<=자본 클램프
    liq_price = entry * (1 + LIQ_MOVE)            # 숏 강제청산가

    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0,
          'target_idx': 0, 'ob_initialized': False, 'fib_wave_start': entry,
          'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': [], 'bearish_obs': [], 'entry_regime': 'downtrend', 'entry_reason': 'gate'}
    first_i = e_idx + 1
    w0 = max(0, first_i - 60 + 1)
    bs['df_1m'] = df.iloc[w0:first_i+1]
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': 15.0, 'fib_sl_roe': 3.0, 'fib_ext_pct': 0.65,
              'innovation1': True}
    size = notional
    reduced = False
    pnl_total = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS)
    rows = []
    for i in range(e_idx+1, end_idx):
        o_,h_,l_,c_ = o[i],h[i],l[i],c[i]
        ticks = (o_,h_,l_,c_) if c_ < o_ else (o_,l_,h_,c_)
        for price in ticks:
            # 강제청산 우선 체크(숏: 가격 >= 청산가)
            if price >= liq_price:
                pnl = -(capital * 1.0)  # 증거금=자본전액 가정 아님; 명목손실로 계산
                loss = size * ((entry - liq_price)/entry)   # 음수
                fee = size * COST * 2
                pnl_total += loss - fee
                rows.append(_row(entry, liq_price, size, idx[e_idx], idx[i], reduced, '강제청산(-20%)', loss-fee))
                return rows, pnl_total, '강제청산'
            sig = exec_eng.check_exit(price, bs, params)
            act = sig.get('action') if sig else None
            if act == 'REDUCE_SHORT' and not reduced:
                amt = size * split_ratio
                pnl = amt * ((entry - price)/entry); fee = amt * COST * 2
                pnl_total += pnl - fee
                rows.append(_row(entry, price, amt, idx[e_idx], idx[i], False, '1차OB분할익절', pnl-fee))
                size *= (1 - split_ratio); reduced = True
                if bep_on:
                    bs['fib_stop'] = entry * (1 - BEP_BP)   # 숏 본전스탑: 진입가-16bp
                continue
            if act == 'CLOSE_SHORT':
                pnl = size * ((entry - price)/entry); fee = size * COST * 2
                dur = (idx[i]-idx[e_idx]).total_seconds()/86400
                funding = size * FUNDING_DAILY * dur
                pnl_total += pnl - fee - funding
                rows.append(_row(entry, price, size, idx[e_idx], idx[i], reduced, sig['reason'][:30], pnl-fee-funding))
                return rows, pnl_total, 'close'
        if (i - e_idx) >= 240 and not reduced:   # 4H timeout (1차OB 미도달만)
            price = c_
            pnl = size * ((entry - price)/entry); fee = size * COST * 2
            pnl_total += pnl - fee
            rows.append(_row(entry, price, size, idx[e_idx], idx[i], reduced, 'timeout_4h', pnl-fee))
            return rows, pnl_total, 'timeout'
    price = c[end_idx-1]
    pnl = size*((entry-price)/entry); pnl_total += pnl - size*COST*2
    rows.append(_row(entry, price, size, idx[e_idx], idx[end_idx-1], reduced, 'max_hold', pnl))
    return rows, pnl_total, 'max_hold'


def _row(entry, price, size, et, xt, reduced, reason, net):
    return dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                연도=et.year, 진입가=round(entry,2), 청산가=round(price,2), 명목=round(size,2),
                청산사유=reason, 순수익=round(net,2),
                구분='REDUCE' if '분할' in reason else 'CLOSE')


def run_config(df, o, h, l, c, idx, down_idx, hp, lp, rr_min, bep_on):
    exec_eng = Exec_Dynamic_TS_GridD_v1()
    cap = START_CAP
    cap_curve = [cap]
    trades = []
    bankrupt = False
    gate_stats = {'pass':0,'no_tp_ob':0,'no_sl_ob':0,'sl_gate':0,'tp_gate':0,'rr_gate':0}
    cur = OB_W + 10
    dptr = np.searchsorted(down_idx, cur, side='left')
    n = len(c)
    while dptr < len(down_idx):
        e_idx = int(down_idx[dptr])
        if e_idx >= n-1: break
        if cap <= MIN_CAP:
            bankrupt = True; break
        gate = entry_gate('short', c[e_idx], e_idx, hp, lp, h, l, rr_min)
        if gate['pass']:
            gate_stats['pass'] += 1
            rows, pnl, why = simulate_one(exec_eng, df, o,h,l,c, idx, e_idx, gate, cap, bep_on)
            cap += pnl
            cap_curve.append(cap)
            for r in rows: r['거래후자본'] = round(cap,2)
            trades.extend(rows)
            last_x = pd.to_datetime(rows[-1]['청산시간']); x_idx = idx.searchsorted(last_x)
            cur = max(int(x_idx)+1, e_idx+1)
        else:
            gate_stats[gate['fail']] = gate_stats.get(gate['fail'],0)+1
            cur = e_idx+1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return trades, cap_curve, bankrupt, gate_stats


def main():
    print("[Stage1b] 게이트+검증청산엔진(다중OB계단)+복리위험7%+강제청산")
    data = find_data(); print(f"[데이터] {data}")
    df = load_data(data)
    o,h,l,c = df['open'].values,df['high'].values,df['low'].values,df['close'].values
    idx = df.index
    down_idx = np.where(df[REGIME_COL].astype(str).values=='downtrend')[0]
    print(f"[로드] {len(df):,}행 하락장 {len(down_idx):,}봉. pivot 계산...")
    hp, lp = precompute_pivots(h, l, OB_W)
    print(f"[pivot] 고점{len(hp):,} 저점{len(lp):,}. config {len(CONFIGS)}개 실행...")

    summary = []
    for rr_min, bep_on, tag in CONFIGS:
        trades, curve, bankrupt, gs = run_config(df, o,h,l,c, idx, down_idx, hp, lp, rr_min, bep_on)
        pd.DataFrame(trades).to_csv(os.path.join(HERE, f"S1b_trades_{tag}.csv"), index=False, encoding='utf-8-sig')
        curve = np.array(curve)
        if len(trades):
            d = pd.DataFrame(trades); g = d.groupby('진입시간')['순수익'].sum().values
            pf = g[g>0].sum()/abs(g[g<0].sum()) if (g<0).any() else 9.99
            mdd = (curve - np.maximum.accumulate(curve)).min()
            row = dict(config=tag, rr=rr_min, bep='ON' if bep_on else 'OFF',
                       진입수=len(g), PF=round(pf,3), 승률=round((g>0).mean()*100,1),
                       최종자본=round(curve[-1]), 시작=int(START_CAP),
                       수익률=f"{(curve[-1]/START_CAP-1)*100:.0f}%",
                       최저자본=round(curve.min()), MDD=round(mdd),
                       파산='YES' if bankrupt else 'NO', 게이트통과=gs['pass'])
        else:
            row = dict(config=tag, rr=rr_min, bep='ON' if bep_on else 'OFF', 진입수=0,
                       PF=0, 승률=0, 최종자본=int(START_CAP), 시작=int(START_CAP), 수익률='0%',
                       최저자본=int(START_CAP), MDD=0, 파산='NO', 게이트통과=gs['pass'])
        summary.append(row)
        print(f"  {tag}: 진입{row['진입수']} PF={row['PF']} 자본 {row['시작']}->{row['최종자본']}({row['수익률']}) "
              f"최저{row['최저자본']} 파산{row['파산']}")
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "S1b_summary.csv"), index=False, encoding='utf-8-sig')
    print("[저장] S1b_trades_*.csv (4) + S1b_summary.csv — 전량 파일저장 완료")


if __name__ == "__main__":
    main()
