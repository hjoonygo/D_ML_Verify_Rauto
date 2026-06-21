# -*- coding: utf-8 -*-
# [ops_status_v2.py] /status v2 — 슬롯 state.json 전수 집계(봇별 표시) + Dauto 신선도.
#   기존 v1(ops_status)은 [Rauto_Daily,Dauto] 하드코딩+단일인스턴스라 봇별 안 나옴 → v2는 C:\Rauto*\state.json을
#   모두 스캔해 슬롯(TS성급/TS인내/SW…)별 1줄 + Dauto 끊김여부 보고. 06-19 재구축 시 표준 /status.
#   대시보드와 동일 데이터원(state.json) = 일관. 표준라이브러리만.
import os, sys, json, glob, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 슬롯 폴더 패턴(필요시 env로 확장). 기존 인스턴스도 state.json 쓰면 자동 포함.
GLOBS = os.environ.get("RAUTO_SLOT_GLOB",
    r"C:\Rauto*\state.json;C:\run_Rauto*\state.json").split(";")


def build_status():
    files = []
    for g in GLOBS:
        files += glob.glob(g)
    files = sorted(set(files))
    if not files:
        return "슬롯 state.json 없음 (아직 미가동)"
    out = []
    dauto_line = None
    slot_lines = []
    for fp in files:
        try:
            st = json.load(open(fp, encoding="utf-8"))
        except Exception:
            slot_lines.append(f"  {os.path.dirname(fp)}: state 읽기 실패"); continue
        # Dauto 신선도(한 번만)
        if dauto_line is None and "dauto_ok" in st:
            ok = st.get("dauto_ok"); sm = st.get("dauto_stale_min", "?")
            dauto_line = ("✅ Dauto 신선" if ok else f"⚠ Dauto 끊김") + f" ({sm}분 전)"
        for s in st.get("slots", []):
            side = {"L": "LONG", "S": "SHORT", "-": "—"}.get(s.get("side", "-"), s.get("side"))
            pnl = s.get("pnl", 0)
            ptxt = f"{pnl:+.1f}%" if s.get("status") == "보유" else s.get("status", "")
            slot_lines.append(f"  {s.get('name','?'):<16} {side:<5} {ptxt:<8} 잔고 ${s.get('bal',0):,.0f} (거래 {s.get('trades','?')})")
    out.append(dauto_line or "Dauto: 상태미상")
    out.append(f"─ 슬롯 {len(slot_lines)}개 ─")
    out += slot_lines
    out.append(f"(집계 {datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M UTC')})")
    return "\n".join(out)


if __name__ == "__main__":
    print(build_status())
