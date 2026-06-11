# -*- coding: utf-8 -*-
# [파일명] 테스트코드.py  (Stage1)
# 코드길이: 약 330줄, 내부버전명: Stage1_gate_bep_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 인프라알파 결합 1단계 — 진입게이트 + 본전스탑(+16bp) + 분할익절 + 4h/무제한 보유.
#        3분할 진입과 뉴욕폐장은 2·3단계에서 추가. 여기선 '게이트 통과 시 전량진입'만.
#        36개월 하락장(feat_struct_8=downtrend) SHORT 순차 시뮬로 OB게이트가 흑자를 만드는지 확인.
#
# [보고서 사양 그대로 — 추측 없음]
#   진입게이트(v9 check_entry_gate): SL_GATE=32bp, TP_GATE=48bp, RR_MIN=1.5,
#                                    SL_CLAMP=100bp(초과시 SL=100bp & TP게이트=161.8bp)
#   OB 탐지: ob_provider_v2.get_levels_above/below (룩어헤드 가드 i<=t-w-1)
#   보유: 1차OB 도달(스텝업 활성)이면 무제한, 아니면 4H(240분) timeout
#   분할익절: 1차OB 도달 시 split_ratio 만큼 익절 + 본전스탑(최초진입가+16bp) 잔량에 적용
#
# [그리드] 본전스탑 16bp 해석 2종 × 분할익절 2종 = 4 config
#   bep_mode: 'price'(진입가+16bp 가격) / 'lev'(진입가+16bp*레버=80bp 가격)
#   split_ratio: 0.55 / 0.60  (앞=1차익절 비율)
#
# [★결과 전량 파일저장] 콘솔은 진행상황만. 거래 CSV + 분석/통계는 전부 파일로.
#   사용자 화면 복붙 요청 절대 안 함.
#
# [경로규칙] 이 스크립트는 D:\ML\verify\<zip명>\ 하위폴더에서 실행.
#   데이터는 상위 D:\ML\verify\ 에 있음 -> 상대경로 .. 로 탐색.
#   결과 거래 CSV는 하위폴더(이 폴더)에 저장. 분석 txt/INDEX는 check.py가 ..\00WorkHstr\ 로.
#
# [함수 In/Out]
#   find_data()             -> 상위폴더의 Merged_Data_with_Regime_Features.csv 경로
#   load_data(path)         -> tz벗긴 OHLC+feat_struct_8 DataFrame
#   entry_gate(...)         -> dict(pass/sl_dist/tp_dist/rr/sl_clamped...) (v9 사양)
#   simulate_one(...)       -> 거래 1건 행리스트(REDUCE/CLOSE)
#   run_config(...)         -> config 1개 거래 전체
# ==============================================================================

import os, sys, glob
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)   # D:\ML\verify

sys.path.insert(0, HERE)
from ob_fast import precompute_pivots, nearest_above, nearest_below   # 고속 OB(원본과 동일 정의)

# ---- 보고서 v9 게이트 상수 (추측 없이 그대로) ----
SL_GATE = 0.0032
TP_GATE = 0.0048
RR_MIN = 1.5
SL_CLAMP = 0.0100
TP_CLAMP = 0.01618
BEP_BP = 0.0016          # 본전스탑 16bp
LEVERAGE = 5
COST_NOMINAL = 0.0016    # 왕복 16bp(보고서). fee로 환산해 적용
FUNDING_DAILY = 0.0001
TIMEOUT_MIN = 240        # 4H
OB_W = 5                 # pivot 윈도우(보고서 그리드 {2,5,7} 중 중앙)
OB_N = 3                 # 검색 OB 개수
OB_LOOKBACK = 1440       # OB 스캔용 룩백(분). 속도 위해 24h로 제한
REGIME_COL = 'feat_struct_8'

CONFIGS = [
    ('price', 0.55, 'bepPrice_split55'),
    ('price', 0.60, 'bepPrice_split60'),
    ('lev',   0.55, 'bepLev_split55'),
    ('lev',   0.60, 'bepLev_split60'),
]


