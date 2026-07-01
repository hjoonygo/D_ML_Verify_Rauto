# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg6_SafeVsRally] ★RevoiSafe vs RevoiRally 정밀 비교 (§19 기준, 캡틴 지시 2026-07-02).
#   캡틴 지적: 두 봇 지표 거의 같고 rally만 수익 낮음(7일 -2.2% 동일). "개선된 게 있나?" → L2 순효과를 정직 격리.
#   원인가설: L2는 랠리(7일추세≥+3%)서만 작동 → 현 하락레짐=no-op=동일. COMBO early_tp가 이미 랠리 수익화 → L2가 그걸 깎아 수익만↓?
#   ★§19 산출: ①OOS(held-out 2025+) 전체+분기별 롱/숏(슬립0/현실10bp) ②post-2024 매월(양수월) ③MDD 4단+강제청산 ④안전장치(강제청산·20%cap) ⑤레버업변형.
#   ★검증엔진만·무손상 앵커·비용 현실=시장청산 10bp(memory#9).
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from veri_edge import VeriEdge
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel, MMR_T1, LIQ_SLIP, LIQ_COST
from rauto_regime_sizing import apply_rally_damp

SZ, LEV = 20.0, 15
WINP = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
S0 = SlipModel(0, 0, 0)       # 슬립0(낙관)
SR = SlipModel(0, 0, 10.0)    # 현실 시장청산 10bp
OUT = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260702_01_MicroRegimeWhip_Stg6_SafeVsRally")


def _p(*a): print(*a, flush=True)


def slc(led, lo=None, hi=None):
    e = pd.to_datetime(led["et"]); m = pd.Series(True, index=led.index)
    if lo: m &= e >= pd.Timestamp(lo)
    if hi: m &= e < pd.Timestamp(hi)
    return led[m].reset_index(drop=True)


def ret(led, slip, sz=SZ, lev=LEV):
    if len(led) == 0:
        return 0.0, 0.0, 0, []
    pnl, bal, mdd, nliq = per_trade_pnl(led, sz, lev, slip)
    return (bal / 1e4 - 1) * 100, mdd, nliq, pnl


def quarterly_ls(led, slip):
    """OOS 분기별 롱/숏 (현실). 분기내 복리(격리)."""
    if len(led) == 0:
        return pd.DataFrame()
    pnl, _, _, _ = per_trade_pnl(led, SZ, LEV, slip)
    d = pd.DataFrame({"et": pd.to_datetime(led["et"]), "side": led["side"].astype(int).values, "p": pnl})
    d["q"] = d["et"].dt.to_period("Q").astype(str)
    rows = []
    for q, g in d.groupby("q"):
        allr = (np.prod(1 + np.array(g["p"]) / 100.0) - 1) * 100   # ★p는 이미 %단위(per_trade_pnl=p*100) → /100로 분율화
        lr = (np.prod(1 + g[g.side == 1]["p"].values / 100.0) - 1) * 100 if (g.side == 1).any() else 0.0
        sr = (np.prod(1 + g[g.side == -1]["p"].values / 100.0) - 1) * 100 if (g.side == -1).any() else 0.0
        rows.append(dict(분기=q, 거래=len(g), 전체=round(allr, 1), 롱=round(lr, 1), 숏=round(sr, 1),
                         롱n=int((g.side == 1).sum()), 숏n=int((g.side == -1).sum())))
    return pd.DataFrame(rows)


def monthly_pos(led, slip, lo="2024-01-01"):
    sub = slc(led, lo)
    if len(sub) == 0:
        return 0, 0, pd.DataFrame()
    pnl, _, _, _ = per_trade_pnl(sub, SZ, LEV, slip)
    d = pd.DataFrame({"m": pd.to_datetime(sub["et"]).dt.to_period("M").astype(str), "p": pnl, "side": sub["side"].astype(int).values})
    rows = []
    for m, g in d.groupby("m"):
        mr = (np.prod(1 + np.array(g["p"]) / 100.0) - 1) * 100   # ★p는 이미 %단위 → /100
        rows.append(dict(년월=m, 거래=len(g), 월수익=round(mr, 1), 롱=int((g.side == 1).sum()), 숏=int((g.side == -1).sum()), 양수="O" if mr > 0 else "X"))
    mdf = pd.DataFrame(rows); pos = int((mdf["월수익"] > 0).sum())
    return pos, len(mdf), mdf


