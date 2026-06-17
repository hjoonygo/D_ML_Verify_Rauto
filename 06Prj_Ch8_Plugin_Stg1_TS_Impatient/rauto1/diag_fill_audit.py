# -*- coding: utf-8 -*-
# [diag_fill_audit.py] 체결가 룩어헤드 교차감사 — 1회용
#   질문: 백테/리플레이의 entry_px·exit_px가 (1)그 시각 실제 1분봉 범위 안의 현실적 체결인가
#         (2)이긴 숏이 진짜로 가격이 내렸을 때인가(상승장 숏이득=모순) 를 데이터로 검증.
#   읽기: C:\Rauto1\paper_ledger.csv + C:\BinanceData\*1m*.csv
#   실행: python diag_fill_audit.py
import csv, glob, sys
import pandas as pd, numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fs = sorted(glob.glob(r"C:\BinanceData\*1m*.csv"))
df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
tcol = [c for c in df.columns if "ts" in c.lower() or "time" in c.lower()][0]
if np.issubdtype(df[tcol].dtype, np.number):
    df["ts"] = pd.to_datetime(df[tcol], unit="ms")
else:
    df["ts"] = pd.to_datetime(df[tcol], errors="coerce")
df = df.dropna(subset=["ts"]).drop_duplicates("ts").set_index("ts").sort_index()
H, L, C = df["high"], df["low"], df["close"]
print(f"1m 데이터: {len(df)}행 {C.index.min()} ~ {C.index.max()}")

def bar(t):
    t = pd.Timestamp(t)
    seg = df[:t]
    if not len(seg):
        return None
    row = seg.iloc[-1]
    return float(row["high"]), float(row["low"]), float(row["close"])

rows = list(csv.DictReader(open(r"C:\Rauto1\paper_ledger.csv", encoding="utf-8-sig")))
print(f"\n원장 {len(rows)}거래 — 체결가 vs 실제 1분봉 교차감사\n")
print(f"{'#':>2} {'entry_t':16} {'sd':>2} {'entry_px':>9} {'mkt@진입[저~고]':>20} {'exit_px':>9} {'mkt@청산[저~고]':>20} {'가격이동%':>8} {'R%':>6} {'플래그'}")
bad_fill = 0; contradiction = 0
for i, x in enumerate(rows, 1):
    ep = float(x["entry_px"]); xp = float(x["exit_px"]); sd = int(x["side"])
    R = float(x["R"]) * 100
    be = bar(x["entry_t"]); bx = bar(x["exit_t"])
    flags = []
    if be:
        ein = be[1] - 1 <= ep <= be[0] + 1  # 진입가가 그 봉 [저~고] 안인가
        if not ein: flags.append("진입가 봉이탈!")
    if bx:
        xin = bx[1] - 1 <= xp <= bx[0] + 1
        if not xin: flags.append("청산가 봉이탈!")
    mv = (xp - ep) / ep * 100
    # 숏(sd=-1): 이득이면 가격 내려야(mv<0). 롱(sd=1): 이득이면 mv>0.
    if (sd == -1 and R > 0 and mv > 0.05) or (sd == 1 and R > 0 and mv < -0.05):
        flags.append("★수익인데 가격역행!"); contradiction += 1
    if "봉이탈" in "".join(flags): bad_fill += 1
    bestr = f"[{be[1]:.0f}~{be[0]:.0f}]" if be else "?"
    bxstr = f"[{bx[1]:.0f}~{bx[0]:.0f}]" if bx else "?"
    print(f"{i:>2} {x['entry_t'][:16]:16} {('L'if sd==1 else'S'):>2} {ep:>9.0f} {bestr:>20} {xp:>9.0f} {bxstr:>20} {mv:>+8.2f} {R:>+6.2f}  {' '.join(flags)}")
print(f"\n요약: 체결가 봉이탈(비현실 체결=룩어헤드 의심) {bad_fill}건 / 수익인데 가격역행(P&L모순) {contradiction}건")
print("→ 둘 다 0이면: 체결가는 실제 시장범위 내 + 수익은 실제 가격이동과 일치 = 룩어헤드 없음(인과 정상).")
