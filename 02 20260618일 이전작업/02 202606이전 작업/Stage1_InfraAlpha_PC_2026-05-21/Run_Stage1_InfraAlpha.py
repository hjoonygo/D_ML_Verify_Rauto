# -*- coding: utf-8 -*-
# [파일명] Run_Stage1_InfraAlpha.py
# 코드길이: 약 300줄, 내부버전명: v10.0 (Exec혁신1 청산 + 4H제거 + 분할3비율), 로직 축약/생략 없이 전체 출력
#
# [목적]
#   1단계/2단계 검증을 PC에서 100% 자동 실행한다.
#   - 검증된 청산엔진 Exec_Dynamic_TS_PautoV75(혁신1, 수정 없음)을 그대로 import해서 사용
#   - v9가 실제 진입한 거래(trades_obtf_*.csv의 entry 기록)를 그대로 재사용(진입 동결)
#   - 청산만 v9의 3단계 → Exec 혁신1(파동 0.618, 눌림목 기준점 상향)로 교체
#   - 4H 강제청산 제거: SL/피보스탑 터치까지 무제한 홀딩(데이터 끝까지)
#   - 분할익절 3비율(50:50 / 45:55 / 40:60) 비교
#   - 펀딩비 민감도 1회(보수적 0.01%/8h, worst-case 드래그) 별도 산출
#   결과: 콘솔 요약 + Stage1_Summary.txt + Stage1_PerTrade_*.csv
#
# [데이터 출처/전제]
#   - 가격: merged_data.csv (또는 자동탐색 후보). 1분봉. 필요한 컬럼은 open/high/low/close 뿐.
#   - 진입: trades_obtf_15m.csv / _30m.csv / _60m.csv 의 entry_t, side, entry_price (v9 실진입)
#   - PF는 '가격수익(net price return)' 기준 = (청산-진입)/진입 - 비용. 레버리지 무관.
#
# [bp 기반 청산 파라미터 (레버리지 무관)]
#   - TRIGGER_BP = 300bp (추세잠금 발동: 진입가 대비 +300bp 유리 이동)
#   - HARD_SL_BP = 115bp (트리거 전 초기 하드손절)
#   - LOCK_RATIO = 0.618 (파동 잠금비율, 혁신1)
#   - Exec는 ROE 기반이라 leverage=1로 환산: fib_trigger_roe=TRIGGER_BP/100, fib_sl_roe=HARD_SL_BP/100
#     → leverage=1 이면 ROE=가격이동×100 이므로 정확히 300bp/115bp 가격거리로 동작
#
# [함수 In/Out]
#   find_data_file()                         IN: 없음            OUT: 데이터 파일 경로(str)
#   load_price(path)                         IN: 경로            OUT: df(1m OHLC, tz-naive 인덱스)
#   load_entries(tf, data_lo, data_hi)       IN: TF, 데이터범위  OUT: 실진입·범위내 DataFrame
#   simulate_exit(entry_ts, side, entry_price, split, df, ex, params, funding_8h, max_days)
#                                            IN: 한 거래 정보     OUT: dict(net, tp1, final, held_h, reason, reduced)
#   compute_pf(arr)                          IN: net 배열        OUT: PF(float)
#   run_one(tf, df, ex, split, funding_8h)   IN: 설정            OUT: (요약dict, 거래DataFrame)
#   main()                                   IN: 없음            OUT: 파일/콘솔 출력
#
# [실행법] D:\ML\Verify 에 본 파일 + Exec_Dynamic_TS_PautoV75.py + trades_obtf_*.csv + merged_data.csv 를 두고:
#          python Run_Stage1_InfraAlpha.py
# ==============================================================================
import sys, os
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

from Exec_Dynamic_TS_PautoV75 import Exec_Dynamic_TS_PautoV75  # 원본(검증, 손절구멍 있음)
from Exec_v10b_PautoV75 import Exec_v10b_PautoV75              # 패치본(손절구멍 막음)

# ============================================================
# 상수
# ============================================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))

COST = 0.0016                 # 왕복 수수료+슬리피지 (v9와 동일, 현 세팅 유지)
TRIGGER_BP = 0.0300           # 300bp 추세잠금 발동
HARD_SL_BP = 0.0115           # 115bp 초기 하드손절
LOCK_RATIO = 0.618            # 파동 잠금비율(혁신1)

