# -*- coding: utf-8 -*-
# [rauto_datafeed.py] ★Rauto 라이브 데이터 교신 — 바이낸스 공개 REST + Dauto CSV 겸용 (세션 260626_02_Rauto2_Sys).
#   책임 = '바이낸스와의 거래데이터 교신'(캡틴 역할분담: 데이터 교신 = Rauto 시스템). 봇은 데이터원 모름.
#   ★공개 엔드포인트만(키 불필요, dauto_collector v1과 동일): /fapi/v1/klines · /ticker/price · /openInterest.
#   ★self-locating(§1): Dauto가 모은 C:\BinanceData CSV가 있으면 그걸 우선(이미 OI·펀딩 포함), 없으면 REST 직접.
#   ★반환 형식 = load_1m과 동일(DatetimeIndex tz-naive UTC, 컬럼 open/high/low/close) → 중앙 d1m에 그대로 append.
#   ★의존성 0(stdlib urllib·csv). 매매·비용 로직 없음(데이터층).
import os
import sys
import csv
import json
import glob
import datetime as dt
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://fapi.binance.com"
SYMBOL = os.environ.get("RAUTO2_SYMBOL", "BTCUSDT")


def _dauto_dir():
    """Dauto CSV 폴더 self-locating: env → C:/D: BinanceData → ★Verify Dauto 미러 → 폴백.
       ★실제 1m CSV가 있는 폴더만 반환(없는 빈 C:\\BinanceData 회피)."""
    env = os.environ.get("RAUTO_DAUTO_DIR") or os.environ.get("BINANCE_DATA_DIR")
    if env and os.path.isdir(env):
        return env
    here_drive = os.path.splitdrive(os.path.abspath(__file__))[0] + "\\"
    cands = ["C:\\BinanceData", "D:\\BinanceData", here_drive + "BinanceData",
             r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"]   # ★PC 로컬 Dauto 백업미러
    for d in cands:
        if os.path.isdir(d) and glob.glob(os.path.join(d, "%s_1m_*.csv" % SYMBOL)):
            return d
    return r"C:\BinanceData"


def http_get(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for k in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rauto2-datafeed"})
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:           # 네트워크/레이트리밋 → 짧게 재시도
            last = e
            import time
            time.sleep(1.0 + k)
    raise last


def fetch_price(symbol=SYMBOL):
    """현재가(최종체결가) float."""
    return float(http_get("/fapi/v1/ticker/price", {"symbol": symbol})["price"])


def fetch_oi(symbol=SYMBOL):
    """현재 미결제약정(OI) float."""
    return float(http_get("/fapi/v1/openInterest", {"symbol": symbol})["openInterest"])


def fetch_klines_1m(limit=500, symbol=SYMBOL):
    """최근 1m 봉 limit개 → [(open_ms, o,h,l,c), ...] (마지막은 진행중 봉일 수 있음). 공개 REST."""
    rows = http_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1m", "limit": int(limit)})
    out = []
    for r in rows:
        out.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return out


def read_dauto_tail(n_rows=2000):
    """Dauto CSV(C:\\BinanceData\\BTCUSDT_1m_*.csv)에서 최근 n행 → [(open_ms,o,h,l,c), ...].
       Dauto가 돌고 있으면 이게 우선(이미 검증된 수집·OI 포함). 없으면 빈 리스트."""
    d = _dauto_dir()
    files = sorted(glob.glob(os.path.join(d, "%s_1m_*.csv" % SYMBOL)))
    if not files:
        return []
    rows = []
    for fp in files[-3:]:                # 최근 3개 일자파일이면 충분(>2000행)
        try:
            with open(fp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        ts = row["ts_utc"]
                        t = dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
                        rows.append((int(t.timestamp() * 1000), float(row["open"]), float(row["high"]),
                                     float(row["low"]), float(row["close"])))
                    except Exception:
                        continue
        except Exception:
            continue
    rows.sort()
    return rows[-n_rows:]


def live_1m_df(limit=500, prefer_dauto=True):
    """라이브 1m → pandas DataFrame(load_1m과 동일: index tz-naive UTC, open/high/low/close).
       Dauto CSV 우선(있으면), 없으면 바이낸스 REST. ★중앙 d1m에 append_1m으로 바로 합칠 수 있음."""
    import pandas as pd
    rows = read_dauto_tail(limit) if prefer_dauto else []
    src = "dauto"
    if not rows:
        rows = fetch_klines_1m(limit)
        src = "binance_rest"
    if not rows:
        return None, src
    idx = pd.to_datetime([r[0] for r in rows], unit="ms")     # tz-naive UTC
    df = pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows],
                       "low": [r[3] for r in rows], "close": [r[4] for r in rows]}, index=idx)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df, src


