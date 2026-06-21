# -*- coding: utf-8 -*-
# [파일명] dauto_collector.py
# 코드길이: 약 380줄 | 내부버전: Dauto_Collector_v1 (08Prj_Dauto_Ch1_Collector_Stg1_RestPoller)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Binance USDT-M 선물 BTCUSDT의 1분 데이터를 '공개 REST'로만 상시 수집해
#   C:\BinanceData\BTCUSDT_1m_YYYYMMDD.csv (UTC, 1분=1행)에 쌓는다.
#   ① 매분 :05초(거래소 서버시각 기준)에 직전 '확정된' 1분봉 + OI스냅샷 + 마크/인덱스/펀딩(현행)을 폴링.
#   ② 시작 시·운전 중 마지막 행과 현재 사이 구멍을 자동 백필:
#      - klines(가격·거래량)·funding(정산이력) = 전기간 복구 가능
#      - open_interest = openInterestHist(5m, 최근 30일만 제공) → 1m 행에 보간없이 forward-fill,
#        출처 플래그 oi_src=hist 명시. 30일 초과 구멍은 복구불가 → INDEX·health에 기록(oi_src=na).
#   ③ 전일 '마감된' CSV를 G드라이브에 1일 1회 복사(드라이브 없으면 자동 스킵 — AWS).
#   ④ 일일 헬스라인(수집행수/구멍수)을 C:\BinanceData\dauto_health.log에 기록.
#   ★read-only: 주문 관련 엔드포인트/코드 없음. API키·시크릿 미사용·미기록.
#
# [★사용명칭 정의]
#   funding_rate_8h(현행) = 라이브 행: premiumIndex.lastFundingRate(다음 정산을 향해 누적 중인 현재값).
#                           백필 행: 그 행이 속한 정산창의 '실제 정산된' 펀딩률(fundingRate 이력).
#                           (정산 전 구간이라 이력이 없으면 직전 정산값 ffill — README 참조)
#   oi_src = live(실시간 스냅샷) / hist(5m 이력 ffill 백필) / na(30일 초과, 복구불가)
#   구멍(gap) = 있어야 할 1분 행이 통째로 없는 것. 백필 행의 mark/index 공란은 '구멍'이 아니라
#               설계상 공백(해당 이력 엔드포인트는 v1 범위 밖 — README '추가 제안' 참조).
#
# [시각 동기] 봉 경계 판정은 Binance 서버시각(/fapi/v1/time) 오프셋 보정으로 수행(1시간마다 재동기).
#             OS 시계 자체의 NTP 동기는 README의 w32tm 절차 참조.
#
# [사용 엔드포인트 — 전부 공개(키 불필요), 분당 평시 3콜(가중치 ~4/2400 = 0.2%)]
#   GET /fapi/v1/time            서버시각          (시작+1h마다)
#   GET /fapi/v1/klines          1m OHLCV+taker    (매분 1콜 / 백필 시 1500봉씩)
#   GET /fapi/v1/openInterest    OI 스냅샷         (매분 1콜)
#   GET /fapi/v1/premiumIndex    마크/인덱스/펀딩  (매분 1콜)
#   GET /fapi/v1/fundingRate     펀딩 정산이력     (백필 시만)
#   GET /futures/data/openInterestHist  OI 5m 이력 (백필 시만, 최근 30일 한정)
#
# [함수 In->Out]
#   http_get(path, params)            경로,파라미터 -> json (재시도5회+지수백오프, 429/418 대기 존중)
#   sync_offset()                     (없음) -> 서버-로컬 ms 오프셋 갱신
#   now_ms()                          (없음) -> 보정된 현재 UTC ms
#   iso(ms) / day_str(ms)             ms -> 'YYYY-MM-DD HH:MM:SS' / 'YYYYMMDD'
#   path_for(ms)                      ms -> 그 날짜의 CSV 경로
#   read_last_open_ms()               (없음) -> 저장된 마지막 행의 봉시작 ms (없으면 None)
#   fetch_klines(a,b)                 ms구간 -> [[openTime,o,h,l,c,vol,takerBuy],...]
#   fetch_funding(a,b)                ms구간 -> [(정산ms, 펀딩률str),...] 오름차순
#   fetch_oi_hist(a,b)                ms구간 -> [(ms, oi_str),...] 5m 오름차순
#   next_funding_ms(ms)               ms -> 다음 8h 정산경계 ms (UTC 00/08/16)
#   backfill(a,b)                     ms구간 -> 구멍 행 생성·저장 (행수, 복구불가행수)
#   live_poll(bar_open_ms)            봉시작ms -> 라이브 1행 저장 (성공 True/False)
#   daily_jobs()                      (없음) -> 자정 후 1회: 전일 헬스라인 + G드라이브 아카이브
#   main()                            상시 루프 (--once = 1회 폴링 출력 후 종료, 저장 안 함)
# ==============================================================================
import os, sys, csv, json, time, shutil, argparse, bisect
import datetime as dt
import urllib.request, urllib.parse, urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE     = "https://fapi.binance.com"
SYMBOL   = "BTCUSDT"
ROOT     = r"C:\BinanceData"
GDRIVE   = "G:\\내 드라이브\\00AI개발지식DB\\자산관리\\유동자산\\자동매매\\08 BTC거래데이터"
INDEX    = r"D:\ML\verify\00WorkHstr\00WorkHstr_INDEX.txt"
STG      = "08Prj_Dauto_Ch1_Collector_Stg1_RestPoller"
HEALTH   = os.path.join(ROOT, "dauto_health.log")