# Exec(ROE기반)을 bp로 환산: leverage=1 → ROE=가격이동×100
PARAMS = {
    'leverage': 1,
    'fib_trigger_roe': TRIGGER_BP * 100.0,   # = 3.0  → 300bp
    'fib_sl_roe': HARD_SL_BP * 100.0,         # = 1.15 → 115bp
    'fib_ext_pct': LOCK_RATIO,
}

SPLITS = [0.50, 0.45, 0.40]           # 1차 익절 비율(앞=OB 1차, 뒤=피보 스텝업 잔량)
FLOOR_BPS = [0.0115, 0.0250, 0.0300]  # 하드손절 바닥 후보(115/250/300bp). OB구조 SL은 250~400bp이므로 비교
TFS = ['15m', '30m', '60m']           # 재사용할 v9 진입세트
ENTERED = {'initial_sl', 'step1_sl', 'step2_sl', 'step3_sl',
           'timeout_4h', 'timeout_step_active', 'reversal_2h'}  # 실진입으로 간주할 exit_reason
MAX_DAYS = 21                          # 한 거래 최대 추적(무제한 홀딩 안전상한)
FUNDING_8H = 0.0001                    # 펀딩 민감도(보수적 0.01%/8h, worst-case 항상 드래그)


# ============================================================
# 데이터 로딩
# ============================================================
def find_data_file():
    """36mo 가격 파일 자동 탐색. 후보를 순서대로 시도."""
    candidates = [
        "merged_data.csv", "Merged_Data.csv",
        "Merged_36mo_With_OI_Funding_REPAIRED_v2.csv",
        "Merged_36mo.csv",
    ]
    for c in candidates:
        p = os.path.join(WORK_DIR, c)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "가격 파일을 찾지 못했습니다. merged_data.csv 를 본 스크립트와 같은 폴더에 두세요.\n"
        f"탐색한 후보: {candidates}")


