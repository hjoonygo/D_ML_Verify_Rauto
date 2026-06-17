# -*- coding: utf-8 -*-
# [diag_live_vs_backtest.py] 백테 구간 vs 실시간(전방) 구간 성과 분리 진단 — 1회용
#   목적: "백테는 좋은데 배포 후 실시간만 연속 손실" 의구심을 데이터로 검증.
#   읽기: C:\Rauto1\paper_ledger.csv (거래원장) + C:\BinanceData\*.csv (1m 가격 — 국면 판정용)
#   출력: 전 거래표 + 배포경계(06-12 인내 / 06-15 성급) 분리 통계 + 국면(추세/횡보) + 수익집중도.
#   실행: python diag_live_vs_backtest.py
import csv, glob, os, sys
import datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LEDGER = r"C:\Rauto1\paper_ledger.csv"
DATA_GLOB = r"C:\BinanceData\*1m*.csv"
DEPLOY_PATIENT = dt.datetime(2026, 6, 12)   # 인내 배포 추정
DEPLOY_IMPAT = dt.datetime(2026, 6, 15)     # 성급 배포 추정


def parse(t):
    return dt.datetime.fromisoformat(str(t)[:19].replace("T", " "))


def load_ledger():
    rows = list(csv.DictReader(open(LEDGER, encoding="utf-8-sig")))
    for r in rows:
        r["_et"] = parse(r["entry_t"]); r["_xt"] = parse(r["exit_t"])
        r["_R"] = float(r["R"]) * 100; r["_side"] = int(r["side"])
    return rows


def grp_stat(name, g):
    if not g:
        print(f"  {name:24}: 0건"); return
    Rs = [r["_R"] for r in g]; w = [x for x in Rs if x > 0]
    s = [r for r in g if r["_side"] == -1]; l = [r for r in g if r["_side"] == 1]
    print(f"  {name:24}: {len(g):>2}건 | 합 {sum(Rs):+7.2f}% | 승률 {len(w)/len(g)*100:>3.0f}% "
          f"| 평균 {sum(Rs)/len(Rs):+5.2f}% | 숏{len(s)}/롱{len(l)}")


def regime(since):
    files = sorted(glob.glob(DATA_GLOB))
    if not files:
        print(f"  (가격데이터 {DATA_GLOB} 없음 — 국면판정 생략)"); return
    closes = []
    for f in files:
        try:
            for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                t = row.get("ts_utc") or row.get("open_time") or row.get("time")
                c = row.get("close")
                if t and c:
                    tt = parse(t)
                    if tt >= since:
                        closes.append((tt, float(c)))
        except Exception:
            pass
    if len(closes) < 2:
        print("  (구간 내 가격 부족)"); return
    closes.sort()
    p0, p1 = closes[0][1], closes[-1][1]
    hi = max(c for _, c in closes); lo = min(c for _, c in closes)
    net = (p1 - p0) / p0 * 100
    span = (hi - lo) / p0 * 100
    # 추세성 = |순변화| / 변동폭. 높으면 추세, 낮으면 횡보(왕복).
    trend = abs(net) / span * 100 if span else 0
    print(f"  기간 {closes[0][0]:%m-%d %H:%M} ~ {closes[-1][0]:%m-%d %H:%M}")
    print(f"  시가 {p0:,.0f} → 종가 {p1:,.0f} | 순변화 {net:+.1f}% | 고저폭 {span:.1f}% | "
          f"추세성(순변화/고저폭) {trend:.0f}%  → {'추세장' if trend >= 50 else '횡보/왕복장'}")


def regime_from_ledger(name, g):
    # 가격파일이 없을 때도 항상 동작: 해당 구간 거래들의 진입/청산가로 시장 흐름·승패패턴 요약
    if not g:
        print(f"  {name}: 해당 구간 거래 0건"); return
    p0 = float(g[0]["entry_px"]); p1 = float(g[-1]["exit_px"])
    pat = "".join("W" if r["_R"] > 0 else "L" for r in g)
    print(f"  {name}: 첫진입가 {p0:,.0f} → 마지막청산가 {p1:,.0f} ({(p1-p0)/p0*100:+.1f}%) | 승패열 {pat}")


def main():
    rows = load_ledger()
    print("=" * 72)
    print(f"진단: 백테 vs 실시간 성과 분리 | 원장 {LEDGER} | 총 {len(rows)}거래")
    print("=" * 72)
    print(f"{'#':>2} {'entry':16} {'exit':16} {'side':>4} {'R%':>7} {'reason':>8} {'cum%':>8}")
    cum = 0.0
    for i, r in enumerate(rows, 1):
        cum += r["_R"]
        sd = "S" if r["_side"] == -1 else "L"
        print(f"{i:>2} {str(r['entry_t'])[:16]:16} {str(r['exit_t'])[:16]:16} {sd:>4} "
              f"{r['_R']:>7.2f} {r.get('reason', '')[:8]:>8} {cum:>8.2f}")
    print("-" * 72)
    print("[구간 분리 — 거래 '진입시각' 기준]")
    grp_stat("전체", rows)
    grp_stat("백테(진입<06-12)", [r for r in rows if r["_et"] < DEPLOY_PATIENT])
    grp_stat("실시간 인내후(>=06-12)", [r for r in rows if r["_et"] >= DEPLOY_PATIENT])
    grp_stat("실시간 성급후(>=06-15)", [r for r in rows if r["_et"] >= DEPLOY_IMPAT])
    print("-" * 72)
    print("[수익 집중도]")
    Rs = [r["_R"] for r in rows]; tot = sum(Rs)
    mx = max(range(len(rows)), key=lambda i: rows[i]["_R"])
    print(f"  전체 합 {tot:+.2f}% | 최대거래 #{mx+1} {rows[mx]['_R']:+.2f}% "
          f"(전체의 {rows[mx]['_R']/tot*100:.0f}%) | 최대제외 {tot-rows[mx]['_R']:+.2f}%")
    print("-" * 72)
    print("[국면 — 원장 가격 기반(항상 동작)]")
    regime_from_ledger("백테(진입<06-12)   ", [r for r in rows if r["_et"] < DEPLOY_PATIENT])
    regime_from_ledger("실시간 인내후(>=06-12)", [r for r in rows if r["_et"] >= DEPLOY_PATIENT])
    regime_from_ledger("실시간 성급후(>=06-15)", [r for r in rows if r["_et"] >= DEPLOY_IMPAT])
    print("[국면 — 1m 가격 기반(데이터 있으면)]")
    print(" 인내(06-12)~:"); regime(DEPLOY_PATIENT)
    print(" 성급(06-15)~:"); regime(DEPLOY_IMPAT)
    print("=" * 72)
    print("해석 가이드: 백테 승률·평균R이 높고 실시간이 음수면 OOS 열화. "
          "실시간 국면이 '횡보/왕복'인데 봇이 추세추종이면 = 국면불일치(버그아님). "
          "수익이 단일거래·단일국면에 쏠렸으면 = 알파 취약(표본 한계).")


if __name__ == "__main__":
    main()
