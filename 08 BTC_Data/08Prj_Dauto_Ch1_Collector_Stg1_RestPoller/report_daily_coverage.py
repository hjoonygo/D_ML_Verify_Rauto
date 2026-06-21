# -*- coding: utf-8 -*-
# [파일명] report_daily_coverage.py — §5 보고 보조: 일자별 행수/oi_src 분해 표 + 그래프(영문 라벨)
# In: C:\BinanceData\BTCUSDT_1m_*.csv -> Out: daily_coverage.csv + dauto_v1_daily_coverage.png + na 행 범위 출력
import os, sys, csv
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\BinanceData"
days, na_rows = [], []
for f in sorted(os.listdir(ROOT)):
    if not (f.startswith("BTCUSDT_1m_") and f.endswith(".csv")):
        continue
    cnt = {"live": 0, "hist": 0, "na": 0}
    with open(os.path.join(ROOT, f), "r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cnt[r.get("oi_src", "na")] = cnt.get(r.get("oi_src", "na"), 0) + 1
            if r.get("oi_src") == "na":
                na_rows.append(r["ts_utc"])
    days.append((f[12:20], cnt["live"], cnt["hist"], cnt["na"]))

with open(os.path.join(HERE, "daily_coverage.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh); w.writerow(["day", "live", "hist", "na", "total"])
    for d, lv, hs, na in days:
        w.writerow([d, lv, hs, na, lv + hs + na])

labels = [d[0][4:] for d in days]
lv = [d[1] for d in days]; hs = [d[2] for d in days]; na = [d[3] for d in days]
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.bar(labels, hs, label="hist (backfill 5m ffill)", color="#4878cf")
ax.bar(labels, lv, bottom=hs, label="live (real-time poll)", color="#6acc65")
ax.bar(labels, na, bottom=[a + b for a, b in zip(hs, lv)], label="na (unrecoverable)", color="#d65f5f")
ax.axhline(1440, color="gray", ls="--", lw=1, label="1440 = full day")
ax.set_title("Dauto Collector v1 — Daily 1m Row Coverage by OI Source (UTC)")
ax.set_xlabel("Date (MMDD, 2026)"); ax.set_ylabel("Rows per day")
ax.legend(loc="lower right", fontsize=8)
plt.xticks(rotation=60, fontsize=7); plt.tight_layout()
plt.savefig(os.path.join(HERE, "dauto_v1_daily_coverage.png"), dpi=120)

total = sum(l + h + n for _, l, h, n in days)
print(f"days={len(days)} total_rows={total} live={sum(lv)} hist={sum(hs)} na={sum(na)}")
if na_rows:
    print(f"na_range={na_rows[0]} ~ {na_rows[-1]} ({len(na_rows)}rows)")
full_days = [d for d in days if d[1] + d[2] + d[3] == 1440]
print(f"full_1440_days={len(full_days)}/{len(days)} (first/last day partial by design)")
