# -*- coding: utf-8 -*-
# [tick_slippage_builder.py] 실측 틱 슬리피지 빌더 (백테=Binance Vision 아카이브, 캐싱).
#   ① 봇 손절거래의 '격렬한 1분봉' 이벤트만 추림(수정창 et+7H~, excursion>THRESH).
#   ② 그날 일별 aggTrades zip(Vision) 다운·캐싱 → ±2분 슬라이스.
#   ③ 스톱 발동(가격이 SL 도달)한 첫 틱 = 소액 시장가 실체결가 → 진짜 슬리피지.
#   라이브용 최근분은 REST fapi/v1/aggTrades(fromId 페이지넘김) 별도(이 백테는 Vision 통일).
#   ※손절터치 윈도우는 반드시 진입체결(et+7H)부터 — 진입봉 시작부터 뒤지면 진입전 가격을 갭오인(룩어헤드 버그, 2026-06-18 수정).
import os, sys, io, zipfile
import numpy as np, pandas as pd, requests
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "tick_cache")
os.makedirs(CACHE, exist_ok=True)
VBASE = "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT"


def vision_day(date_str):
    """일별 aggTrades(transact_time[ms], price) 반환. 캐싱."""
    fp = os.path.join(CACHE, f"agg_{date_str}.parquet")
    if os.path.exists(fp):
        return pd.read_parquet(fp)
    url = f"{VBASE}/BTCUSDT-aggTrades-{date_str}.zip"
    r = requests.get(url, timeout=180); r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content)); name = z.namelist()[0]
    head = pd.read_csv(z.open(name), nrows=1, header=None)
    has_hdr = not str(head.iloc[0, 0]).replace('.', '', 1).replace('-', '', 1).isdigit()
    df = pd.read_csv(z.open(name), header=0 if has_hdr else None)
    if has_hdr:
        tc = 'transact_time' if 'transact_time' in df.columns else df.columns[5]
        pc = 'price' if 'price' in df.columns else df.columns[1]
    else:
        tc, pc = 5, 1
    out = pd.DataFrame({'T': df[tc].astype('int64'), 'price': df[pc].astype(float)})
    out.to_parquet(fp); return out


def real_fill(date_str, minute_ts, sl, side):
    """minute_ts ±2분 틱에서 스톱(가격 SL도달) 첫 체결가 반환(소액 시장가)."""
    df = vision_day(date_str)
    lo = int((minute_ts - pd.Timedelta(minutes=2)).value // 10**6)
    hi = int((minute_ts + pd.Timedelta(minutes=3)).value // 10**6)
    w = df[(df['T'] >= lo) & (df['T'] <= hi)].sort_values('T')
    if not len(w): return None, 0
    cross = w[w['price'] <= sl] if side == 1 else w[w['price'] >= sl]
    if not len(cross): return None, len(w)
    return float(cross.iloc[0]['price']), len(w)


def main(top_n=5):
    exec(open(os.path.join(HERE, "worst_trade.py"), encoding="utf-8").read().split('def worst(')[0], globals())
    TF = pd.Timedelta(minutes=E.TF_MIN)
    ev = []
    for t in KT:
        if t['reason'] != 'sl': continue
        seg = m.loc[t['et'] + TF: t['xt'] + TF + pd.Timedelta(minutes=5)]
        hit = seg[seg['low'] <= t['sl']] if t['side'] == 1 else seg[seg['high'] >= t['sl']]
        if not len(hit): continue
        em = hit.iloc[0]; mt = hit.index[0]
        exc = max(0.0, (t['sl'] - float(em['low'])) / t['ep'] if t['side'] == 1 else (float(em['high']) - t['sl']) / t['ep'])
        ev.append(dict(et=t['et'], mt=mt, ep=t['ep'], sl=t['sl'], side=t['side'], exc_bp=exc * 1e4))
    ev.sort(key=lambda x: -x['exc_bp'])
    print(f"손절거래 격렬 이벤트(excursion 큰 순) 상위 {top_n}건 — 1분저점 가정 vs 틱 실체결:")
    print(f"{'손절1분봉':>17} {'side':>4} {'SL밀림(1분저점)':>14} {'틱실체결':>12} {'틱수':>6}")
    for e in ev[:top_n]:
        ds = str(e['mt'].date())
        try:
            fill, n = real_fill(ds, e['mt'], e['sl'], e['side'])
        except Exception as ex:
            print(f"{str(e['mt'])[:16]:>17}  다운실패 {ex}"); continue
        bp_min = e['exc_bp']
        if fill is None:
            print(f"{str(e['mt'])[:16]:>17} {e['side']:>4} {bp_min:>12.0f}bp  스톱미발동(틱{n})"); continue
        slip_real = (e['side'] * (e['sl'] - fill) / e['ep']) * -1e4  # 불리>0 (체결이 SL보다 더 불리한 정도)
        print(f"{str(e['mt'])[:16]:>17} {e['side']:>4} {bp_min:>12.0f}bp {slip_real:>+10.0f}bp {n:>6}")
    print("\n(SL밀림=1분 저점까지 갔다 가정(보수상한). 틱실체결=소액 시장가가 실제 닿은 가격. 둘 차이가 내가 과대평가한 부분)")


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
