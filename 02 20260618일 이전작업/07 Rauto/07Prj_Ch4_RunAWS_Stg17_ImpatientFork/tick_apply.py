# -*- coding: utf-8 -*-
# [tick_apply.py] 검증봇 손절 이벤트에 실측 틱 슬리피지 적용.
#   PhaseA(다운無): 각 손절의 SL터치 1분봉 excursion(스톱 초과거리) 측정 → 격렬 이벤트 식별.
#   PhaseB(Vision): 격렬건만 일별 틱 받아 '스톱 도달 첫 체결가' = 소액 시장가 실체결 → 진짜 슬립.
#   정상건(excursion 작음)은 스톱±5bp로 충분(measure_slippage: 진입/청산 슬립 ~0 검증).
import os, sys, io, zipfile
import numpy as np, pandas as pd, requests
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "tick_cache")
os.makedirs(CACHE, exist_ok=True)
TF = pd.Timedelta(hours=7)
M = pd.read_csv(r"D:\ML\Verify\Merged_Data.csv", usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close'))
M['timestamp'] = pd.to_datetime(M['timestamp'], utc=True).dt.tz_convert(None); M = M.set_index('timestamp').sort_index()


def sl_touch_minute(r):
    """손절 SL터치 1분봉(시각, 그 봉) 반환."""
    stop = r['exit_px']; side = r['side']
    if r['reason'] == 'sl_intrabar':
        mt = pd.Timestamp(r['exit_t'])
        if mt in M.index: return mt, M.loc[mt]
    seg = M.loc[pd.Timestamp(r['exit_t']): pd.Timestamp(r['exit_t']) + TF + pd.Timedelta(minutes=5)]
    hit = seg[seg['low'] <= stop] if side == 1 else seg[seg['high'] >= stop]
    if len(hit): return hit.index[0], hit.iloc[0]
    seg2 = M.loc[pd.Timestamp(r['entry_t']) + TF: pd.Timestamp(r['exit_t']) + TF]
    hit2 = seg2[seg2['low'] <= stop] if side == 1 else seg2[seg2['high'] >= stop]
    if len(hit2): return hit2.index[0], hit2.iloc[0]
    return None, None


def phaseA(led, nm):
    sl = led[led['reason'].isin(['sl', 'sl_intrabar'])].copy()
    exc = []
    for _, r in sl.iterrows():
        mt, bar = sl_touch_minute(r)
        if bar is None: exc.append(np.nan); continue
        e = (r['exit_px'] - float(bar['low'])) / r['entry_px'] if r['side'] == 1 else (float(bar['high']) - r['exit_px']) / r['entry_px']
        exc.append(max(0.0, e) * 1e4)
    sl['exc_bp'] = exc
    v = sl['exc_bp'].dropna().values
    print(f"[{nm}] 손절 {len(sl)}건 | excursion(bp): 중앙{np.median(v):.0f} 90%{np.percentile(v,90):.0f} 최악{v.max():.0f}")
    for th in (20, 50, 100):
        print(f"    >{th}bp: {int((v>th).sum())}건 ({np.unique([str(sl_touch_minute(r)[0].date()) for _,r in sl[sl['exc_bp']>th].iterrows() if sl_touch_minute(r)[0] is not None]).size}일)")
    return sl


VBASE = "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT"
def vision_day(date_str):
    fp = os.path.join(CACHE, f"agg_{date_str}.parquet")
    if os.path.exists(fp): return pd.read_parquet(fp)
    r = requests.get(f"{VBASE}/BTCUSDT-aggTrades-{date_str}.zip", timeout=180); r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content)); name = z.namelist()[0]
    head = pd.read_csv(z.open(name), nrows=1, header=None)
    hh = not str(head.iloc[0, 0]).replace('.', '', 1).replace('-', '', 1).isdigit()
    dfv = pd.read_csv(z.open(name), header=0 if hh else None)
    tc = 'transact_time' if hh and 'transact_time' in dfv.columns else (5 if not hh else dfv.columns[5])
    pc = 'price' if hh and 'price' in dfv.columns else (1 if not hh else dfv.columns[1])
    out = pd.DataFrame({'T': dfv[tc].astype('int64'), 'price': dfv[pc].astype(float)})
    out.to_parquet(fp); return out


def real_fill(mt, stop, side):
    df = vision_day(str(mt.date()))
    lo = int((mt - pd.Timedelta(minutes=1)).value // 10**6); hi = int((mt + pd.Timedelta(minutes=2)).value // 10**6)
    w = df[(df['T'] >= lo) & (df['T'] <= hi)].sort_values('T')
    cross = w[w['price'] <= stop] if side == 1 else w[w['price'] >= stop]
    return float(cross.iloc[0]['price']) if len(cross) else None


def phaseB(topn=25):
    rows = []
    for nm in ("king", "imp_pinned"):
        led = pd.read_csv(os.path.join(HERE, f"led36_{nm}.csv"), parse_dates=['entry_t', 'exit_t'])
        sl = phaseA(led, nm)
        sl['bot'] = nm; rows.append(sl)
    allsl = pd.concat(rows).sort_values('exc_bp', ascending=False)
    top = allsl.head(topn)
    print(f"\n=== PhaseB: 상위 {topn} 격렬손절 실체결(Vision 틱) ===")
    print(f"{'봇':>10} {'손절1분봉':>16} {'1분excur':>8} {'틱실슬립':>8}")
    real_bps = []
    for _, r in top.iterrows():
        mt, bar = sl_touch_minute(r)
        if mt is None: continue
        try:
            fill = real_fill(mt, r['exit_px'], r['side'])
        except Exception as e:
            print(f"{r['bot']:>10} {str(mt)[:16]:>16}  다운실패{e}"); continue
        if fill is None:
            print(f"{r['bot']:>10} {str(mt)[:16]:>16} {r['exc_bp']:>7.0f}b  미발동"); continue
        rs = (r['exit_px'] - fill) / r['entry_px'] if r['side'] == 1 else (fill - r['exit_px']) / r['entry_px']
        rs_bp = max(0.0, rs) * 1e4; real_bps.append(rs_bp)
        print(f"{r['bot']:>10} {str(mt)[:16]:>16} {r['exc_bp']:>7.0f}b {rs_bp:>7.0f}b")
    if real_bps:
        rb = np.array(real_bps)
        print(f"\n실측 스톱슬립(상위격렬): 중앙{np.median(rb):.0f}bp 평균{rb.mean():.0f}bp 최악{rb.max():.0f}bp")
        print(f"→ 1분 excursion(상한)은 평균 {top['exc_bp'].head(len(rb)).mean():.0f}bp인데 실제 체결은 평균 {rb.mean():.0f}bp")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "B":
        phaseB(int(sys.argv[2]) if len(sys.argv) > 2 else 25)
    else:
        for nm in ("king", "imp_pinned"):
            led = pd.read_csv(os.path.join(HERE, f"led36_{nm}.csv"), parse_dates=['entry_t', 'exit_t'])
            phaseA(led, nm)
        print("\nPhaseA 완료.")