def load_price(path):
    """1분봉 OHLC만 읽어 tz-naive DatetimeIndex로 정렬 반환(메모리 절약)."""
    print(f"[데이터] 로딩: {os.path.basename(path)} (open/high/low/close만)")
    df = pd.read_csv(path, usecols=['timestamp', 'open', 'high', 'low', 'close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_localize(None)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    print(f"[데이터] 범위 {df.index.min()} ~ {df.index.max()} | 1분봉 {len(df):,}행")
    return df


def load_entries(tf, data_lo, data_hi):
    """trades_obtf_{tf}.csv에서 실진입·데이터범위내 거래만 추출."""
    p = os.path.join(WORK_DIR, f"trades_obtf_{tf}.csv")
    if not os.path.exists(p):
        print(f"[경고] {p} 없음 → {tf} 건너뜀")
        return None
    t = pd.read_csv(p)
    ent = t[t['exit_reason'].isin(ENTERED)].copy()
    ent['et'] = pd.to_datetime(ent['entry_t'], utc=True).dt.tz_localize(None)
    sub = ent[(ent['et'] >= data_lo) & (ent['et'] <= data_hi)].copy()
    sub = sub.dropna(subset=['entry_price'])
    print(f"[진입] {tf}: 실진입 {len(ent)} → 데이터범위내 {len(sub)} (커버 {len(sub)/max(1,len(ent))*100:.0f}%)")
    return sub


# ============================================================
# 청산 시뮬레이션 (검증 Exec 엔진 구동)
# ============================================================
def simulate_exit(entry_ts, side, entry_price, split, df, ex, params, funding_8h, max_days=MAX_DAYS):
    """
    한 거래에 대해 Exec(혁신1) 청산을 1분봉 4틱으로 구동. 4H 캡 없음.
    OUT: dict(net, net_funded, tp1, final, held_h, reason, reduced) 또는 None(데이터 부족)
    """
    pos = 'LONG' if str(side).lower() == 'long' else 'SHORT'
    hist = df.loc[:entry_ts].tail(120)          # 진입 시점 OB 탐지용(미래참조 없음)
    if len(hist) < 10:
        return None
    bs = {'position': pos, 'entry_price': entry_price, 'remaining_pct': 1.0,
          'target_idx': 0, 'ob_initialized': False,
          'fib_wave_start': entry_price, 'fib_extreme': entry_price,
          'pulled_back': False, 'fib_stop': None,
          'bullish_obs': [], 'bearish_obs': [], 'df_1m': hist}
    path = df.loc[entry_ts: entry_ts + pd.Timedelta(days=max_days)]
    if len(path) < 2:
        return None

    def roe(px):
        return (px - entry_price) / entry_price if pos == 'LONG' else (entry_price - px) / entry_price

    o_arr = path['open'].values; h_arr = path['high'].values
    l_arr = path['low'].values;  c_arr = path['close'].values
    idx = path.index
    reduced = False; tp1 = None

    for k in range(len(path)):
        o, h, l, c = o_arr[k], h_arr[k], l_arr[k], c_arr[k]
        # 캔들 내부 4틱 경로: 음봉이면 고가 먼저, 양봉이면 저가 먼저(Historical_DataEngine 가정)
        ticks = (o, h, l, c) if c < o else (o, l, h, c)
        for px in ticks:
            sig = ex.check_exit(float(px), bs, params)
            a = sig['action']
            if a in ('REDUCE_LONG', 'REDUCE_SHORT') and not reduced:
                tp1 = roe(float(px)); reduced = True
                bs['remaining_pct'] = round(1.0 - split, 4)   # 1차 익절 후 잔량
            elif a in ('CLOSE_LONG', 'CLOSE_SHORT'):
                fin = roe(float(px))
                held_h = (idx[k] - entry_ts).total_seconds() / 3600.0
                net = (split * tp1 + (1 - split) * fin - COST) if reduced else (fin - COST)
                fund = funding_8h * (held_h / 8.0)            # 보수적 드래그
                return {'net': net, 'net_funded': net - fund, 'tp1': tp1, 'final': fin,
                        'held_h': held_h, 'reason': str(sig['reason'])[:24], 'reduced': reduced}

    # 데이터 끝까지 미청산 → 마지막 종가 청산으로 처리(표본 끝 절단)
    fin = roe(float(c_arr[-1]))
    held_h = (idx[-1] - entry_ts).total_seconds() / 3600.0
    net = (split * tp1 + (1 - split) * fin - COST) if reduced else (fin - COST)
    fund = funding_8h * (held_h / 8.0)
    return {'net': net, 'net_funded': net - fund, 'tp1': tp1, 'final': fin,
            'held_h': held_h, 'reason': 'DATA_END', 'reduced': reduced}


def compute_pf(arr):
    a = np.asarray(arr, dtype=float)
    g = a[a > 0].sum(); l = -a[a < 0].sum()
    return (g / l) if l > 0 else float('inf')


def run_one(tf, df, ex, split, funding_8h, entries, params):
    """한 (TF, split, params) 조합 실행 → (요약dict, 거래DataFrame)."""
    rows = []
    n = len(entries)
    for i, (_, r) in enumerate(entries.iterrows()):
        res = simulate_exit(r['et'], r['side'], float(r['entry_price']), split, df, ex, params, funding_8h)
        if res is None:
            continue
        res['side'] = str(r['side']).lower()
        rows.append(res)
    R = pd.DataFrame(rows)
    if len(R) == 0:
        return None, R
    nets = R['net'].values
    summary = {
        'tf': tf, 'split': f"{int(split*100)}:{int((1-split)*100)}",
        'n': len(R), 'PF': round(compute_pf(nets), 3),
        'sum': round(float(nets.sum()), 4),
        'winrate%': round(float((nets > 0).mean() * 100), 1),
        'PF_funded': round(compute_pf(R['net_funded'].values), 3),
        'sum_funded': round(float(R['net_funded'].sum()), 4),
        'over4h_sum': round(float(R.loc[R['held_h'] > 4, 'net'].sum()), 4),
        'under4h_sum': round(float(R.loc[R['held_h'] <= 4, 'net'].sum()), 4),
        'data_end': int((R['reason'] == 'DATA_END').sum()),
        'max_held_h': round(float(R['held_h'].max()), 0),
    }
    return summary, R


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 72)
    print("[1·2단계] 인프라알파 검증 — Exec 혁신1 청산 + 4H제거 + 분할 3비율")
    print("=" * 72)
    data_path = find_data_file()
    df = load_price(data_path)
    data_lo, data_hi = df.index.min(), df.index.max()

    # 비교 설정: 원본(구멍 있음, 기준) + 패치본 3개 손절바닥(115/250/300bp)
    ex_orig = Exec_Dynamic_TS_PautoV75()
    ex_patch = Exec_v10b_PautoV75()
    configs = [('original_115', ex_orig, 0.0115)]
    for fb in FLOOR_BPS:
        configs.append((f'v10b_{int(fb*1e4)}bp', ex_patch, fb))

    all_summ = []
    for tf in TFS:
        entries = load_entries(tf, data_lo, data_hi)
        if entries is None or len(entries) == 0:
            continue
        base_pf = compute_pf(entries['net_return'].values) if 'net_return' in entries.columns else float('nan')
        print(f"\n--- {tf} | 표본 {len(entries)} | v9 baseline PF={base_pf:.3f} (청산=3단계+4H) ---")
        for cfg_name, ex, floor_bp in configs:
            params = dict(PARAMS)
            params['fib_sl_roe'] = floor_bp * 100.0   # 하드손절/바닥 거리 = floor_bp
            for split in SPLITS:
                summ, R = run_one(tf, df, ex, split, FUNDING_8H, entries, params)
                if summ is None:
                    continue
                summ['engine'] = cfg_name
                summ['floor_bp'] = int(floor_bp * 1e4)
                summ['v9_baseline_PF'] = round(base_pf, 3)
                all_summ.append(summ)
                print(f"   [{cfg_name:>12}] 분할 {summ['split']:>5}  PF={summ['PF']:<5} (펀딩 {summ['PF_funded']}) "
                      f"합 {summ['sum']:+.4f}  승률 {summ['winrate%']}%  "
                      f"4H초과 {summ['over4h_sum']:+.3f}/이하 {summ['under4h_sum']:+.3f}  "
                      f"미청산 {summ['data_end']}  최대보유 {summ['max_held_h']:.0f}h")
                # 각 패치본 40:60 거래상세 저장
                if cfg_name.startswith('v10b') and abs(split - 0.40) < 1e-9:
                    R.to_csv(os.path.join(WORK_DIR, f"Stage1_PerTrade_{tf}_{cfg_name}_4060.csv"),
                             index=False, encoding='utf-8-sig')

    # 요약 저장
    S = pd.DataFrame(all_summ)
    out_csv = os.path.join(WORK_DIR, "Stage1_Summary.csv")
    S.to_csv(out_csv, index=False, encoding='utf-8-sig')

    txt = os.path.join(WORK_DIR, "Stage1_Summary.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("1·2단계 인프라알파 검증 결과\n")
        f.write(f"데이터: {os.path.basename(data_path)} ({data_lo} ~ {data_hi})\n")
        f.write(f"청산: Exec 혁신1(파동 {LOCK_RATIO}) | trigger {TRIGGER_BP*1e4:.0f}bp | hard SL {HARD_SL_BP*1e4:.0f}bp | 4H제거 | 비용 {COST*1e4:.0f}bp\n")
        f.write(f"펀딩 민감도(보수적): {FUNDING_8H*100:.3f}%/8h\n\n")
        f.write(S.to_string(index=False))
        f.write("\n\n해석 가이드:\n")
        f.write(" - PF>1 이면 흑자. v9_baseline_PF(=0.6대 적자)와 비교.\n")
        f.write(" - over4h_sum 이 양(+)이고 under4h_sum 이 음(-)이면, 수익원이 '4H 초과 추세보유'임을 뜻함(4H제거 효과).\n")
        f.write(" - PF_funded 는 며칠 홀딩에 펀딩비를 보수적으로 물렸을 때 값. 본PF와 차이가 작아야 안전.\n")
        f.write(" - data_end>0 이면 데이터 끝 절단 거래가 있다는 뜻(기간 끝부분 진입).\n")

    print("\n" + "=" * 72)
    print(f"[완료] 요약: {out_csv}")
    print(f"        텍스트: {txt}")
    print(f"        거래상세(40:60): Stage1_PerTrade_*_4060.csv")
    print("=" * 72)


if __name__ == "__main__":
    main()
