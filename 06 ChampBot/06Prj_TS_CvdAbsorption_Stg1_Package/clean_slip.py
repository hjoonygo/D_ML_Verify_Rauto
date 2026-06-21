# -*- coding: utf-8 -*-
# [clean_slip.py] 정밀 스톱 슬리피지: 트리거(SL) 직전 마지막 틱 → 첫 크로싱 틱 갭 = 진짜 실행 슬립.
#   빌더 real_fill의 window-민감성 보완: 진입체결(et+7H)부터 틱 경로를 따라가 'SL을 위에서 아래로
#   처음 깬' 첫 체결틱을 잡고, 직전 틱(아직 SL 위)과의 갭을 측정 = 시장가 스톱의 실제 미끄러짐.
#   캐시된 Vision 틱(tick_cache) 재사용. §15 gate3: 윈도우는 et+7H(진입체결)부터.
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
sys.path.insert(0, STG17); sys.path.insert(0, os.path.join(STG17, "bots"))
import worst_trade as WT          # KT(king 'sl' 거래), m(1분), E
import tick_slippage_builder as TB  # vision_day(캐시)
import trendstack_signal_engine as E

TF = pd.Timedelta(minutes=E.TF_MIN)
m = WT.m


def sl_touch_minute(t):
    seg = m.loc[t['et'] + TF: t['xt'] + TF + pd.Timedelta(minutes=5)]
    hit = seg[seg['low'] <= t['sl']] if t['side'] == 1 else seg[seg['high'] >= t['sl']]
    return hit.index[0] if len(hit) else None


def precise_fill(day, mt, sl, side):
    """mt-5분~+5분 틱에서 'SL 위→아래 첫 크로싱' 틱과 직전틱(SL 위) 반환."""
    df = TB.vision_day(day)
    lo = int((mt - pd.Timedelta(minutes=5)).value // 10**6)
    hi = int((mt + pd.Timedelta(minutes=5)).value // 10**6)
    w = df[(df['T'] >= lo) & (df['T'] <= hi)].sort_values('T').reset_index(drop=True)
    if len(w) < 2: return None
    px = w['price'].values
    crossed = (px <= sl) if side == 1 else (px >= sl)
    # 위에서 아래로 첫 크로싱: 직전 틱은 SL 반대편(아직 안전)
    for k in range(1, len(px)):
        if crossed[k] and not crossed[k-1]:
            return dict(prev=float(px[k-1]), fill=float(px[k]), n=len(w), kidx=k)
    # 윈도우 시작부터 이미 깨져있으면(갭오픈) 첫 틱을 fill로(보수)
    if crossed[0]:
        return dict(prev=float('nan'), fill=float(px[0]), n=len(w), kidx=0, gapopen=True)
    return None


def main():
    ev = [t for t in WT.KT if t['reason'] == 'sl' and t['exc'] > 0]
    ev.sort(key=lambda x: -x['exc'])
    print(f"\n=== 정밀 스톱 슬리피지 (king 'sl' 거래, excursion 상위) ===")
    print(f"{'SL터치(분)':>17} {'side':>4} {'1분극단갭':>9} {'트리거→첫체결':>13} {'직전틱→체결':>11} {'갭오픈':>6} {'틱수':>7}")
    slips = []
    for t in ev[:12]:
        mt = sl_touch_minute(t)
        if mt is None: continue
        day = str(mt.date()); ep = t['ep']; sl = t['sl']; side = t['side']
        exc_bp = t['exc'] * 1e4
        try:
            r = precise_fill(day, mt, sl, side)
        except Exception as e:
            print(f"{str(mt)[:16]:>17}  다운/측정 실패 {e}"); continue
        if r is None:
            print(f"{str(mt)[:16]:>17} {side:>4} {exc_bp:>8.0f}bp  크로싱없음"); continue
        slip_trig = side * (sl - r['fill']) / ep * 1e4          # SL 대비 첫체결 미끄러짐(불리>0)
        gap = (abs(r['prev'] - r['fill']) / ep * 1e4) if not np.isnan(r.get('prev', np.nan)) else float('nan')
        go = 'Y' if r.get('gapopen') else ''
        slips.append(slip_trig)
        print(f"{str(mt)[:16]:>17} {side:>4} {exc_bp:>8.0f}bp {slip_trig:>+11.0f}bp {gap:>9.0f}bp {go:>6} {r['n']:>7}")
    if slips:
        s = np.array(slips)
        print(f"\n[요약] 트리거→첫체결 슬립(불리bp): 평균 {s.mean():+.0f} / 중앙 {np.median(s):+.0f} / 최대 {s.max():+.0f} / 최소 {s.min():+.0f}")
        print(f"  백테 가정(SL+5bp) 대비: 5bp 초과 건수 {(s>5).sum()}/{len(s)}")
    print("\n(트리거→첫체결=SL을 위에서 처음 깬 첫 실제 체결틱의 SL 대비 미끄러짐 = 진짜 스톱 실행 슬립.")
    print(" 직전틱→체결=그 직전 틱(아직 SL 안전측)과 체결틱 가격차=호가 갭/유동성 공백 크기.)")


if __name__ == "__main__":
    main()
