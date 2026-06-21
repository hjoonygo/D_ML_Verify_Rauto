# -*- coding: utf-8 -*-
# [seed_seen.py] 과거 거래를 'seen'으로 1회 등록 → 이후 alert_check는 '새 거래'만 발신(실시간).
#   (없으면 첫 실행에 과거 전체가 신규로 잡혀 텔레그램 폭주). AWS 배포 직후 1회만 실행.
import os, csv, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.environ.get("RAUTO_OPS_STATE", os.path.join(HERE, "ops_state.json"))
LED = os.path.join(os.environ.get("RAUTO_DIR", HERE), "paper_ledger.csv")

seen = []
if os.path.exists(LED):
    for row in csv.DictReader(open(LED, encoding="utf-8-sig")):
        seen.append(f"{row['bot']}|{row['entry_t']}")
st = {"started": True, "seen": seen, "last_health_alert": "",
      "kill_alerted": False, "hb_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")}
with open(STATE, "w", encoding="utf-8") as f:
    json.dump(st, f, ensure_ascii=False, indent=1)
print(f"[seed] 과거 {len(seen)}거래 seen 등록 → 이후 새 거래만 발신. state={STATE}")