# ══════════════════════════════════════════════════════════════════════════════
#  운영모드 워밍업 빌더 — '꼭 필요한 기간만 1회 읽고 그 뒤 실시간'(캡틴 2026-06-26)
#  ★oi_zscore_24h 라이브 = 누적OI(oi_sum/openInterest)의 인과 24h 롤링z(1440분·mp720·클립±10).
#    검증: 이 계산이 원본 Merged_Data oi_zscore_24h ≡ REVoi 앵커 +1851.65% 1원단위 재현(룩어헤드0).
# ══════════════════════════════════════════════════════════════════════════════
OI_ROLL_MIN = 1440          # oi_zscore 롤링창(분)=24h
OI_ROLL_MINP = 720          # min_periods(§8 mp720)
OI_CLIP = 10.0              # ±클립


def fetch_klines_1m_range(days, symbol=SYMBOL):
    """최근 days일 1m봉 전체 → [(ms,o,h,l,c),...] (endTime 페이징 1500/콜)."""
    need = int(days * 1440)
    out = []
    end_time = None
    while len(out) < need:
        params = {"symbol": symbol, "interval": "1m", "limit": 1500}
        if end_time:
            params["endTime"] = end_time
        rows = http_get("/fapi/v1/klines", params)
        if not rows:
            break
        batch = [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]
        out = batch + out
        end_time = int(rows[0][0]) - 1
        if len(rows) < 1500:
            break
    # 중복 제거
    seen = {}
    for r in out:
        seen[r[0]] = r
    return [seen[k] for k in sorted(seen)][-need:]


def fetch_oi_hist(days=30, symbol=SYMBOL):
    """누적 OI 5m 이력(최근 30일 한정) → [(ms, sumOpenInterest),...]. 운영 oi_zscore 입력."""
    need = int(days * 288)            # 5m points/day = 288
    out = []
    end_time = None
    while len(out) < need:
        params = {"symbol": symbol, "period": "5m", "limit": 500}
        if end_time:
            params["endTime"] = end_time
        rows = http_get("/futures/data/openInterestHist", params)
        if not rows:
            break
        batch = [(int(r["timestamp"]), float(r["sumOpenInterest"])) for r in rows]
        out = batch + out
        end_time = int(rows[0]["timestamp"]) - 1
        if len(rows) < 500:
            break
    seen = {}
    for r in out:
        seen[r[0]] = r
    return [seen[k] for k in sorted(seen)][-need:]


def fetch_funding_hist(limit=1000, symbol=SYMBOL):
    """실펀딩 8h 이력 → (times[datetime64ns], prefix_sum) = fib_replay_1m.load_funding과 동일 형식."""
    import numpy as np
    import pandas as pd
    rows = http_get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": int(limit)})
    rows = sorted(rows, key=lambda r: int(r["fundingTime"]))
    times = pd.to_datetime([int(r["fundingTime"]) for r in rows], unit="ms").values.astype("datetime64[ns]")
    pref = np.concatenate([[0.0], np.cumsum([float(r["fundingRate"]) for r in rows])])
    return times, pref


def oi_zscore_from_series(oi_1m):
    """★oi_zscore_24h 라이브 계산 = 인과 24h 롤링z(mp720)+클립±10. (검증=앵커 1원단위 재현)"""
    roll = oi_1m.rolling(OI_ROLL_MIN, min_periods=OI_ROLL_MINP)
    z = (oi_1m - roll.mean()) / (roll.std() + 1e-9)
    return z.clip(-OI_CLIP, OI_CLIP)