POLL_SEC            = 5        # 매분 :05초 폴링(봉 확정 대기)
FIRST_BACKFILL_DAYS = 30       # 첫 구동(파일 전무) 시 시드 백필 일수 = OI 이력 한도와 동일
OI_HIST_DAYS        = 30       # openInterestHist 제공 한도
RESYNC_SEC          = 3600     # 서버시각 재동기 주기
MIN_MS              = 60_000
H8_MS               = 8 * 3600 * 1000

COLS = ["ts_utc", "open", "high", "low", "close", "volume", "taker_buy_volume",
        "open_interest", "mark_price", "index_price", "funding_rate_8h",
        "next_funding_time", "oi_src"]

_offset_ms = 0
_last_written_ms = None        # 메모리 캐시(매분 파일 재스캔 방지)


def hlog(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}Z | {msg}"
    print(line, flush=True)
    try:
        os.makedirs(ROOT, exist_ok=True)
        with open(HEALTH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def http_get(path, params=None, host=BASE):
    url = host + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last_err = None
    for k in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dauto-collector-v1"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 418):                      # 레이트리밋: 지시 대기 존중
                wait = int(e.headers.get("Retry-After", "30"))
                hlog(f"RATE-LIMIT {e.code} {path} -> {wait}s 대기")
                time.sleep(wait)
            else:
                time.sleep(2 ** k)
        except Exception as e:
            last_err = e
            time.sleep(2 ** k)
    raise RuntimeError(f"http_get 실패 {path}: {last_err}")


def sync_offset():
    global _offset_ms
    t0 = int(time.time() * 1000)
    sv = int(http_get("/fapi/v1/time")["serverTime"])
    t1 = int(time.time() * 1000)
    _offset_ms = sv - (t0 + t1) // 2
    return _offset_ms


def now_ms():
    return int(time.time() * 1000) + _offset_ms


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def day_str(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y%m%d")


def path_for(ms):
    return os.path.join(ROOT, f"{SYMBOL}_1m_{day_str(ms)}.csv")


def parse_ts(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def read_last_open_ms():
    if not os.path.isdir(ROOT):
        return None
    files = sorted(f for f in os.listdir(ROOT) if f.startswith(f"{SYMBOL}_1m_") and f.endswith(".csv"))
    for fname in reversed(files):
        try:
            with open(os.path.join(ROOT, fname), "r", encoding="utf-8") as f:
                last = None
                for line in f:
                    if line.strip():
                        last = line
                if last and not last.startswith("ts_utc"):
                    return parse_ts(last.split(",")[0])
        except Exception as e:
            hlog(f"경고 last행 읽기실패 {fname}: {e}")
    return None


def append_rows(rows):
    # rows = [dict] ts 오름차순. 일자별 파일에 일괄 추가(없으면 헤더부터). 중복 ts 방지.
    global _last_written_ms
    os.makedirs(ROOT, exist_ok=True)
    by_day = {}
    for row in rows:
        ms = parse_ts(row["ts_utc"])
        if _last_written_ms is not None and ms <= _last_written_ms:
            continue
        by_day.setdefault(path_for(ms), []).append(row)
        _last_written_ms = ms
    for p, day_rows in by_day.items():
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if new:
                w.writeheader()
            w.writerows(day_rows)


def fetch_klines(a, b):
    out = []
    cur = a
    while cur <= b:
        ks = http_get("/fapi/v1/klines", {"symbol": SYMBOL, "interval": "1m",
                                          "startTime": cur, "endTime": b, "limit": 1500})
        if not ks:
            break
        for k in ks:
            out.append(k)               # [0]openTime [1]o [2]h [3]l [4]c [5]vol ... [9]takerBuyBase
        cur = ks[-1][0] + MIN_MS
        if len(ks) < 1500:
            break
    return out


def fetch_funding(a, b):
    out = []
    cur = a
    while cur <= b:
        fs = http_get("/fapi/v1/fundingRate", {"symbol": SYMBOL, "startTime": cur,
                                               "endTime": b, "limit": 1000})
        if not fs:
            break
        for x in fs:
            out.append((int(x["fundingTime"]), str(x["fundingRate"])))
        cur = int(fs[-1]["fundingTime"]) + 1
        if len(fs) < 1000:
            break
    out.sort()
    return out


def fetch_oi_hist(a, b):
    # ★openInterestHist는 구간 내 '최신' limit건을 반환(과거→미래 전진 페이지네이션 불가).
    #   500포인트(=2500분) 이하 창으로 쪼개 창마다 전량 수신 → 전기간 누락 없음.
    out = []
    win = 500 * 5 * MIN_MS
    cur = a
    while cur <= b:
        hi = min(cur + win - 1, b)
        os_ = http_get("/futures/data/openInterestHist",
                       {"symbol": SYMBOL, "period": "5m", "startTime": cur,
                        "endTime": hi, "limit": 500})
        for x in (os_ or []):
            out.append((int(x["timestamp"]), str(x["sumOpenInterest"])))
        cur = hi + 1
    out.sort()
    return out


def next_funding_ms(ms):
    return (ms // H8_MS + 1) * H8_MS


def note_unrecoverable(a, b, n):
    msg = f"OI구멍 복구불가(>{OI_HIST_DAYS}d): {iso(a)}~{iso(b)} ({n}행, oi_src=na)"
    hlog("★" + msg)
    try:
        if os.path.exists(INDEX):
            stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
            with open(INDEX, "a", encoding="utf-8") as f:
                f.write(f"{stamp} | {STG} | {msg} | src=dauto_collector\n")
    except Exception as e:
        hlog(f"경고 INDEX 기록실패: {e}")


def backfill(a, b):
    # [a,b] 봉시작 ms 구간(분단위 정렬 가정)의 구멍을 채운다. 반환 (백필행수, 복구불가행수)
    if a > b:
        return 0, 0
    hlog(f"백필 시작 {iso(a)}~{iso(b)} ({(b - a) // MIN_MS + 1}분)")
    ks = fetch_klines(a, b)
    if not ks:
        hlog("백필: klines 0건(거래소 무자료) — 스킵")
        return 0, 0
    fund = fetch_funding(a - H8_MS, b + H8_MS)
    f_times = [t for t, _ in fund]
    oi_cut = now_ms() - OI_HIST_DAYS * 86400_000
    oi_lo = max(a - 15 * MIN_MS, oi_cut)   # 15분 룩백: 직전 5m 포인트 확보(짧은 구멍 ffill용)
    oih = fetch_oi_hist(oi_lo, b) if oi_lo <= b else []
    o_times = [t for t, _ in oih]

    rows, na_n = [], []
    for k in ks:
        ms = int(k[0])
        # 펀딩: 이 행이 속한 정산창의 '정산된' 률(다음 경계의 정산값). 미정산이면 직전 정산값 ffill.
        nf = next_funding_ms(ms)
        j = bisect.bisect_left(f_times, nf)
        if j < len(fund) and f_times[j] == nf:
            fr = fund[j][1]
        else:
            j2 = bisect.bisect_right(f_times, ms) - 1
            fr = fund[j2][1] if j2 >= 0 else ""
        # OI: 5m 이력에서 ms 이하 최근 포인트 ffill(보간 금지)
        i2 = bisect.bisect_right(o_times, ms) - 1
        if i2 >= 0:
            oi, src = oih[i2][1], "hist"
        else:
            oi, src = "", "na"
            na_n.append(ms)
        rows.append({"ts_utc": iso(ms), "open": k[1], "high": k[2], "low": k[3],
                     "close": k[4], "volume": k[5], "taker_buy_volume": k[9],
                     "open_interest": oi, "mark_price": "", "index_price": "",
                     "funding_rate_8h": fr, "next_funding_time": iso(nf), "oi_src": src})
    append_rows(rows)
    if na_n:
        # 진짜 복구불가(30일 초과)만 INDEX 기록. 30일 내 포인트 공백은 --repair-oi로 회수 가능.
        old = [m for m in na_n if m < oi_cut]
        rec = [m for m in na_n if m >= oi_cut]
        if old:
            note_unrecoverable(old[0], old[-1], len(old))
        if rec:
            hlog(f"경고 OI이력 포인트 공백(30일 내, 복구가능): {iso(rec[0])}~{iso(rec[-1])} "
                 f"{len(rec)}행 — python dauto_collector.py --repair-oi 로 회수")
    hlog(f"백필 완료 {len(rows)}행 (복구불가 {len(na_n)}행)")
    return len(rows), len(na_n)


def live_poll(bar_open, write=True):
    ks = http_get("/fapi/v1/klines", {"symbol": SYMBOL, "interval": "1m",
                                      "startTime": bar_open, "endTime": bar_open + MIN_MS - 1, "limit": 1})
    if not ks:
        time.sleep(2)
        ks = http_get("/fapi/v1/klines", {"symbol": SYMBOL, "interval": "1m",
                                          "startTime": bar_open, "endTime": bar_open + MIN_MS - 1, "limit": 1})
        if not ks:
            hlog(f"경고 확정봉 미수신 {iso(bar_open)} — 다음 사이클 백필로 회수")
            return False
    k = ks[0]
    oi = http_get("/fapi/v1/openInterest", {"symbol": SYMBOL})
    pi = http_get("/fapi/v1/premiumIndex", {"symbol": SYMBOL})
    row = {"ts_utc": iso(int(k[0])), "open": k[1], "high": k[2], "low": k[3],
           "close": k[4], "volume": k[5], "taker_buy_volume": k[9],
           "open_interest": str(oi["openInterest"]), "mark_price": str(pi["markPrice"]),
           "index_price": str(pi["indexPrice"]), "funding_rate_8h": str(pi["lastFundingRate"]),
           "next_funding_time": iso(int(pi["nextFundingTime"])), "oi_src": "live"}
    if write:
        append_rows([row])
    else:
        print(json.dumps(row, ensure_ascii=False, indent=1))
    return True


_last_daily_day = None

def daily_jobs():
    # UTC 자정 이후 첫 호출에서 1회: 전일 헬스라인 + G드라이브 아카이브(마감 파일만 — 잠금 회피)
    global _last_daily_day
    today = day_str(now_ms())
    if _last_daily_day == today:
        return
    y_ms = now_ms() - 86400_000
    yday = day_str(y_ms)
    p = path_for(y_ms)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip() and not l.startswith("ts_utc")]
            n = len(lines)
            srcs = [l.rstrip("\n").split(",")[-1] for l in lines]
            gaps = 1440 - n
            hlog(f"HEALTH {yday} | rows={n}/1440 | gaps={gaps} | "
                 f"live={srcs.count('live')} hist={srcs.count('hist')} na={srcs.count('na')}")
        except Exception as e:
            hlog(f"경고 헬스라인 실패 {yday}: {e}")
        if os.path.isdir(GDRIVE):
            try:
                dst = os.path.join(GDRIVE, os.path.basename(p))
                if (not os.path.exists(dst)) or os.path.getsize(dst) != os.path.getsize(p):
                    shutil.copy2(p, dst)
                    hlog(f"아카이브 {os.path.basename(p)} -> G드라이브")
            except Exception as e:
                hlog(f"경고 아카이브 실패: {e}")
        else:
            pass  # AWS 등 G드라이브 없음 — 자동 스킵(에러 아님)
    _last_daily_day = today


def repair_oi():
    # 기존 CSV의 oi_src=na 행 중 30일 내 행을 5m 이력으로 회수(ffill, 보간 금지). 멱등.
    cut = now_ms() - OI_HIST_DAYS * 86400_000
    files = sorted(f for f in os.listdir(ROOT) if f.startswith(f"{SYMBOL}_1m_") and f.endswith(".csv")) \
        if os.path.isdir(ROOT) else []
    total_fix = 0
    for fname in files:
        p = os.path.join(ROOT, fname)
        with open(p, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        nas = [parse_ts(r["ts_utc"]) for r in rows if r.get("oi_src") == "na" and parse_ts(r["ts_utc"]) >= cut]
        if not nas:
            continue
        oih = fetch_oi_hist(max(min(nas) - 15 * MIN_MS, cut), max(nas))
        o_times = [t for t, _ in oih]
        n_fix = 0
        for r in rows:
            if r.get("oi_src") != "na":
                continue
            ms = parse_ts(r["ts_utc"])
            if ms < cut:
                continue
            i2 = bisect.bisect_right(o_times, ms) - 1
            if i2 >= 0:
                r["open_interest"] = oih[i2][1]; r["oi_src"] = "hist"; n_fix += 1
        if n_fix:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                w.writeheader(); w.writerows(rows)
            os.replace(tmp, p)
            total_fix += n_fix
            hlog(f"repair-oi {fname}: na->hist {n_fix}행")
    hlog(f"repair-oi 완료: 총 {total_fix}행 회수")


def main():
    global _last_written_ms
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="1회 폴링 출력 후 종료(저장 안 함, 스모크)")
    ap.add_argument("--repair-oi", action="store_true", help="기존 oi_src=na 행을 30일 내 이력으로 회수 후 종료")
    args = ap.parse_args()

    sync_offset()
    if args.repair_oi:
        repair_oi()
        return
    if args.once:
        bar_open = (now_ms() // MIN_MS) * MIN_MS - MIN_MS
        ok = live_poll(bar_open, write=False)
        print(f"[--once] {'PASS' if ok else 'FAIL'} bar={iso(bar_open)} offset={_offset_ms}ms")
        return

    os.makedirs(ROOT, exist_ok=True)
    hlog(f"STARTUP {STG} | root={ROOT} | offset={_offset_ms}ms | read-only(공개REST)")
    _last_written_ms = read_last_open_ms()
    target = (now_ms() // MIN_MS) * MIN_MS - MIN_MS
    if _last_written_ms is None:
        backfill(((now_ms() - FIRST_BACKFILL_DAYS * 86400_000) // MIN_MS) * MIN_MS, target)
    elif _last_written_ms + MIN_MS <= target:
        backfill(_last_written_ms + MIN_MS, target)

    last_sync = time.time()
    while True:
        nxt = (now_ms() // MIN_MS + 1) * MIN_MS + POLL_SEC * 1000
        time.sleep(max(0.2, (nxt - now_ms()) / 1000))
        bar_open = (now_ms() // MIN_MS) * MIN_MS - MIN_MS
        if _last_written_ms is not None and bar_open > _last_written_ms + MIN_MS:
            backfill(_last_written_ms + MIN_MS, bar_open - MIN_MS)   # 운전 중 구멍(슬립 등) 회수
        if _last_written_ms is None or bar_open > _last_written_ms:
            try:
                live_poll(bar_open)
            except Exception as e:
                hlog(f"경고 폴링 실패 {iso(bar_open)}: {e} — 다음 사이클 백필로 회수")
        daily_jobs()
        if time.time() - last_sync > RESYNC_SEC:
            try:
                sync_offset(); last_sync = time.time()
            except Exception as e:
                hlog(f"경고 시각 재동기 실패: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        hlog("SHUTDOWN (사용자 중단)")