def find_data():
    names = ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 가 필요합니다.")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    if REGIME_COL not in head.columns:
        raise KeyError(f"'{REGIME_COL}' 컬럼 없음. 가진 컬럼: {list(head.columns)[:12]}")
    cols.append(REGIME_COL)
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def entry_gate(side, candidate_price, e_idx, hp_idx, lp_idx, high, low):
    """v9 check_entry_gate 사양 그대로. OB는 ob_fast(전체 pivot 1회계산)로 조회. SHORT 전용 경로."""
    res = {'pass': False, 'fail': None, 'sl_dist': None, 'tp_dist': None,
           'rr': None, 'sl_clamped': False, 'sl_price': None, 'tp_price': None}
    # SHORT: TP=아래 지지OB(가격하락 목표), SL=위 저항OB(가격상승 위험)
    tp_ob = nearest_below(candidate_price, e_idx, lp_idx, high, low, OB_W)
    sl_ob = nearest_above(candidate_price, e_idx, hp_idx, high, low, OB_W)

    if tp_ob is None:
        res['fail'] = 'no_tp_ob'; return res
    tp_price = float(tp_ob[0])   # 지지OB top(가까운 쪽) = 1차 타겟
    tp_dist = (candidate_price - tp_price) / candidate_price
    res['tp_price'] = tp_price; res['tp_dist'] = tp_dist

    if sl_ob is None:
        res['fail'] = 'no_sl_ob'; return res
    sl_price = float(sl_ob[0])   # 저항OB top = SL
    sl_dist = (sl_price - candidate_price) / candidate_price
    res['sl_price'] = sl_price; res['sl_dist'] = sl_dist

    if sl_dist < SL_GATE:
        res['fail'] = f'sl_gate({sl_dist*10000:.0f}bp<32)'; return res
    if sl_dist > SL_CLAMP:
        sl_eff = SL_CLAMP; res['sl_clamped'] = True; tp_req = TP_CLAMP
    else:
        sl_eff = sl_dist; tp_req = TP_GATE
    res['sl_dist'] = sl_eff
    if tp_dist < tp_req:
        res['fail'] = f'tp_gate({tp_dist*10000:.0f}bp<{tp_req*10000:.0f})'; return res
    rr = tp_dist / max(sl_eff, 1e-8); res['rr'] = rr
    if rr < RR_MIN:
        res['fail'] = f'rr_gate({rr:.2f}<1.5)'; return res
    res['pass'] = True
    return res


def simulate_one(df, o, h, l, c, idx, e_idx, side, bep_mode, split_ratio, gate):
    """게이트 통과한 진입 1건. 1차OB 도달 분할익절 + 본전스탑 + 4h/무제한. SHORT 기준."""
    entry = c[e_idx]
    sl_price = gate['sl_price']           # 초기 SL = SL OB 엣지
    tp_price = gate['tp_price']           # 1차 OB 타겟
    bep_off = BEP_BP if bep_mode == 'price' else BEP_BP * LEVERAGE
    # SHORT: 본전스탑 = 최초진입가 - 16bp(가격 내려가는 게 이익이므로 stop은 진입가보다 약간 아래로 내려 이익확정)
    #   진입가에서 가격이 내려가면 이익. 본전스탑은 '진입가-off' 위로 가격 오르면 청산 -> 진입가 부근 방어.
    bep_stop = entry * (1 + bep_off) if side == 'long' else entry * (1 - bep_off)
    size = 10000.0 * LEVERAGE
    n = len(c)
    end_idx = min(n, e_idx + 1 + 60*24*120)   # 안전상한 120일
    rows = []
    reduced = False
    stepup_active = False    # 1차OB 도달 = 스텝업 활성(무제한 보유)
    cur_stop = sl_price
    for i in range(e_idx + 1, end_idx):
        # 4H timeout (스텝업 미활성만)
        if (not stepup_active) and (i - e_idx) >= TIMEOUT_MIN:
            _close(rows, entry, c[i], size, idx[e_idx], idx[i], side, reduced, split_ratio, 'timeout_4h')
            return rows
        hi, lo = h[i], l[i]
        # 1차 OB 타겟 도달 (SHORT: 가격이 tp_price 이하로) -> 분할익절 + 스텝업 활성 + 본전스탑
        if (not reduced):
            hit_tp = (lo <= tp_price) if side == 'short' else (hi >= tp_price)
            if hit_tp:
                _reduce(rows, entry, tp_price, size, idx[e_idx], idx[i], side, split_ratio)
                size *= (1.0 - split_ratio)
                reduced = True; stepup_active = True
                cur_stop = bep_stop    # 잔량 본전스탑(최초진입가+16bp)
                continue
        # SL/본전스탑 터치
        if side == 'short':
            stop_hit = hi >= cur_stop
        else:
            stop_hit = lo <= cur_stop
        if stop_hit:
            reason = 'bep_stop' if reduced else 'initial_sl'
            _close(rows, entry, cur_stop, size, idx[e_idx], idx[i], side, reduced, split_ratio, reason)
            return rows
    # 안전상한 도달
    _close(rows, entry, c[end_idx-1], size, idx[e_idx], idx[end_idx-1], side, reduced, split_ratio, 'max_hold')
    return rows


def _reduce(rows, entry, price, size, et, xt, side, split_ratio):
    amt = size * split_ratio
    pnl = (entry - price)/entry if side == 'short' else (price - entry)/entry
    fee = amt * COST_NOMINAL
    rows.append(dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                     연도=et.year, 포지션=f'{side.upper()} ({int(split_ratio*100)}% 익절)',
                     수량=round(amt,2), 청산사유='1차OB 분할익절', 진입가=round(entry,2),
                     청산가=round(price,2), 순수익=round(amt*pnl - fee,2), 구분='REDUCE'))


