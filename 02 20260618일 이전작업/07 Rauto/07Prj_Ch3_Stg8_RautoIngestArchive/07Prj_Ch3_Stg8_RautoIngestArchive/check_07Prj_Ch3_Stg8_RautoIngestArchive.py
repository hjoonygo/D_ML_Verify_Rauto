# [파일명] check_07Prj_Ch3_Stg8_RautoIngestArchive.py
# 코드길이: 약 150줄 / 내부버전: stg8_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 라이브 수집·아카이브 로직을 12개 시나리오로 검증(모의 피드).
#        수집/정규화, 호가 시퀀스 동기화·갭 감지·재동기화, REST 폴링, parquet 아카이브·라운드트립,
#        1주 보존정리, WS URL 구성. (실 Binance 접속은 PC/AWS에서 검증)
# [Lookahead] 해당 없음.
# ── 사용 파일 ── rauto_ingest / rauto_orderbook / rauto_archiver / mock_feed
#  OUT(../00WorkHstr) <YYYYMMDDHHMM>.txt + 00WorkHstr_INDEX.txt(append)
# ── 함수 In/Out ── approx(a,b) / main(): 12 시나리오 PASS/FAIL + 기록
# ── 상수 ── ROOT / OUT_DIR
# ─────────────────────────────────────────────────────────────────────────
import os, shutil, glob, json
from datetime import datetime
import pandas as pd
from rauto_ingest import IngestService, RestPoller, normalize_kline, normalize_force
import mock_feed as M

BASE = "07Prj_Ch3_Stg8_RautoIngestArchive"
ROOT = "./_ingest_archive_chk"
OUT_DIR = os.path.join('..', '00WorkHstr')


def approx(a, b, t=1e-6):
    try:
        return abs(float(a) - float(b)) <= t
    except (TypeError, ValueError):
        return False


