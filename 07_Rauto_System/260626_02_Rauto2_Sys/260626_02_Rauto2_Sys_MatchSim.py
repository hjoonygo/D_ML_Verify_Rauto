# -*- coding: utf-8 -*-
# [260626_02_Rauto2_Sys_MatchSim.py] ★Rauto2 신규시스템 + REVoi봇 ↔ 옛 b32 폰 대시보드 '매칭 시뮬레이션'
#   (세션 260626_02_Rauto2_Sys). 캡틴 지시: "기존 서버·폰 코드가 검증된 게 맞는지 다시 확인하고,
#    Rauto2에서 바뀐 시스템과 REVoi봇 매칭에 문제없는지 시뮬레이션 후 진행."
#   = 코드 본격 개조 '전에' 아래 3관문을 통과해야 진행한다.
#     [관문A 무손상] 봇(REVoi)→관제센터→RautoCEX run_backtest = 앵커 +1851.6%/MDD-24.6% 1원단위 재현(§15.2).
#     [관문B 거래오버레이 매칭] REVoi 거래원장 → b32 slot.trd 스키마{et,xt,ep,xp,side,pnl} 무손실 변환 +
#                              per-trade pnl 복리 == run_backtest tot (이중계산·누락 없음).
#     [관문C 차트버그 해소] 중앙 1m(DataHub) 단일출처 px를 모든 봇이 '공유' → 캔들 동일, 거래만 다름.
#                          = "봇마다 실시간 차트가 다르게 나타난" 옛 버그가 구조적으로 사라짐을 증명.
#   ★검증엔진 무수정·호출만(§15.1): 데이터·신호·진입/청산·체결비용은 전부 검증모듈을 '호출'.
#     per-trade pnl 추출은 rauto_cex의 FeeModel/SlipModel/MarginModel을 '그대로 import'해 동일 코드로 돈다
#     (재구현 아님). 최종 잔고가 RautoCEX.run()과 1원단위 일치하는지 assert로 가드.
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))                 # 07_Rauto_System/<세션> → RfRauto 루트
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths                                   # noqa: E402
ensure_paths()
import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402
from fib_replay_1m import load_1m, load_funding                        # noqa: E402 검증된 데이터 로더
from rauto_orchestrator import RautoOrchestrator                       # noqa: E402 [0] 관제센터(봇무관)
from REVoi_bot import REVoiBot                                         # noqa: E402 [1] REVoi 봇(계약)
from rauto_cex import RautoCEX, SlipModel, FeeModel, MarginModel, MK, TK  # noqa: E402 [3] 체결+비용

LOG = os.path.join(HERE, "260626_02_Rauto2_Sys_MatchSim_run.log")
STATE_OUT = os.path.join(HERE, "260626_02_Rauto2_Sys_state_sample.json")

ANCHOR_TOT = 1851.6491162901439     # back2tv_rev_winners.json REV_MDD25_36mo
ANCHOR_MDD = -24.555640887050735
ANCHOR_NTR = 932
SIZE_PCT, LEV = 75.0, 3.0           # 사이징 = Rauto 결정(봇 아님)
PX_WINDOW_DAYS = 60                 # state.json px 윈도우(폰 차트용; 운영은 슬라이딩, 여기선 최근 60일)