def _close(rows, entry, price, size, et, xt, side, reduced, split_ratio, reason):
    pnl = (entry - price)/entry if side == 'short' else (price - entry)/entry
    fee = size * COST_NOMINAL
    dur = (xt - et).total_seconds()/86400
    funding = size * FUNDING_DAILY * dur
    tag = f'{side.upper()} (잔량 {int((1-split_ratio)*100)}%)' if reduced else f'{side.upper()} (전량)'
    rows.append(dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                     연도=et.year, 포지션=tag, 수량=round(size,2), 청산사유=reason,
                     진입가=round(entry,2), 청산가=round(price,2),
                     순수익=round(size*pnl - fee - funding,2), 구분='CLOSE'))


def run_config(df, o, h, l, c, idx, down_idx, bep_mode, split_ratio, hp_idx, lp_idx):
    """순차 SHORT: 하락장 봉마다 게이트검사 -> 통과시 진입, 청산까지 보유. 게이트 실패는 기록."""
    n = len(c); trades = []; gate_stats = {'pass':0, 'no_tp_ob':0, 'no_sl_ob':0,
                                            'sl_gate':0, 'tp_gate':0, 'rr_gate':0}
    cur = OB_W + 10
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        e_idx = int(down_idx[dptr])
        if e_idx >= n - 1: break
        gate = entry_gate('short', c[e_idx], e_idx, hp_idx, lp_idx, h, l)
        if gate['pass']:
            gate_stats['pass'] += 1
            rows = simulate_one(df, o, h, l, c, idx, e_idx, 'short', bep_mode, split_ratio, gate)
            trades.extend(rows)
            last_x = pd.to_datetime(rows[-1]['청산시간'])
            x_idx = idx.searchsorted(last_x)
            cur = max(int(x_idx)+1, e_idx+1)
        else:
            key = gate['fail'].split('(')[0]
            gate_stats[key] = gate_stats.get(key, 0) + 1
            cur = e_idx + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return trades, gate_stats


def main():
    print("[Stage1] 게이트+본전스탑+분할익절+4h무제한 — 36개월 하락장 SHORT")
    data = find_data(); print(f"[데이터] {data}")
    df = load_data(data)
    o,h,l,c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
    idx = df.index
    down = (df[REGIME_COL].astype(str) == 'downtrend').values
    down_idx = np.where(down)[0]
    print(f"[로드] {len(df):,}행 하락장 {len(down_idx):,}봉. pivot 1회 계산중...")
    hp_idx, lp_idx = precompute_pivots(h, l, OB_W)
    print(f"[pivot] 고점 {len(hp_idx):,} 저점 {len(lp_idx):,}. config {len(CONFIGS)}개 실행...")

    summary = []
    for bep_mode, split_ratio, tag in CONFIGS:
        trades, gs = run_config(df, o,h,l,c, idx, down_idx, bep_mode, split_ratio, hp_idx, lp_idx)
        # 거래 CSV 저장(하위폴더)
        out_csv = os.path.join(HERE, f"S1_trades_{tag}.csv")
        pd.DataFrame(trades).to_csv(out_csv, index=False, encoding='utf-8-sig')
        # 진입당 집계
        if trades:
            d = pd.DataFrame(trades); g = d.groupby('진입시간')['순수익'].sum()
            net = g.values; pf = net[net>0].sum()/abs(net[net<0].sum()) if (net<0).any() else 9.99
            row = dict(config=tag, bep=bep_mode, split=split_ratio, 진입수=len(g),
                       PF=round(pf,3), 승률=round((net>0).mean()*100,1), 순익=round(net.sum()),
                       게이트통과=gs['pass'], 게이트실패=sum(v for k,v in gs.items() if k!='pass'))
        else:
            row = dict(config=tag, bep=bep_mode, split=split_ratio, 진입수=0, PF=0, 승률=0, 순익=0,
                       게이트통과=gs['pass'], 게이트실패=sum(v for k,v in gs.items() if k!='pass'))
        row.update({f'gate_{k}': v for k, v in gs.items()})
        summary.append(row)
        print(f"  {tag}: 진입{row['진입수']} PF={row['PF']} 순익={row['순익']:,}$ (게이트통과 {gs['pass']})")

    sm = pd.DataFrame(summary)
    sm.to_csv(os.path.join(HERE, "S1_summary.csv"), index=False, encoding='utf-8-sig')
    # 게이트 통계도 별도 파일(분석용)
    print("[저장] S1_trades_*.csv (4개) + S1_summary.csv  — 모든 결과 파일로 저장 완료")
    print("[다음] check.py 가 오염검사 + 분석txt + INDEX 기록을 ..\\00WorkHstr\\ 에 수행")


if __name__ == "__main__":
    main()
