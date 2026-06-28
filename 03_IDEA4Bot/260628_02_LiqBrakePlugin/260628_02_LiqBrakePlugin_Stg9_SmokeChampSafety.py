# -*- coding: utf-8 -*-
# [260628_02 Stg9] 통합 스모크 — RevoiSafe@ETF 슬롯 로딩 + 안전점수 + 챔피언 선정(가산점 타이브레이커) 작동 확인.
import os, sys, json
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
from rauto_live import Rauto2Live
from REVoi_bot import REVoiBot
import champion_safety as CS

cfg = json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
BOTKEYS = ("tp_frac", "regime_factor", "gate", "gate_lo", "gate_hi", "early_tp_pct", "early_frac")
bots = [
    {"name": "REVoi@ETF",     "lev": 3.0,  "sz": 75.0,  "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "mdd": -11.2},
    {"name": "RevoiSafe@ETF", "lev": 15.0, "sz": 20.0,  "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "mdd": -14.8},
    {"name": "M0천장",        "lev": 16.0, "sz": 100.0, "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -70.1},
    {"name": "결합R+P80",     "lev": 6.0,  "sz": 75.0,  "tp_frac": 0.8, "gate": True, "dd_cut": [-0.08, 0.5], "mdd": -18.6},
]

print("=" * 78)
print("[Stg9 스모크] 챔피언 안전장치 가산점 + RevoiSafe 로딩 (핀 해제로 가산점 작동 확인)")
print("=" * 78)
d1m, fund = load_1m(), load_funding()
nl = Rauto2Live(d1m, fund, champ_mode="recent", champ_pin=None)   # ★핀 해제 = 자동선발+가산점
for b in bots:
    pp = dict(cfg)
    for k in BOTKEYS:
        if k in b:
            pp[k] = b[k]
    nl.add_bot(b["name"], REVoiBot(pp), b["sz"], b["lev"], dd_cut=b.get("dd_cut"),
               m20=(b["mdd"] >= -22.0), reg_monthly=None, safety_meta=b)

st = nl.state(int(nl._idx_ms[-1]))
print(f"\n{'봇':>16}{'M20풀':>7}{'안전점수':>9}{'챔피언':>8}   충족 안전장치")
for s in st["slots"]:
    items = "·".join(it["name"] for it in s.get("safety_items", []))
    print(f"  {s['name']:>14}{'O' if s['m20'] else 'X':>6}{s.get('safety',0):>8}/8{'★' if s['champ'] else '':>6}   {items}")
champ = next((s for s in st["slots"] if s["champ"]), None)
print(f"\n  → 챔피언 = {champ['name'] if champ else '없음'} (champ_mode=recent·핀해제·M20풀+최근수익 동점시 안전점수)")
print("  → RevoiSafe@ETF 슬롯 로딩 = " + ("✅ 성공" if any(s['name'] == 'RevoiSafe@ETF' for s in st['slots']) else "❌ 실패"))
print("[OK] 스모크 완료")