def build_warmup(days=30, prefer_dauto=True):
    """운영 시작용 d1m(OHLC+oi_zscore_24h) + funding. ★Dauto(과거 OHLC+OI) + 바이낸스klines(최근/갭채움)을
       항상 '합쳐' now까지 커버(Dauto가 stale해도 최근분 보충). OI=Dauto open_interest + 바이낸스hist(30일).
       반환 (d1m, fund, meta)."""
    import numpy as np
    import pandas as pd
    drows, doi = (_read_dauto_full(days) if prefer_dauto else ([], []))
    # 바이낸스 klines(항상 — 완전 OHLC + 최근 보충)
    kl = fetch_klines_1m_range(days)
    bi = pd.to_datetime([k[0] for k in kl], unit="ms")
    ohlc = pd.DataFrame({"open": [k[1] for k in kl], "high": [k[2] for k in kl],
                         "low": [k[3] for k in kl], "close": [k[4] for k in kl]}, index=bi)
    oi = pd.Series(np.nan, index=None, dtype=float)
    src = "binance_rest"
    if drows:                                       # Dauto(미러/실시간) OHLC+OI를 과거쪽에 합침
        src = "dauto+binance"
        di = pd.to_datetime([r[0] for r in drows], unit="ms")
        df_d = pd.DataFrame({"open": [r[1] for r in drows], "high": [r[2] for r in drows],
                             "low": [r[3] for r in drows], "close": [r[4] for r in drows]}, index=di)
        ohlc = pd.concat([df_d, ohlc])              # dauto + binance
        ohlc = ohlc[~ohlc.index.duplicated(keep="first")].sort_index()   # 겹침=dauto 우선
        oi = pd.Series([o for o in doi], index=di)
    ohlc = ohlc.sort_index()
    oi_1m = pd.Series(np.nan, index=ohlc.index)
    if len(oi):
        oi_1m = oi_1m.fillna(oi[~oi.index.duplicated(keep="last")].reindex(ohlc.index))
    try:                                            # 바이낸스 OI hist(5m·최근30일)로 보충
        oih = fetch_oi_hist(min(days, 30))
        if oih:
            oi5 = pd.Series([o[1] for o in oih], index=pd.to_datetime([o[0] for o in oih], unit="ms"))
            oi_1m = oi_1m.fillna(oi5.reindex(ohlc.index, method="ffill"))
    except Exception:
        pass
    oi_1m = oi_1m.ffill().bfill()
    ohlc["oi_zscore_24h"] = oi_zscore_from_series(oi_1m).values
    try:
        fund = fetch_funding_hist()
    except Exception:
        fund = (np.array([], dtype="datetime64[ns]"), np.array([0.0]))
    meta = {"src": src, "rows": len(ohlc), "from": str(ohlc.index[0]), "to": str(ohlc.index[-1]),
            "oi_valid": int(ohlc["oi_zscore_24h"].notna().sum())}
    return ohlc[["open", "high", "low", "close", "oi_zscore_24h"]], fund, meta


def _read_dauto_full(days):
    """Dauto CSV에서 최근 days일 OHLC + open_interest → ([(ms,o,h,l,c),...], [oi,...]). 없으면 ([],[])."""
    import datetime as _dt
    d = _dauto_dir()
    files = sorted(glob.glob(os.path.join(d, "%s_1m_*.csv" % SYMBOL)))
    if not files:
        return [], []
    rows = []
    ois = []
    for fp in files[-(days + 2):]:
        try:
            with open(fp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        t = _dt.datetime.strptime(row["ts_utc"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_dt.timezone.utc)
                        ms = int(t.timestamp() * 1000)
                        rows.append((ms, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
                        ois.append(float(row.get("open_interest") or "nan"))
                    except Exception:
                        continue
        except Exception:
            continue
    order = sorted(range(len(rows)), key=lambda i: rows[i][0])
    rows = [rows[i] for i in order][-days * 1440:]
    ois = [ois[i] for i in order][-days * 1440:]
    return rows, ois


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[rauto_datafeed] 스모크 — Dauto폴더=%s" % _dauto_dir(), flush=True)
    try:
        px = fetch_price()
        print("  현재가 BTCUSDT = %.1f" % px, flush=True)
        kl = fetch_klines_1m(5)
        print("  최근 1m 5봉:", flush=True)
        for k in kl:
            print("   ", dt.datetime.fromtimestamp(k[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                  "O%.1f H%.1f L%.1f C%.1f" % (k[1], k[2], k[3], k[4]), flush=True)
        df, src = live_1m_df(10)
        print("  live_1m_df src=%s rows=%d (마지막 %s)" % (src, len(df), str(df.index[-1])), flush=True)
        print("  → ★데이터 교신 OK", flush=True)
    except Exception as e:
        print("  ✗ 네트워크 실패(인터넷/방화벽 확인): %s" % e, flush=True)
        print("    (모듈 자체는 정상 — AWS/운영서버에선 공개REST 접속 가능)", flush=True)