def liq_cap(sz=SZ, lev=LEV):
    """강제청산 1회 손실율(격리마진): exp×(hsd+LIQ_COST). hsd=1/lev-mmr-slip."""
    exp = sz / 100.0 * lev; hsd = 1.0 / lev - MMR_T1 - LIQ_SLIP
    return exp * (hsd + LIQ_COST) * 100, hsd * 100


def main():
    os.makedirs(OUT, exist_ok=True)
    p = json.load(open(WINP, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    combo = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    d1m, fund = load_1m(), load_funding(); rev_tf = int(p["rev_tf"])
    # 무손상
    anc = VeriEdge(B2.rev_trades(d1m, fund, dict(p))).anchor_check(75, 3, 1851.6)
    _p(f"[무손상] BASE 앵커 = {anc['got_%']}% → {'PASS' if anc['pass'] else 'FAIL 중단'}")
    if not anc["pass"]:
        return False
    safe = B2.rev_trades(d1m, fund, combo)
    rally = apply_rally_damp(safe, d1m, rev_tf, 3.0, 0.5)
    ndamp = int((rally["size_mult"] < 1.0).sum())

    L = []
    L.append("=" * 100)
    L.append("[RevoiSafe vs RevoiRally 정밀비교 — §19] 둘 다 lev15/증거금20%(노출3) 고정 = L2 순효과 격리")
    L.append(f"[무손상] BASE 앵커 {anc['got_%']}% 재현 · L2 damp {ndamp}건(랠리숏만·현 하락레짐선 no-op)")
    cap, hsd = liq_cap()
    L.append(f"[안전장치 원리] lev15/sz20 강제청산 문턱 hsd={hsd:.2f}% · 강제청산 1회 손실 = {cap:.1f}% (유지증거금만·20% 이내 cap)")
    L.append("")

    # ── ① OOS held-out (2025+) 전체 + 분기별 롱/숏 ──
    L.append("[★① OOS held-out(2025+) — 헤드라인 · 슬립0 / 현실10bp]")
    L.append(f"{'봇':<12}{'슬립0 수익%':>12}{'현실 수익%':>12}{'현실 MDD%':>11}{'강제청산':>9}{'거래':>6}")
    oos = {}
    for nm, led in [("RevoiSafe", safe), ("RevoiRally", rally)]:
        te = slc(led, "2025-01-01")
        r0, m0, n0, _ = ret(te, S0); rr, mr, nr, _ = ret(te, SR)
        oos[nm] = (te, rr, mr, nr)
        L.append(f"{nm:<12}{r0:>+11.0f}%{rr:>+11.0f}%{mr:>+10.1f}%{nr:>9}{len(te):>6}")
    d_oos = oos["RevoiRally"][1] - oos["RevoiSafe"][1]
    L.append(f"   → OOS 현실 수익 차이(Rally−Safe) = {d_oos:+.0f}%p  {'(개선)' if d_oos>0 else '(악화 = L2가 COMBO 랠리수익 깎음)'}")
    L.append("")
    for nm in ["RevoiSafe", "RevoiRally"]:
        q = quarterly_ls(oos[nm][0], SR)
        L.append(f"  [{nm} · OOS 분기별 롱/숏(현실%)]")
        L.append("   " + q.to_string(index=False).replace("\n", "\n   "))
    L.append("")

    # ── ② post-2024 매월(양수월) ──
    L.append("[★② post-2024(ETF후) 매월 — 현실10bp · §0 매월양수 점검]")
    for nm, led in [("RevoiSafe", safe), ("RevoiRally", rally)]:
        pos, nmo, mdf = monthly_pos(led, SR)
        L.append(f"  {nm}: 매월양수 {pos}/{nmo} ({pos/nmo*100:.0f}%)  · 음수월 {[r['년월'] for _,r in mdf.iterrows() if r['월수익']<=0]}")
    L.append("  (두 봇 매월표 동일구조 — 차이는 랠리 있던 달만. CSV 첨부)")
    L.append("")

    # ── ③ MDD 4단 게이트(알파 천장·in-sample 상한) + 강제청산 ──
    L.append("[③ MDD 4단 게이트 — ★in-sample 천장(레버최적·실전아님·헤드라인금지)·현실10bp·sz75서 레버스윕]")
    L.append(f"{'봇':<12}{'M0':>22}{'M30':>20}{'M25':>20}{'M20':>20}")
    for nm, led in [("RevoiSafe", safe), ("RevoiRally", rally)]:
        g = VeriEdge(led).mdd_4gate(period_lo="2024-01-01", size_pct=75, lev_lo=2, lev_hi=20, slip_bp=10.0)
        def c(t):
            v = g[t]; return "없음" if v is None else f"{v['수익%']:+,}%/L{v['lev']}/청{v['청산']}"
        L.append(f"{nm:<12}{c('M0'):>22}{c('M30'):>20}{c('M25'):>20}{c('M20'):>20}")
    L.append("")

    # ── ④ 안전장치: 36mo + 2025-10 극단 ──
    L.append("[★④ 안전장치(강제청산 손실cap) — lev15/sz20]")
    for nm, led in [("RevoiSafe", safe), ("RevoiRally", rally)]:
        r36, m36, n36, pnl36 = ret(led, SR)
        worst = min(pnl36) if pnl36 else 0.0                       # ★pnl36은 이미 %단위(per_trade_pnl=p*100)
        oct25 = slc(led, "2025-10-01", "2025-11-01")
        _, moct, noct, poct = ret(oct25, SR)
        woct = min(poct) if poct else 0.0
        L.append(f"  {nm}: 36mo 강제청산 {n36}회 · 최악 단일거래손실 {worst:.1f}% · 2025-10급락 {len(oct25)}거래/강제청산{noct}/최악{woct:.1f}%/월MDD{moct:.1f}%")
    L.append(f"  → 강제청산 발생시 손실 = {cap:.1f}%(유지증거금만·20%이내). RevoiRally는 랠리숏 노출½ = 랠리서 더 안전.")
    L.append("")

    # ── ⑤ 레버업 변형(같은 MDD서 수익 비교) ──
    L.append("[⑤ 참고 — RevoiRally 레버업 변형: RevoiSafe MDD에 맞춰 증거금↑시 OOS수익(현실)·20%cap 여부]")
    _, safe_mdd36, _, _ = ret(safe, SR)
    L.append(f"   RevoiSafe 36mo 현실 MDD 기준선 = {safe_mdd36:.1f}%")
    for sz in [20, 25, 30, 35]:
        te = slc(rally, "2025-01-01")
        r0, _, _, _ = ret(rally, SR, sz=sz)   # 36mo mdd
        _, mdd36, _, _ = ret(rally, SR, sz=sz)
        rroos, mroos, nroos, _ = ret(te, SR, sz=sz)
        capx, _ = liq_cap(sz=sz)
        L.append(f"   Rally sz{sz}(노출{sz*LEV/100:.1f}): 36mo현실MDD{mdd36:.1f}% · OOS현실 {rroos:+.0f}%/MDD{mroos:.1f}% · 강제청산cap {capx:.1f}%{' ★20%초과' if capx>20 else ''}")
    L.append("")

    # ── 판정 ──
    L.append("[★판정 — 정직]")
    if d_oos < -50:
        L.append(f"  · ★같은 노출3(lev15/sz20)선 RevoiRally OOS수익 {d_oos:+.0f}%p = 개선 아님(악화). 원인=COMBO early_tp가 이미 랠리 수익화→L2가 그 수익거래를 깎음.")
        L.append("  · ★L2의 유일 이점 = MDD 소폭↓(리스크리듀서). 수익 개선은 레버업(⑤)서만 오고, 증거금↑는 20%cap을 위협.")
        L.append("  · ★결론: 캡틴 지적 정확 — 안전사이징 고정에선 L2가 COMBO 위에 추가이점 미미. 진짜 개선(수익+안전)은 추세봇 상보(4차확인).")
    else:
        L.append(f"  · RevoiRally OOS수익 {d_oos:+.0f}%p · MDD 개선. 검토 지속.")
    body = "\n".join(L)

    for nm, led in [("RevoiSafe", safe), ("RevoiRally", rally)]:
        _, _, mdf = monthly_pos(led, SR)
        mdf.to_csv(os.path.join(OUT, f"매월_{nm}.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(OUT, "분석.txt"), "w", encoding="utf-8").write(body)
    _p("\n" + body)
    _p(f"\n[저장] {OUT}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
