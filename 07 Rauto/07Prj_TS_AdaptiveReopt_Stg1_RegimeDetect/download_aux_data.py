# -*- coding: utf-8 -*-
# [download_aux_data.py] 2nd봇용 보조데이터 자동수집(Binance Vision, 무료·키불필요).
#   funding rate(BTC/ETH/SOL) + 4H klines(ETH/SOL/BNB). 2021-01~2026-05. 월별 zip 캐싱.
#   캐리(funding) + 페어/멀티심볼(altcoin OHLCV) 봇 검증용. CPCV는 36mo+ 필요→5년 수집.
import os, io, zipfile
import requests, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "aux_data"); os.makedirs(OUT, exist_ok=True)
VB = "https://data.binance.vision/data/futures/um/monthly"
MONTHS = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13)]
MONTHS = [x for x in MONTHS if "2021-01" <= x <= "2026-05"]


def fetch(url):
    r = requests.get(url, timeout=60)
    if r.status_code != 200: return None
    z = zipfile.ZipFile(io.BytesIO(r.content)); return z.read(z.namelist()[0])


def funding(sym):
    rows = []
    for mo in MONTHS:
        try:
            b = fetch(f"{VB}/fundingRate/{sym}/{sym}-fundingRate-{mo}.zip")
            if b is None: continue
            df = pd.read_csv(io.BytesIO(b))
            if df.columns[0] not in ('calc_time', 'fundingTime'):  # 헤더 없는 경우
                df = pd.read_csv(io.BytesIO(b), header=None, names=['calc_time', 'funding_interval', 'last_funding_rate'])
            rows.append(df)
        except Exception as e:
            print(f"  {sym} funding {mo} err {e}")
    if rows:
        out = pd.concat(rows, ignore_index=True); fp = os.path.join(OUT, f"funding_{sym}.csv")
        out.to_csv(fp, index=False); return len(out), fp
    return 0, None


def klines(sym, tf="4h"):
    rows = []; cols = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_vol', 'count', 'taker_buy_vol', 'taker_buy_quote', 'ignore']
    for mo in MONTHS:
        try:
            b = fetch(f"{VB}/klines/{sym}/{tf}/{sym}-{tf}-{mo}.zip")
            if b is None: continue
            df = pd.read_csv(io.BytesIO(b), header=None)
            if df.shape[1] >= 12: df = df.iloc[:, :12]; df.columns = cols
            df = df[pd.to_numeric(df['open_time'], errors='coerce').notna()]  # 헤더행 제거
            df['open_time'] = df['open_time'].astype('int64')
            rows.append(df)
        except Exception as e:
            print(f"  {sym} {tf} {mo} err {e}")
    if rows:
        out = pd.concat(rows, ignore_index=True).drop_duplicates('open_time').sort_values('open_time')
        fp = os.path.join(OUT, f"klines_{sym}_{tf}.csv"); out.to_csv(fp, index=False); return len(out), fp
    return 0, None


if __name__ == "__main__":
    print("=== funding rate ===")
    for s in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
        n, fp = funding(s)
        if n: print(f"  {s}: {n}행 → {os.path.basename(fp)}")
    print("=== 4H klines ===")
    for s in ('ETHUSDT', 'SOLUSDT', 'BNBUSDT'):
        n, fp = klines(s, "4h")
        if n: print(f"  {s}: {n}행 → {os.path.basename(fp)}")
    print("DONE aux data")
