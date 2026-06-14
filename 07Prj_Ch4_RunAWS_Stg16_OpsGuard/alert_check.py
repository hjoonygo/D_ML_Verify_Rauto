# -*- coding: utf-8 -*-
# [파일명] alert_check.py — Rauto_Daily STEP4: 신규 이벤트 diff → 텔레그램(중복방지 state)
# 코드길이: 약 110줄 | 내부버전: stg16_alert_check_v2 (v1 + ⑤일일 하트비트 — 캡틴 승인 2026-06-13)
# [v2] 매시간 배치 전환에 맞춰, UTC 날짜가 바뀐 뒤 첫 완주에서 하루 1장 생존신고 발신.
# [이벤트 4종] ①시작(첫 OK 완주 1회) ②진입 ③청산 ④오류(★긴급·kill.flag)
# [★설계 주석 — 캡틴 보고분] Stg14 원장 = 완결거래 1행(entry_t+exit_t 동시 기록).
#   별도 OPEN 행이 없어 실시간 진입 알림은 불가(일배치·봇 무수정 원칙) →
#   신규 행 1건당 ②진입+③청산 2장 연속 발신. 가격은 Dauto 1m close 역참조.
#   실거래 전환 시 주문모듈이 OPEN 이벤트를 같은 send 인터페이스로 직접 발신.
import os, sys, csv, json, glob
import ops_common as oc
import alert_telegram as tg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE = os.environ.get("RAUTO_OPS_STATE", os.path.join(oc.HERE, "ops_state.json"))
LEV_NOTE = {"TS": "lev22 x k0.77", "SW": "lev15 x 26.67% x k0.77"}   # §9 확정 설정값
_PX = None


def price_at(ts):
    global _PX
    if _PX is None:
        _PX = {}
        for f in glob.glob(os.path.join(oc.DAUTO_DIR, "BTCUSDT_1m_*.csv")):
            with open(f, encoding="utf-8-sig") as fh:        # BOM 안전
                for row in csv.DictReader(fh):
                    _PX[row["ts_utc"]] = row["close"]
    v = _PX.get(str(ts))
    return float(v) if v else None


def dollar(v):
    return f"${v:,.0f}" if v is not None else "N/A"


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"started": False, "seen": [], "last_health_alert": "", "kill_alerted": False}


def main():
    st, sent = load_state(), 0
    rd = oc.rauto_dir()
    hl_path = os.path.join(rd, "stg14_health.log")
    hlast = ""
    if os.path.exists(hl_path):
        body = open(hl_path, encoding="utf-8").read().strip()
        hlast = body.splitlines()[-1] if body else ""
    # ① 시작 — Rauto_Daily가 OK로 완주한 첫날 1회
    if not st["started"] and hlast.startswith("OK"):
        tg.send(f"🟢 Rauto 시작 | {oc.now_utc()} | Rauto_Daily 첫 OK 완주 | {hlast}")
        st["started"] = True
        sent += 1
    # ②③ 신규 거래 행 → 진입+청산 2장 (key=bot|entry_t, 멱등 재생성 안전)
    led = os.path.join(rd, "paper_ledger.csv")
    if os.path.exists(led):
        for row in csv.DictReader(open(led, encoding="utf-8-sig")):   # BOM 안전
            key = f"{row['bot']}|{row['entry_t']}"
            if key in st["seen"]:
                continue
            side = "LONG" if float(row["side"]) > 0 else "SHORT"
            p = float(row["p"])
            bal = float(row["bal"])
            bal0 = bal / (1.0 + p) if p > -1.0 else bal
            pe, px = price_at(row["entry_t"]), price_at(row["exit_t"])
            lev = LEV_NOTE.get(row["bot"], "")
            tg.send(f"📈 진입 | {row['bot']} {side} | {row['entry_t']} UTC | "
                    f"진입가 {dollar(pe)} | 슬롯잔고 {dollar(bal0)} | {lev}")
            tg.send(f"📉 청산 | {row['bot']} {side} | {row['exit_t']} UTC | "
                    f"청산가 {dollar(px)} | P&L {p:+.2%} ({bal - bal0:+,.2f}$) | "
                    f"잔고 ${bal:,.2f} | 사유 {row['reason']}")
            st["seen"].append(key)
            sent += 2
    # ④ 오류 — ★긴급 신규 / kill.flag (kill_guard 발신과 별개 state로 중복 방지)
    if hlast.startswith("★긴급") and st["last_health_alert"] != hlast:
        tg.send(f"🚨 오류 | {hlast}")
        st["last_health_alert"] = hlast
        sent += 1
    if os.path.exists(oc.KILL_FLAG):
        if not st["kill_alerted"]:
            tg.send(f"🚨 KILL | kill.flag 존재 확인 | {oc.now_utc()}")
            st["kill_alerted"] = True
            sent += 1
    else:
        st["kill_alerted"] = False
    # ⑤ 일일 하트비트 — UTC 날짜가 바뀐 뒤 첫 완주에서 하루 1장 (침묵=정상/사망 구분용)
    today = oc.now_utc()[:10]
    if st.get("hb_date", "") != today:
        sc = os.path.join(rd, "scorecard_daily.csv")
        if os.path.exists(sc):
            rows = list(csv.DictReader(open(sc, encoding="utf-8-sig")))
            if rows:
                r = rows[-1]
                tg.send(f"✅ 일일요약 {r['date']} | 거래 {r['trade_n']}건 | "
                        f"잔고 TS ${float(r['bal_ts']):,.0f} / SW ${float(r['bal_sw']):,.0f} | "
                        f"갭 {r['gap_n']}건 | 동치 {r['equiv_chk']}")
                st["hb_date"] = today
                sent += 1
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    oc.olog(f"alert_check 완료 | 신규발신 {sent}건 | 원장키 {len(st['seen'])}개 추적")
    return 0


if __name__ == "__main__":
    sys.exit(main())