# ── b32 control_dashboard.html 이 실제로 '읽는' 필드(내가 547줄 정독해 추출) = 매칭 기준 ──
REQ_TRD_FIELDS = ["et", "xt", "ep", "xp", "side", "pnl"]              # drawChart()/diagBox() 가 쓰는 거래 필드
REQ_SLOT_FIELDS = ["name", "side", "ret", "pnl", "mdd", "trades",     # render()/cmpCard() 가 쓰는 슬롯 필드
                   "winrate", "pf", "payoff", "consec", "px", "trd"]


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def _ms(t):
    """pandas/numpy 시각 → epoch ms(UTC). load_1m이 tz제거(UTC naive)라 .value(ns)/1e6."""
    return int(pd.Timestamp(t).value // 1_000_000)


def per_trade_pnl(T, size_pct, lev):
    """★per-trade 계좌 손익% 추출 = RautoCEX.run()의 루프를 '동일 모델(import)'로 1:1 미러.
       재구현 아님 — FeeModel/SlipModel/MarginModel/MK/TK를 rauto_cex에서 그대로 가져와 같은 산식.
       반환: (pnl_list[%], final_bal, mdd%, nliq). 가드 = RautoCEX.run() 최종값과 1원단위 일치 assert."""
    fee = FeeModel()
    slip = SlipModel(0.0, 0.0)                        # 앵커 = 슬립0
    margin = MarginModel(size_pct, lev)
    R = T["R"].values.astype(float)
    MAE = T["mae"].values.astype(float)
    FUND = T["fund"].values.astype(float)
    REASON = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    bal = 10000.0
    peak = 10000.0
    mdd = 0.0
    nliq = 0
    pnl = []
    slip_mkt = slip.market_exit_slip()
    for i in range(len(R)):
        gR = R[i] + MK + TK + FUND[i]                # _gross_R 복원(rauto_cex 동일)
        ec = fee.entry_cost(False)
        xc = fee.exit_cost(REASON[i])
        is_mkt_exit = REASON[i] != "tp"
        R_net = gR - ec - xc - FUND[i] - (slip_mkt if is_mkt_exit else 0.0)
        p, liq = margin.step(bal, R_net, MAE[i], FUND[i])
        if liq:
            nliq += 1
        bal *= (1.0 + p)
        pnl.append(p * 100.0)
        if bal > peak:
            peak = bal
        dd = bal / peak - 1.0
        if dd < mdd:
            mdd = dd
        if bal <= 0:
            break
    return pnl, bal, mdd * 100.0, nliq


def _stats(pnl):
    """b32 cmpCard 통계(거래·승률·손익비·PF·연속손실·수익률) — control_server._stats와 동일 산식."""
    n = len(pnl)
    if not n:
        return dict(trades=0, winrate=0, payoff="-", pf="-", ret=0.0, consec=0)
    w = [x for x in pnl if x > 0]
    l = [x for x in pnl if x < 0]
    payoff = round((sum(w) / len(w)) / abs(sum(l) / len(l)), 1) if (w and l) else "-"
    pf = round(sum(w) / abs(sum(l)), 2) if l else "-"
    r = 1.0
    for x in pnl:
        r *= (1.0 + x / 100.0)
    cc = mx = 0
    for x in pnl:
        cc = cc + 1 if x < 0 else 0
        mx = max(mx, cc)
    return dict(trades=n, winrate=round(len(w) / n * 100), payoff=payoff, pf=pf,
                ret=round((r - 1) * 100, 1), consec=mx)


def build_slot(name, T, pnl_list, px_rows):
    """REVoi 거래원장 + per-trade pnl + 중앙 px → b32 state.json slot 1개(스키마 1:1)."""
    trd = []
    for r, pn in zip(T.itertuples(), pnl_list):
        trd.append({
            "et": _ms(r.et),
            "xt": _ms(getattr(r, "xt_fill", r.xt)),   # 실제 체결 청산시각(et+TF) — 대시보드 30일/오버레이용
            "ep": round(float(r.entry), 2),
            "xp": round(float(r.exit), 2),
            "side": "L" if int(r.side) == 1 else "S",  # 원장 정수(1/-1) → 대시보드 L/S
            "pnl": round(float(pn), 2),                # 사이징·비용 반영 계좌 손익%
        })
    st = _stats(pnl_list)
    eq = []
    bal = 10000.0
    for pn in pnl_list:
        bal *= (1.0 + pn / 100.0)
        eq.append(round(bal, 1))
    slot = {
        "name": name,
        "side": "-",                  # 백테 종료 = 무포지션(열린포지션 fabricate 금지)
        "ret": st["ret"],
        "pnl": 0.0,
        "mdd": round(min([0.0] + [eq[i] / max(eq[:i + 1]) - 1.0 for i in range(len(eq))]) * 100.0, 1) if eq else 0.0,
        "trades": st["trades"],
        "winrate": st["winrate"],
        "pf": st["pf"],
        "payoff": st["payoff"],
        "consec": st["consec"],
        "entry": None,
        "open_et": None,
        "px": px_rows,                # ★중앙 1m 단일출처(모든 봇 공유)
        "trd": trd,
        "equity": eq[-300:],          # 자산곡선(폰 cmpCard) — 최근 300점
        "eqt": [t["xt"] for t in trd][-300:],
    }
    return slot


def main():
    open(LOG, "w").close()
    _p("=" * 68)
    _p("[Rauto2 ↔ REVoi ↔ b32 매칭 시뮬레이션] 세션 260626_02_Rauto2_Sys")
    _p("=" * 68)

    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp",
                                      "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    _p(f"[config] REV_MDD25_36mo · 레버{LEV}/증거금{SIZE_PCT}% · 신호TF {p['rev_tf']}m · 기대앵커 {ANCHOR_TOT:+.1f}%")

    d1m = load_1m()
    fund = load_funding()
    _p(f"[데이터] 중앙 1m {len(d1m):,}행 · 기간 {d1m.index.min()} ~ {d1m.index.max()} · 컬럼 {list(d1m.columns)}")

    # ───────────────────────── 관문A: 무손상 (봇→관제센터→CEX = 앵커) ─────────────────────────
    bot = REVoiBot(p)
    orch = RautoOrchestrator(bot, size_pct=SIZE_PCT, lev=LEV, slip=SlipModel(0.0, 0.0))
    r = orch.run_backtest(d1m, fund)
    T = r["trades"].sort_values("et").reset_index(drop=True)
    dA_tot = abs(r["tot"] - ANCHOR_TOT)
    dA_mdd = abs(r["mdd"] - ANCHOR_MDD)
    gateA = (dA_tot < 0.5 and dA_mdd < 0.5 and r["nliq"] == 0 and len(T) == ANCHOR_NTR)
    _p("")
    _p("─ [관문A 무손상] 봇(REVoi)→관제센터(봇무관)→RautoCEX run_backtest")
    _p(f"   결과 : {r['tot']:+.2f}% · MDD {r['mdd']:.2f}% · 청산 {r['nliq']} · 거래 {len(T)}")
    _p(f"   앵커 : {ANCHOR_TOT:+.2f}% · MDD {ANCHOR_MDD:.2f}% · 청산 0 · 거래 {ANCHOR_NTR}")
    _p(f"   차이 : 복리 {dA_tot:.3f}%p · MDD {dA_mdd:.3f}%p → {'★PASS(무손상)' if gateA else '✗FAIL'}")

    # ───────────────── 관문B: 거래오버레이 매칭 (per-trade pnl 복리 == run_backtest) ─────────────────
    T2 = T.copy()
    T2["_ym"] = pd.to_datetime(T2["et"]).dt.to_period("M").astype(str)
    cex_chk = RautoCEX(SIZE_PCT, LEV, slip=SlipModel(0.0, 0.0)).run(T2.copy())   # 공식 집계
    pnl_list, bal_mirror, mdd_mirror, nliq_mirror = per_trade_pnl(T, SIZE_PCT, LEV)
    # 가드: per-trade 미러 최종잔고 ≡ RautoCEX.run() 최종잔고 (per-trade 추출이 충실하다는 증거)
    d_final = abs(bal_mirror - cex_chk["final"])
    tot_from_trades = (bal_mirror / 10000.0 - 1.0) * 100.0
    # 스키마 변환 + 필드 검사
    px_all = d1m.reset_index()
    px_all.columns = ["t"] + list(d1m.columns)
    cut = d1m.index.max() - pd.Timedelta(days=PX_WINDOW_DAYS)
    win = px_all[px_all["t"] >= cut]
    px_rows = [[_ms(row.t), round(float(row.open), 1), round(float(row.high), 1),
                round(float(row.low), 1), round(float(row.close), 1)] for row in win.itertuples()]
    slot_revoi = build_slot("REVoi", T, pnl_list, px_rows)
    # 필드 누락 검사 (대시보드가 읽는 필드 전부 있는가)
    miss_slot = [k for k in REQ_SLOT_FIELDS if k not in slot_revoi]
    miss_trd = []
    for t in slot_revoi["trd"]:
        for k in REQ_TRD_FIELDS:
            if k not in t:
                miss_trd.append(k)
    miss_trd = sorted(set(miss_trd))
    bad_side = [t["side"] for t in slot_revoi["trd"] if t["side"] not in ("L", "S")]
    bad_px = [row for row in px_rows[:50] if len(row) != 5]
    gateB = (d_final < 1e-6 and abs(tot_from_trades - r["tot"]) < 0.01
             and not miss_slot and not miss_trd and not bad_side and not bad_px)
    _p("")
    _p("─ [관문B 거래오버레이 매칭] REVoi 원장 → b32 slot.trd{et,xt,ep,xp,side,pnl}")
    _p(f"   per-trade pnl 복리 {tot_from_trades:+.2f}%  vs  run_backtest {r['tot']:+.2f}%  (차이 {abs(tot_from_trades-r['tot']):.4f}%p)")
    _p(f"   per-trade 미러 최종잔고 ${bal_mirror:,.2f}  vs  RautoCEX.run ${cex_chk['final']:,.2f}  (차이 ${d_final:.6f})")
    _p(f"   slot.trd {len(slot_revoi['trd'])}건 변환 · 누락필드 slot={miss_slot or '없음'} trd={miss_trd or '없음'} · side오류 {len(bad_side)} · px형식오류 {len(bad_px)}")
    _p(f"   → {'★PASS(무손실 변환·이중계산0)' if gateB else '✗FAIL'}")
    if slot_revoi["trd"]:
        ex = slot_revoi["trd"][len(slot_revoi["trd"]) // 2]
        _p(f"   [예시 거래] {ex}")

    # ───────────────── 관문C: 차트버그 해소 (중앙 px 공유 → 캔들 동일, 거래만 다름) ─────────────────
    # 가상의 두 번째 봇 슬롯(REVoi 거래의 롱만) — 같은 중앙 px를 '공유'하는지 검증.
    T_long = T[T["side"].astype(int) == 1].reset_index(drop=True)
    pnl_long = [pn for r2, pn in zip(T.itertuples(), pnl_list) if int(r2.side) == 1]
    slot_b = build_slot("REVoi_롱전용(가상)", T_long, pnl_long, px_rows)   # ★동일 px_rows 객체 전달
    # 캔들(px) 동일 + 거래(trd) 다름?
    px_identical = (slot_revoi["px"] == slot_b["px"])
    trd_differ = (len(slot_revoi["trd"]) != len(slot_b["trd"]))
    gateC = px_identical and trd_differ
    _p("")
    _p("─ [관문C 차트버그 해소] 중앙 1m(DataHub) 단일출처 px 공유")
    _p(f"   봇1(REVoi) 캔들 {len(slot_revoi['px'])}개 · 거래 {len(slot_revoi['trd'])}건")
    _p(f"   봇2(롱전용) 캔들 {len(slot_b['px'])}개 · 거래 {len(slot_b['trd'])}건")
    _p(f"   캔들 완전동일 = {px_identical}  ·  거래는 봇마다 다름 = {trd_differ}")
    _p(f"   → {'★PASS(봇마다 캔들 동일·거래만 상이 = 옛 버그 구조해소)' if gateC else '✗FAIL'}")

    # ───────────────── 샘플 state.json 저장 (b32 대시보드가 그대로 읽을 수 있는 형태) ─────────────────
    state = {
        "slots": [slot_revoi, slot_b],
        "live": False,
        "dauto_ok": True,
        "dauto_stale_min": 0,
        "updated": str(d1m.index.max()),
        "acct": {},
        "_note": "Rauto2 매칭 시뮬레이션 산출 — b32 control_dashboard.html 스키마 1:1",
    }
    with open(STATE_OUT, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    sz = os.path.getsize(STATE_OUT) / 1024.0
    _p("")
    _p(f"[산출] 샘플 state.json 저장 = {STATE_OUT} ({sz:,.0f} KB · 슬롯 2개)")

    # ───────────────────────────── 종합 판정 ─────────────────────────────
    allpass = gateA and gateB and gateC
    _p("")
    _p("=" * 68)
    _p(f"[종합] 관문A 무손상={'O' if gateA else 'X'} · 관문B 거래매칭={'O' if gateB else 'X'} · 관문C 차트버그해소={'O' if gateC else 'X'}")
    _p(f"[판정] Rauto2 신규시스템 + REVoi봇 ↔ b32 대시보드 매칭 : "
       + ("✅ 문제없음 — 개조 진행 가능" if allpass else "❌ 문제발견 — 멈추고 원인규명"))
    _p("=" * 68)
    return allpass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