def main():
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    svc = IngestService(ROOT, retention_days=7)
    snap, raws, gap_idx = M.build_sequence()
    svc.set_book_snapshot(snap)

    # 정상 구간 주입(갭 직전까지)
    svc.feed_mock(raws[:gap_idx])
    c = svc.counts
    s1 = (c["kline_1m"] == 2)
    s2 = (c["agg_trade"] == 2)
    s3 = (c["liquidation"] == 1)
    s4 = (svc.book.synced is True)
    s7 = approx(svc.book.mid(), 50007.5)        # 50000 / 50015 → mid 50007.5

    # 정규화 키 점검(샘플)
    kr = normalize_kline(json.loads(raws[0])["data"])
    norm_ok = all(k in kr for k in ("ts_open", "ts_close", "o", "h", "l", "c", "v", "closed"))

    # 갭 주입 → 재동기화 필요
    before = svc.resyncs
    svc.feed_mock(raws[gap_idx:])
    s5 = (svc.resyncs == before + 1 and svc.book.need_resync is True and svc.book.synced is False and c["depth"] == 3)

    # 재동기화(스냅샷 재요청)
    svc.set_book_snapshot(M.snapshot(2000, bids=[(50000, 1.0)], asks=[(50010, 1.0)]))
    s6 = (svc.book.need_resync is False and svc.book.status()["last_update_id"] == 2000)

    # REST 폴링
    poller = RestPoller(svc.archiver,
                        fetch_oi=lambda: M.fake_oi(123456.7, 1_700_000_100_000),
                        fetch_lsr=lambda: M.fake_lsr(1.85, 1_700_000_100_000))
    poller.poll_oi_once(); poller.poll_lsr_once()
    s8 = (poller.n_oi == 1)
    s9 = (poller.n_lsr == 1)

    # flush → parquet 파일·행수
    flushed = svc.flush_archive()
    stats = svc.archiver.stats()
    s10 = (stats.get("kline_1m", {}).get("rows") == 2 and stats.get("agg_trade", {}).get("rows") == 2
           and stats.get("liquidation", {}).get("rows") == 1 and stats.get("depth", {}).get("rows") == 3
           and stats.get("oi", {}).get("rows") == 1 and stats.get("lsr", {}).get("rows") == 1)

    # parquet 라운드트립(liquidation)
    lf = glob.glob(os.path.join(ROOT, 'liquidation', '*.parquet'))
    rt_ok = False
    if lf:
        df = pd.read_parquet(lf[0])
        rt_ok = (len(df) == 1 and approx(df.iloc[0]["price"], 49980) and df.iloc[0]["side"] == "SELL")
    s11 = rt_ok

    # 보존정리: 오래된 파일 제거 / 최근 유지
    old_dir = os.path.join(ROOT, 'depth'); os.makedirs(old_dir, exist_ok=True)
    pd.DataFrame([{"x": 1}]).to_parquet(os.path.join(old_dir, 'depth_20200101_000000_000000.parquet'), index=False)
    recent_before = len(glob.glob(os.path.join(old_dir, '*.parquet')))
    deleted = svc.archiver.prune()
    recent_after = len(glob.glob(os.path.join(old_dir, '*.parquet')))
    s12 = (deleted == 1 and recent_after == recent_before - 1)

    # WS URL 구성
    url = svc.ws.url()
    url_ok = all(x in url for x in ["kline_1m", "forceOrder", "depth", "aggTrade"])

    checks = [
        ("S1 캔들(@kline_1m) 수집·정규화", s1 and norm_ok),
        ("S2 틱(@aggTrade) 수집", s2),
        ("S3 청산(@forceOrder) 수집", s3),
        ("S4 호가 스냅샷+증분 동기화", s4),
        ("S5 호가 갭(pu 불일치) 감지·재동기화필요", s5),
        ("S6 스냅샷 재요청 재동기화", s6),
        ("S7 호가 mid 정확(50007.5)", s7),
        ("S8 REST OI 폴링", s8),
        ("S9 REST 롱숏비율 폴링", s9),
        ("S10 parquet 아카이브 행수 일치", s10),
        ("S11 parquet 라운드트립 무결성", s11),
        ("S12 1주 보존정리(오래된 삭제/최근 유지)", s12),
    ]
    n_pass = sum(1 for _, ok in checks if ok)
    all_ok = (n_pass == len(checks))

    print(f"=== {BASE} 검증 ({n_pass}/{len(checks)} PASS) ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"수집 counts={svc.counts} resyncs={svc.resyncs} 아카이브={ {k: v['rows'] for k, v in stats.items()} }")
    print(f"WS URL ok={url_ok} : {url}")
    print(f"종합: {'PASS ✅ 전 시나리오 통과(로직). 실접속은 PC/AWS 검증.' if all_ok else 'FAIL ⚠️ 미통과 항목 확인'}")

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M')
        with open(os.path.join(OUT_DIR, f'{ts}.txt'), 'w', encoding='utf-8') as f:
            f.write(f"[{BASE}] 라이브 수집·아카이브 검증(모의 피드)\n")
            f.write(f"수집 counts={svc.counts} resyncs={svc.resyncs}\n")
            f.write(f"아카이브 rows={ {k: v['rows'] for k, v in stats.items()} }\n")
            f.write(f"WS URL={url}\n\n")
            for name, ok in checks:
                f.write(f"  [{'PASS' if ok else 'FAIL'}] {name}\n")
            f.write(f"\n종합: {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} (로직). 실 Binance 접속은 PC/AWS 검증(컨테이너 403).\n")
        with open(os.path.join(OUT_DIR, '00WorkHstr_INDEX.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {BASE} | {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} | "
                    f"수집 kline/liq/trade/depth+OI/LSR · 호가시퀀스(U/u/pu)갭·재동기화 · parquet 1주보존 | "
                    f"실접속은 PC/AWS 검증(컨테이너 Binance 차단)\n")
        print(f"[기록] ../00WorkHstr/{ts}.txt + INDEX append")
    except Exception as e:
        print(f"[기록 실패] {e}")


if __name__ == '__main__':
    main()
