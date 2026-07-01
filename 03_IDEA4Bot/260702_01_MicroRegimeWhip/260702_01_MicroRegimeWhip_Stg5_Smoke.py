# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg5_Smoke] ★RevoiRally@ETF 슬롯 로딩 스모크 + 무손상 재확인 (세션 260702_01).
#   검증: ① Rauto2Live.add_bot(rally_damp) 슬롯 정상 로딩 ② RevoiRally 원장에 size_mult 187건 damp(랠리숏)
#         ③ RevoiRally MDD < RevoiSafe MDD(리스크리듀서 효과) ④ RevoiSafe(damp없음) = 앵커/무손상 ⑤ m20·safety 정상.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_live import Rauto2Live
import champion_safety as CS
from veri_edge import VeriEdge
import back2tv_REVoi as B2

WINP = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
M20_THR = -22.0
# ★서버 BOT_REGISTRY와 동일 2엔트리(내가 등록한 것)
SAFE = {"name": "RevoiSafe@ETF", "lev": 15.0, "sz": 20.0, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "mdd": -14.8}
RALLY = {"name": "RevoiRally@ETF", "lev": 15.0, "sz": 20.0, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "rally_damp": [3.0, 0.5], "mdd": -12.6}
_BOTKEYS = ("tp_frac", "regime_factor", "gate", "gate_lo", "gate_hi", "early_tp_pct", "early_frac")


def _p(*a): print(*a, flush=True)


def bot_from(b, cfgp):
    p = dict(cfgp)
    for k in _BOTKEYS:
        if k in b:
            p[k] = b[k]
    return REVoiBot(p)


def main():
    _p("[Stg5 스모크] RevoiRally@ETF 슬롯 로딩 + 무손상")
    cfgp = json.load(open(WINP, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m, fund = load_1m(), load_funding()

    # ── 무손상 앵커(엔진 수정 후에도 BASE 재현) ──
    anc = VeriEdge(B2.rev_trades(d1m, fund, dict(cfgp))).anchor_check(75, 3, 1851.6)
    _p(f"  [무손상] BASE 앵커 = {anc['got_%']}% → {'✅' if anc['pass'] else '❌ 중단'}")
    if not anc["pass"]:
        return False

    live = Rauto2Live(d1m, fund, px_window_min=45 * 1440, champ_mode="recent", m20_thr=M20_THR)
    for b in [SAFE, RALLY]:
        live.add_bot(b["name"], bot_from(b, cfgp), b["sz"], b["lev"],
                     m20=(b.get("mdd", -99) >= M20_THR), rally_damp=b.get("rally_damp"))
    slots = {s.name: s for s in live.slots}
    _p(f"  슬롯 로딩 = {list(slots)} ({len(slots)}개)")
    assert set(slots) == {"RevoiSafe@ETF", "RevoiRally@ETF"}, "두 슬롯 로딩"

    s_safe, s_rally = slots["RevoiSafe@ETF"], slots["RevoiRally@ETF"]
    # ② size_mult 컬럼 검사
    has_sm_safe = "size_mult" in s_safe.T.columns
    sm_rally = s_rally.T["size_mult"].values if "size_mult" in s_rally.T.columns else None
    ndamp = int((sm_rally < 1.0).sum()) if sm_rally is not None else 0
    all_short = bool((s_rally.T.loc[sm_rally < 1.0, "side"].astype(int) == -1).all()) if ndamp else False
    _p(f"  ② size_mult: RevoiSafe 컬럼있음={has_sm_safe}(없어야 무손상) · RevoiRally damp {ndamp}건·전부숏={all_short}")
    assert not has_sm_safe, "RevoiSafe엔 size_mult 없어야(무손상)"
    assert ndamp > 0 and all_short, "RevoiRally damp = 랠리숏만"

    # ③ 리스크리듀서: RevoiRally MDD가 RevoiSafe보다 얕아야(같은 노출)
    _p(f"  ③ 슬립0 최종: RevoiSafe {(s_safe.final/1e4-1)*100:+,.0f}%/MDD{s_safe.mdd_full:.1f}% · RevoiRally {(s_rally.final/1e4-1)*100:+,.0f}%/MDD{s_rally.mdd_full:.1f}%")
    assert s_rally.mdd_full > s_safe.mdd_full, "RevoiRally MDD 더 얕아야(리스크리듀서)"
    assert abs((s_safe.final / 1e4 - 1) * 100 - (s_rally.final / 1e4 - 1) * 100) > 1.0, "damp로 수익 달라야"

    # ⑤ m20·safety
    _p(f"  ⑤ m20자격: RevoiSafe={s_safe._m20_cert} RevoiRally={s_rally._m20_cert} · 안전점수 Safe={CS.safety_score(SAFE)[0]}/{CS.MAX_SCORE} Rally={CS.safety_score(RALLY)[0]}/{CS.MAX_SCORE}")
    assert s_rally._m20_cert and s_safe._m20_cert, "둘 다 M20 자격"
    _p("  ✅ 스모크 통과 — RevoiRally 슬롯 로딩·damp 적용·리스크리듀서·무손상")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
