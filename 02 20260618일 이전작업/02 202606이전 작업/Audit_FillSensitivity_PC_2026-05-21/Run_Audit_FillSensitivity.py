# -*- coding: utf-8 -*-
# [파일명] Run_Audit_FillSensitivity.py
# 코드길이: 약 150줄, 내부버전명: audit_v1 (체결순서 민감도/미래참조 감사), 로직 축약 없이 전체 출력
#
# [목적] 1·2단계 흑자(PF~1.2)가 '캔들 내부 체결순서 가정'에 얼마나 의존하는지(=미래참조 위험) 측정.
#   같은 진입·같은 청산엔진(Exec_v10b, 300bp)에서 봉 내부 틱 순서만 3가지로 바꿔 PF 비교.
#   - fav  : 포지션에 유리한 극값을 먼저 처리(롱=고가먼저). 추세추종에선 '조기 락인+조기 손절' → 보통 최악 PF
#   - heur : 종가기반(음봉=고가먼저) — 메인 러너가 쓰는 가정
#   - adv  : 불리한 극값을 먼저 처리(롱=저가먼저)
#   세 값의 폭이 좁고 모두 1을 넘으면 견고. fav가 1 아래면 → 흑자가 체결가정에 의존(주의).
#
# [전제] 미래참조 아님: 세 모드 모두 '그 봉의 OHLC'만 쓰며 미래 봉을 안 봄. OB 탐지도 진입봉-3까지의 과거만 사용.
#   이 테스트는 '봉 안에서 어느 극값이 먼저 닿았는지 모른다'는 불확실성의 영향만 잰다.
#
# [함수 In/Out]
#   ticks_for(o,h,l,c,side,mode) -> tuple   : 봉 내부 4틱 순서 생성
#   sim(entry_ts,side,entry_price,split,mode)-> float|None : 한 거래 net
#   main() : 결과 콘솔 + Audit_FillSensitivity.csv
#
# [실행] D:\ML\Verify 에 본 파일 + Exec_v10b_PautoV75.py + trades_obtf_*.csv + merged_data.csv 두고:
#        python Run_Audit_FillSensitivity.py
# ==============================================================================
import sys, os
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
from Exec_v10b_PautoV75 import Exec_v10b_PautoV75

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
COST = 0.0016
PARAMS = {'leverage': 1, 'fib_trigger_roe': 3.0, 'fib_sl_roe': 3.0, 'fib_ext_pct': 0.618}  # 300bp floor
SPLIT = 0.40
TFS = ['15m', '30m', '60m']
ENTERED = {'initial_sl', 'step1_sl', 'step2_sl', 'step3_sl',
           'timeout_4h', 'timeout_step_active', 'reversal_2h'}
MAX_DAYS = 21


def find_data_file():
    for c in ["merged_data.csv", "Merged_Data.csv",
              "Merged_36mo_With_OI_Funding_REPAIRED_v2.csv", "Merged_36mo.csv"]:
        p = os.path.join(WORK_DIR, c)
        if os.path.exists(p):
            return p
    raise FileNotFoundError("merged_data.csv 를 같은 폴더에 두세요.")


def ticks_for(o, h, l, c, side, mode):
    if mode == 'heur':
        return (o, h, l, c) if c < o else (o, l, h, c)
    if mode == 'adv':
        return (o, l, h, c) if side == 'long' else (o, h, l, c)
    return (o, h, l, c) if side == 'long' else (o, l, h, c)   # fav


def pf(arr):
    a = np.asarray(arr, float); g = a[a > 0].sum(); l = -a[a < 0].sum()
    return (g / l) if l > 0 else float('inf')


