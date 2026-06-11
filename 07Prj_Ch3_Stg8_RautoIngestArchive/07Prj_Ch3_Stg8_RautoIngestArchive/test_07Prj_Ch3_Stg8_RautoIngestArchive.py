# [파일명] test_07Prj_Ch3_Stg8_RautoIngestArchive.py
# 코드길이: 약 110줄 / 내부버전: stg8_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 라이브 수집·아카이브 '로직'을 모의 피드로 시연한다(Binance 실접속은 PC/AWS에서).
#        합성 WS 메시지(@kline_1m·@forceOrder·@aggTrade·@depth)와 REST OI/롱숏을 흘려
#        정규화→아카이브, 호가 시퀀스 동기화/갭, 보존정리까지 확인.
# [Lookahead] 해당 없음.
# ── 사용 파일 ── rauto_ingest.py / rauto_orderbook.py / rauto_archiver.py / mock_feed.py
#  OUT(cwd) ./_ingest_archive/<stream>/*.parquet  (아카이브 산출)
# ── 함수 In/Out ── main(): 모의 수집→아카이브→폴링→보존정리 시연
# ── 상수 ── ROOT 아카이브 루트
# ─────────────────────────────────────────────────────────────────────────
import os, shutil
import pandas as pd
from rauto_ingest import IngestService, RestPoller
import mock_feed as M

ROOT = "./_ingest_archive"


def main():
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    svc = IngestService(ROOT, retention_days=7)

    snap, raws, gap_idx = M.build_sequence()
    svc.set_book_snapshot(snap)
    print(f"[스냅샷] lastUpdateId={snap['lastUpdateId']} → 호가 {svc.book.status()['bids']}b/{svc.book.status()['asks']}a")

    # 정상 구간(갭 직전까지) 주입
    svc.feed_mock(raws[:gap_idx])
    print(f"[정상 주입] counts={svc.counts} book.synced={svc.book.synced} mid={svc.book.mid()}")

    # 갭 이벤트 주입 → 재동기화 필요
    svc.feed_mock(raws[gap_idx:])
    print(f"[갭 주입] resyncs={svc.resyncs} need_resync={svc.book.need_resync} synced={svc.book.synced}")

    # 스냅샷 재요청(재동기화)
    snap2 = M.snapshot(2000, bids=[(50000, 1.0)], asks=[(50010, 1.0)])
    svc.set_book_snapshot(snap2)
    print(f"[재동기화] need_resync={svc.book.need_resync} last_update_id={svc.book.status()['last_update_id']}")

    # REST 폴링(OI/롱숏) — 가짜 fetch
    poller = RestPoller(svc.archiver,
                        fetch_oi=lambda: M.fake_oi(123456.7, 1_700_000_100_000),
                        fetch_lsr=lambda: M.fake_lsr(1.85, 1_700_000_100_000))
    poller.poll_oi_once(); poller.poll_lsr_once()
    print(f"[REST 폴링] oi={poller.n_oi} lsr={poller.n_lsr}")

    # 아카이브 flush + 통계
    flushed = svc.flush_archive()
    print(f"[flush] {flushed}")
    print(f"[아카이브 통계] {svc.archiver.stats()}")

    # parquet 라운드트립 확인(kline)
    import glob
    kf = glob.glob(os.path.join(ROOT, 'kline_1m', '*.parquet'))
    if kf:
        df = pd.read_parquet(kf[0])
        print(f"[parquet 읽기] kline rows={len(df)} 컬럼={list(df.columns)}")

    # 보존정리: 오래된 파일 1개 심고 prune
    old_dir = os.path.join(ROOT, 'depth'); os.makedirs(old_dir, exist_ok=True)
    old_fp = os.path.join(old_dir, 'depth_20200101_000000_000000.parquet')
    pd.DataFrame([{"x": 1}]).to_parquet(old_fp, index=False)
    deleted = svc.archiver.prune()  # now=utcnow, 보존 7일
    print(f"[보존정리] 삭제 {deleted}건 (오래된 파일 제거, 최근 유지) / 잔존 depth={len(glob.glob(os.path.join(old_dir,'*.parquet')))}")

    print(f"\n[WS URL] {svc.ws.url()}")
    print("[참고] Binance 실접속(start_live)은 PC/AWS에서 검증(컨테이너 403 차단).")


if __name__ == '__main__':
    main()
