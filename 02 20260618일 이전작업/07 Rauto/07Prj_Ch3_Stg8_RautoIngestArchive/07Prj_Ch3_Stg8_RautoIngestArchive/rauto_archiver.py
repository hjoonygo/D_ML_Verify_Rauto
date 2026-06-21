# [파일명] rauto_archiver.py
# 코드길이: 약 120줄 / 내부버전: rauto_archiver_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 수집된 오더플로우/캔들 레코드를 스트림별로 버퍼 → 압축 parquet 파일로 롤링 저장하고,
#        1주(기본) 보존정책으로 오래된 파일을 정리한다. (요구사항 2: 백업·향후분석용)
#        파일명에 날짜를 넣어(스트림/스트림_YYYYMMDD_HHMMSS_micro.parquet) 보존정리를 단순화.
#        pyarrow 없으면 gzip CSV로 폴백(어디서든 동작).
# [Lookahead] 해당 없음(저장만).
# ── 사용 파일 ── pandas (+ pyarrow 있으면 parquet, 없으면 .csv.gz)
# ── 함수 In/Out ──
#  Archiver(root,retention_days,fmt)  In: 루트경로·보존일·형식 → Out: 아카이버
#   .add(stream,record)  In: 스트림명·dict → Out: 버퍼 적재
#   .flush()             In: -            → Out: {stream:기록행수} (버퍼→파일)
#   .prune(now)          In: 기준시각(옵션) → Out: 삭제 파일수 (보존기간 초과분 제거)
#   .stats()             In: -            → Out: {stream:{files,rows}}
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import os
import glob
import gzip
import csv
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

try:
    import pyarrow  # noqa: F401
    _PARQUET = True
except Exception:
    _PARQUET = False


class Archiver:
    def __init__(self, root: str, retention_days: int = 7, fmt: str = 'auto'):
        self.root = root
        self.retention_days = retention_days
        self.use_parquet = (fmt == 'parquet') or (fmt == 'auto' and _PARQUET)
        self.ext = 'parquet' if self.use_parquet else 'csv.gz'
        self._buf = defaultdict(list)
        os.makedirs(root, exist_ok=True)

    def add(self, stream: str, record: dict):
        self._buf[stream].append(record)

    def _write(self, stream: str, recs: list) -> str:
        d = os.path.join(self.root, stream)
        os.makedirs(d, exist_ok=True)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        path = os.path.join(d, f"{stream}_{ts}.{self.ext}")
        df = pd.DataFrame(recs)
        if self.use_parquet:
            df.to_parquet(path, index=False)
        else:
            with gzip.open(path, 'wt', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(df.columns))
                w.writeheader()
                for r in recs:
                    w.writerow(r)
        return path

    def flush(self) -> dict:
        out = {}
        for stream, recs in list(self._buf.items()):
            if not recs:
                continue
            self._write(stream, recs)
            out[stream] = len(recs)
            self._buf[stream] = []
        return out

    def _file_date(self, fname: str):
        # 스트림_YYYYMMDD_HHMMSS_micro.ext → YYYYMMDD 추출
        base = os.path.basename(fname)
        parts = base.split('_')
        for p in parts:
            if len(p) == 8 and p.isdigit():
                try:
                    return datetime.strptime(p, '%Y%m%d')
                except ValueError:
                    pass
        return None

    def prune(self, now: datetime = None) -> int:
        now = now or datetime.utcnow()
        cutoff = now - timedelta(days=self.retention_days)
        deleted = 0
        for path in glob.glob(os.path.join(self.root, '*', '*.*')):
            d = self._file_date(path)
            if d is not None and d < cutoff:
                try:
                    os.remove(path)
                    deleted += 1
                except OSError:
                    pass
        return deleted

    def stats(self) -> dict:
        out = {}
        for d in sorted(glob.glob(os.path.join(self.root, '*'))):
            if not os.path.isdir(d):
                continue
            stream = os.path.basename(d)
            files = glob.glob(os.path.join(d, f'*.{self.ext}'))
            rows = 0
            for fp in files:
                try:
                    rows += len(pd.read_parquet(fp)) if self.use_parquet else sum(1 for _ in gzip.open(fp, 'rt')) - 1
                except Exception:
                    pass
            out[stream] = {"files": len(files), "rows": rows}
        return out