def main():
    print("=" * 64)
    print("[감사] 체결순서 민감도 — 300bp, 40:60 (미래참조 의존성 측정)")
    print("=" * 64)
    path = find_data_file()
    print(f"[데이터] {os.path.basename(path)}")
    df = pd.read_csv(path, usecols=['timestamp', 'open', 'high', 'low', 'close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_localize(None)
    df = df.set_index('timestamp').sort_index()
    df = df[~df.index.duplicated(keep='first')]
    lo, hi = df.index.min(), df.index.max()
    print(f"[데이터] {lo} ~ {hi} | {len(df):,}행")
    ex = Exec_v10b_PautoV75()

    def sim(entry_ts, side, entry_price, mode):
        pos = 'LONG' if side == 'long' else 'SHORT'
        hist = df.loc[:entry_ts].tail(120)
        if len(hist) < 10:
            return None
        bs = {'position': pos, 'entry_price': entry_price, 'remaining_pct': 1.0,
              'target_idx': 0, 'ob_initialized': False, 'fib_wave_start': entry_price,
              'fib_extreme': entry_price, 'pulled_back': False, 'fib_stop': None,
              'bullish_obs': [], 'bearish_obs': [], 'df_1m': hist}
        p = df.loc[entry_ts: entry_ts + pd.Timedelta(days=MAX_DAYS)]
        if len(p) < 2:
            return None

        def roe(px):
            return (px - entry_price) / entry_price if pos == 'LONG' else (entry_price - px) / entry_price
        o = p['open'].values; h = p['high'].values; l = p['low'].values; c = p['close'].values
        red = False; tp1 = None
        for k in range(len(p)):
            for px in ticks_for(o[k], h[k], l[k], c[k], side, mode):
                try:
                    sg = ex.check_exit(float(px), bs, PARAMS)
                except Exception:
                    return None
                a = sg['action']
                if a in ('REDUCE_LONG', 'REDUCE_SHORT') and not red:
                    tp1 = roe(float(px)); red = True; bs['remaining_pct'] = round(1 - SPLIT, 4)
                elif a in ('CLOSE_LONG', 'CLOSE_SHORT'):
                    fin = roe(float(px))
                    return (SPLIT * tp1 + (1 - SPLIT) * fin - COST) if red else (fin - COST)
        fin = roe(float(c[-1]))
        return (SPLIT * tp1 + (1 - SPLIT) * fin - COST) if red else (fin - COST)

    out = []
    print(f"\n{'TF':>4} {'fav(최악?)':>11} {'heur(메인)':>11} {'adv':>9}  판정")
    for tf in TFS:
        t = pd.read_csv(os.path.join(WORK_DIR, f"trades_obtf_{tf}.csv"))
        ent = t[t['exit_reason'].isin(ENTERED)].copy()
        ent['et'] = pd.to_datetime(ent['entry_t'], utc=True).dt.tz_localize(None)
        sub = ent[(ent['et'] >= lo) & (ent['et'] <= hi)].dropna(subset=['entry_price'])
        r = {}
        for mode in ['fav', 'heur', 'adv']:
            nets = [sim(x['et'], str(x['side']).lower(), float(x['entry_price']), mode) for _, x in sub.iterrows()]
            nets = [v for v in nets if v is not None]
            r[mode] = pf(nets)
        worst = min(r.values())
        verdict = "견고(최악도 흑자)" if worst > 1.0 else "주의(최악 시 적자/본전)"
        print(f"{tf:>4} {r['fav']:>11.3f} {r['heur']:>11.3f} {r['adv']:>9.3f}  {verdict}")
        out.append({'tf': tf, 'cover': len(sub), 'PF_fav': round(r['fav'], 3),
                    'PF_heur': round(r['heur'], 3), 'PF_adv': round(r['adv'], 3),
                    'worst': round(worst, 3), 'verdict': verdict})
    pd.DataFrame(out).to_csv(os.path.join(WORK_DIR, "Audit_FillSensitivity.csv"),
                             index=False, encoding='utf-8-sig')
    print("\n해석: fav<heur<adv 이면 메인 결과(heur)는 낙관 아님(오히려 보수쪽).")
    print("      그러나 fav(추세전략 최악 순서)가 1 미만이면 → 흑자가 체결가정에 의존(보수적으론 본전~적자).")
    print(f"\n[완료] Audit_FillSensitivity.csv 저장")


if __name__ == "__main__":
    main()
