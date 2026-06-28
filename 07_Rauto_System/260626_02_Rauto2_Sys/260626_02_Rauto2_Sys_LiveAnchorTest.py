# -*- coding: utf-8 -*-
# [260626_02_Rauto2_Sys_LiveAnchorTest.py] ★rauto_live(리플레이/라이브 구동기) 검증 (세션 260626_02_Rauto2_Sys).
#   통과기준:
#     [T1 무손상]   now=마지막 → 드러난 ret == 앵커 +1851.6% (per-trade final == RautoCEX.run().final, 1원단위).
#     [T2 룩어헤드] 임의 now 여러개에서 ⒜드러난 거래는 모두 xt<=now ⒝px 최신 ts <= now-60s (마감봉만). 위반0.
#     [T3 단조]     now 전진 시 드러난 거래수 비감소, 마지막 = 932.
#     [T4 중앙px]   봇 2개 state() = 최상위 px 1개 공유(슬롯엔 px 없음) = 차트버그 구조해소.
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import pandas as pd  # noqa: E402
from fib_replay_1m import load_1m, load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_cex import RautoCEX, SlipModel  # noqa: E402
from rauto_live import Rauto2Live, per_trade_pnl  # noqa: E402

LOG = os.path.join(HERE, "260626_02_Rauto2_Sys_LiveAnchorTest_run.log")
ANCHOR_TOT = 1851.6491162901439
ANCHOR_NTR = 932
SIZE_PCT, LEV = 75.0, 3.0


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def main():
    open(LOG, "w").close()
    _p("=" * 64)
    _p("[rauto_live 검증] 리플레이/라이브 구동기 (세션 260626_02_Rauto2_Sys)")
    _p("=" * 64)
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d1m = load_1m()
    fund = load_funding()

    live = Rauto2Live(d1m, fund, px_window_min=14 * 1440)
    live.add_bot("REVoi", REVoiBot(p), SIZE_PCT, LEV)
    live.add_bot("REVoi_롱전용(가상)", REVoiBot(p), SIZE_PCT, LEV)   # 같은 봇 2슬롯 = px 공유 확인용
    slot0 = live.slots[0]

    # ── T1 무손상: per-trade final == RautoCEX.run().final, full reveal ret == anchor ──
    T = slot0.T.copy()
    T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    cex = RautoCEX(SIZE_PCT, LEV, slip=SlipModel(0.0, 0.0)).run(T.copy())
    d_final = abs(slot0.final - cex["final"])
    end_ms = int(live._idx_ms[-1])
    s_end = slot0.reveal(end_ms)
    t1 = (abs(slot0.ret_full - ANCHOR_TOT) < 0.5 and d_final < 1e-6
          and s_end["trades"] == ANCHOR_NTR and abs(s_end["ret"] - ANCHOR_TOT) < 0.5)
    _p("")
    _p("─ [T1 무손상]")
    _p(f"   per-trade final ${slot0.final:,.2f}  vs  RautoCEX.run ${cex['final']:,.2f}  (차이 ${d_final:.6f})")
    _p(f"   full reveal ret {s_end['ret']:+.2f}% · 거래 {s_end['trades']}  vs  앵커 {ANCHOR_TOT:+.2f}% · {ANCHOR_NTR}")
    _p(f"   → {'★PASS' if t1 else '✗FAIL'}")

    # ── T2 룩어헤드: 여러 now에서 드러난거래 xt<=now & px 최신 ts<=now-60s ──
    times = live.replay_times(step_min=240)
    probe = times[::max(1, len(times) // 20)]                  # 약 20개 표본
    viol_trade = 0
    viol_px = 0
    for now in probe:
        st = live.state(now, with_px=True)
        for sl in st["slots"]:
            for t in sl["trd"]:
                if t["xt"] > now:
                    viol_trade += 1
            if sl.get("open_et") is not None and sl["open_et"] > now:
                viol_trade += 1
        if st["px"]:
            if st["px"][-1][0] > now - 60_000:
                viol_px += 1
    t2 = (viol_trade == 0 and viol_px == 0)
    _p("")
    _p("─ [T2 룩어헤드 차단]")
    _p(f"   표본 {len(probe)}개 now · 미래거래 노출 {viol_trade} · 미마감px 노출 {viol_px} → {'★PASS(룩어헤드0)' if t2 else '✗FAIL'}")

    # ── T3 단조: now 전진 → 거래수 비감소, 마지막=932 ──
    counts = [live.slots[0].reveal(now)["trades"] for now in times]
    mono = all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1))
    t3 = (mono and counts[-1] == ANCHOR_NTR)
    _p("")
    _p("─ [T3 단조 드러내기]")
    _p(f"   거래수 {counts[0]} → ... → {counts[-1]} · 비감소={mono} · 마지막=={ANCHOR_NTR} → {'★PASS' if t3 else '✗FAIL'}")

    # ── T4 중앙 px 공유: state.px 최상위 1개, 슬롯엔 px 없음 ──
    st = live.state(end_ms, with_px=True)
    has_top_px = ("px" in st and len(st["px"]) > 0)
    no_slot_px = all("px" not in sl for sl in st["slots"])
    t4 = has_top_px and no_slot_px and len(st["slots"]) == 2
    _p("")
    _p("─ [T4 중앙 px 단일출처]")
    _p(f"   최상위 px {len(st['px'])}봉(윈도우 14일) · 슬롯에 px 없음={no_slot_px} · 슬롯 {len(st['slots'])}개 → {'★PASS(전봇 공유=차트버그해소)' if t4 else '✗FAIL'}")

    allpass = t1 and t2 and t3 and t4
    _p("")
    _p("=" * 64)
    _p(f"[종합] T1무손상={'O' if t1 else 'X'} T2룩어헤드={'O' if t2 else 'X'} T3단조={'O' if t3 else 'X'} T4중앙px={'O' if t4 else 'X'}")
    _p(f"[판정] rauto_live 구동기 : {'✅ 검증통과 — 서버/대시보드 개조 진행 가능' if allpass else '❌ 실패 — 멈추고 원인규명'}")
    _p("=" * 64)
    return allpass


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
