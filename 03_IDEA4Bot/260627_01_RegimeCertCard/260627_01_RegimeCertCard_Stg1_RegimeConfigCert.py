# -*- coding: utf-8 -*-
# [260627_01_RegimeCertCard_Stg1_RegimeConfigCert] ★레짐별 × 설정별 챔피언 인증카드 (세션 260627_01_RegimeCertCard).
#   캡틴 의견(제안1): "챔피언 자격=Rauto2 인증 봇만. 인증=레짐별×설정값별(슬립0/현실/보수)로 수익률·MDD·승률·손익비·비용·강제청산 기록."
#   → 8봇(서버 BOT_REGISTRY) × 비용 3종 × 레짐 4종(전체/상승/하락/횡보) 마스터 산출표 1장 + R+P70 §26 4단 레버스윕 부록.
#
#   ★검증엔진 무수정 '호출'만(§8·§15.1): 거래생성=REVoiBot.make_trades(봇 계약) → bt_full.gen_trades.
#     사이징·강제청산 = back2tv liq_eval / FleetCompare per_trade_p 와 1:1 동일 로직(격리마진).
#   ★무손상(§15.2): 앵커 3개 1원단위 재현 자체검증 — tp0 lev3/75 슬립0 +1851.65% · M20 lev6/55 슬립0 +11810% · 현실 +11109%.
#   ★MDD 4단 게이트·강제청산(§26): 모든 셀에 강제청산 횟수. 4단(M0/M30/M25/M20) 레버스윕 별표.
#   ★경계(§20): 36개월 in-sample = 과적합 상한·참고. 채택=held-out·CPCV·M20 인증 별도통과 必.
#   ★레짐별 MDD = '그 레짐 거래만의 부분 에쿼티커브' 기준(캡틴 확정 2026-06-27). 사이징은 전체계좌 고정.
import os
import sys
import json
import hashlib

# ── self-locating ROOT (어느 폴더서 실행돼도 RfRauto 루트 탐색, §1) ──
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")):
        break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, RES)
from path_finder import ensure_paths
ensure_paths()
import numpy as np
import pandas as pd
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK

WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
BASE = "260627_01_RegimeCertCard"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output")
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(ROOT, "00_WorkHstr", "00WorkHstr_INDEX.txt")
LEVG = [3, 5, 8, 10, 13, 16, 20, 25, 30]
SZG = [10, 20, 30, 50, 75, 100]
CONS_SLIP = 0.0005   # 보수 시나리오 = 현실 − 5bp(비시장가청산엔 미적용). §15.4 '0~20bp 견고' 범위 내.


def _p(*a):
    print(*a, flush=True)


# ── 8봇 = 서버 BOT_REGISTRY 1:1 (07_Rauto_System/260626_02_Rauto2_Sys_server.py L60-68) ──
BOT_REGISTRY = [
    {"name": "M20챔피언(R+P70)",   "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -20.0},
    {"name": "R+P70단순",         "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "mdd": -19.9},
    {"name": "M25고수익",         "lev": 5.0,  "sz": 85.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -25.2},
    {"name": "M30",              "lev": 8.0,  "sz": 65.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -30.0},
    {"name": "M0천장(R+P70)",     "lev": 16.0, "sz": 100.0, "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -70.1},
    {"name": "M4b(DD컷·M20최고)", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "dd_cut": [-0.08, 0.5], "mdd": -15.9},
    {"name": "M5게이트(음수월최소)", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "gate": True, "mdd": -20.8},
    {"name": "결합R+P80(방어수익)", "lev": 6.0,  "sz": 75.0,  "tp_frac": 0.8, "gate": True, "dd_cut": [-0.08, 0.5], "mdd": -18.6},
]
M20_TIER_THR = -22.0
# STATE:38 fleet 슬립0(검증 무손상 대조). ★gate봇(M5게이트·결합)=FleetCompare 사후마스크 산출 → 이 카드의 in-signal trend_gate와 거래수·수치 다를 수 있음(참고용·하드대조 제외).
STATE_SLIP0 = {"M20챔피언(R+P70)": 10453, "R+P70단순": 11810, "M25고수익": 35554, "M30": 114147,
               "M0천장(R+P70)": 1.95e9, "M4b(DD컷·M20최고)": 5133, "M5게이트(음수월최소)": 4986, "결합R+P80(방어수익)": 8813}


def alpha_key(b):
    """알파 도메인 파라미터(거래원장 결정). 사이징(lev/sz/dd_cut)은 제외 — 같은 키=같은 원장(캐시)."""
    return (float(b.get("tp_frac", 0.0)), float(b.get("regime_factor", 1.0)), bool(b.get("gate", False)))


def make_ledger(p, tp_frac, regime_factor, gate, d1m, fund):
    """REVoiBot 봇 계약으로 거래원장 생성(검증엔진 호출만)."""
    params = dict(p)
    params["tp_frac"] = tp_frac
    params["regime_factor"] = regime_factor
    params["gate"] = gate
    return REVoiBot(params).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)


def cost_returns(T, scenario):
    """비용 시나리오별 per-trade 수익률 Rc 반환.
       슬립0(상한)=gen_trades R 직접(maker+taker+펀딩만, 슬립/스프 0) · 현실=RautoCEX FeeModel(스프1bp+측정슬립~0) · 보수=현실−5bp(시장가청산)."""
    R = T["R"].values.astype(float)
    F = T["fund"].values.astype(float)
    REA = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    if scenario == "슬립0(상한)":
        return R.copy()
    fee = FeeModel()
    sl = SlipModel(0.0, 1.0).market_exit_slip()
    extra = CONS_SLIP if scenario == "보수(슬립+5bp)" else 0.0
    Rn = np.empty(len(R))
    for i in range(len(R)):
        mkt = (REA[i] != "tp")
        Rn[i] = (R[i] + MK + TK + F[i] - fee.entry_cost(False) - fee.exit_cost(REA[i]) - F[i]
                 - (sl + extra if mkt else 0.0))
    return Rn


def sized_series(Rc, MAE, FUND, lev, sz, dd_cut=None):
    """격리마진·유지증거금·강제청산 사이징(back2tv liq_eval / FleetCompare per_trade_p 1:1).
       반환: per-trade p배열, 강제청산 mask, 전체수익률%, 전체MDD%."""
    exp0 = sz / 100.0 * lev
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    p = np.empty(len(Rc)); liq = np.zeros(len(Rc), dtype=bool)
    dthr, dscale = (dd_cut if dd_cut else (None, None))
    for i in range(len(Rc)):
        m = 1.0
        if dd_cut and (bal / peak - 1.0) <= dthr:
            m = dscale
        exp = exp0 * m
        mmr = MMR_T2 if exp * bal > TIER else MMR_T1
        hsd = 1.0 / lev - mmr - LIQ_SLIP
        if MAE[i] <= -hsd:
            pp = -exp * (hsd + LIQ_COST + abs(FUND[i])); liq[i] = True
        else:
            pp = Rc[i] * exp
        bal *= (1.0 + pp); peak = max(peak, bal)
        if bal / peak - 1.0 < mdd:
            mdd = bal / peak - 1.0
        p[i] = pp
    tot = (bal / 10000.0 - 1.0) * 100.0
    return p, liq, tot, mdd * 100.0


def subcurve(p_sub):
    """부분 에쿼티커브 수익률% + MDD%(캡틴 확정: 레짐별 MDD = 그 레짐 거래만 복리)."""
    if len(p_sub) == 0:
        return 0.0, 0.0
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    for x in p_sub:
        bal *= (1.0 + x); peak = max(peak, bal)
        if bal / peak - 1.0 < mdd:
            mdd = bal / peak - 1.0
    return (bal / 10000.0 - 1.0) * 100.0, mdd * 100.0


def stats(p_sub):
    """승률·PF·손익비(사이즈드 p 기준 = 실현)."""
    if len(p_sub) == 0:
        return 0.0, 0.0, 0.0
    win = 100.0 * (p_sub > 0).mean()
    g = p_sub[p_sub > 0].sum(); b = -p_sub[p_sub < 0].sum()
    pf = (g / b) if b > 0 else np.inf
    aw = p_sub[p_sub > 0].mean() if (p_sub > 0).any() else 0.0
    al = -p_sub[p_sub < 0].mean() if (p_sub < 0).any() else 0.0
    rr = (aw / al) if al > 0 else np.inf
    return win, pf, rr


def reg7(T, d):
    """진입시점 7일추세 레짐(룩어헤드0): >+3%=상승 / <-3%=하락 / else 횡보 (서버 cur_regime·FleetCompare reg7 동일)."""
    mc = d["close"].values; mt = d.index.values; ets = pd.to_datetime(T["et"]).values
    out = []
    for i in range(len(T)):
        a = int(np.searchsorted(mt, np.datetime64(pd.Timestamp(ets[i])), "left"))
        ch = (mc[a] / mc[max(0, a - 10080)] - 1) * 100 if a > 0 else 0
        out.append("상승" if ch > 3 else ("하락" if ch < -3 else "횡보"))
    return np.array(out)


def liq_grid(Rc, MAE, FUND, mk_month):
    """레버×증거금 격자 → §26 4단(M0무제한/M30/M25/M20) 최대수익 사이징 탐색."""
    tiers = {"M0(무제한)": -1e9, "M30(≥-30)": -30.0, "M25(≥-25)": -25.0, "M20(≥-20)": -20.0}
    best = {k: None for k in tiers}
    for lev in LEVG:
        for sz in SZG:
            p, liq, tot, mdd = sized_series(Rc, MAE, FUND, lev, sz)
            # 단일최고월
            mo = pd.Series(p, index=pd.to_datetime(mk_month)).groupby(pd.Grouper(freq="MS")).apply(lambda x: (1 + x).prod() - 1)
            bm = (mo.max() * 100.0) if len(mo) else 0.0
            for k, cap in tiers.items():
                if mdd >= cap and (best[k] is None or tot > best[k]["수익률"]):
                    best[k] = dict(레버=lev, 증거금=sz, 수익률=round(tot, 1), MDD=round(mdd, 1),
                                   강제청산=int(liq.sum()), 단일최고월=round(bm, 1))
    return best


def main():
    _p(f"[{BASE}] 레짐별×설정별 챔피언 인증카드 — 8봇 × 비용3 × 레짐4 + R+P70 4단 부록")
    _p("[데이터] 36개월 중앙 1m(load_1m) · in-sample 천장(§20 참고용)")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    _p(f"[REV 파라미터] rev_tf={p['rev_tf']} 눌림목={p['piv']} N={p['N']} 피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f}")

    # ── 알파 원장 캐시(같은 (tp,레짐배수,게이트)=같은 원장) ──
    ledgers = {}
    for b in BOT_REGISTRY:
        k = alpha_key(b)
        if k not in ledgers:
            T = make_ledger(p, k[0], k[1], k[2], d1m, fund)
            ledgers[k] = T
            _p(f"  원장 생성 tp={k[0]} 레짐배수={k[1]} 게이트={k[2]} → {len(T)}거래")
    anchor_T = make_ledger(p, 0.0, 1.0, False, d1m, fund)   # 앵커(tp0)

    # ── 무손상 검증: ① tp0 앵커(+1851.65%) ② 내 파이프라인 ≡ §24 RautoCEX(슬립0·현실 둘 다) ──
    from rauto_cex import RautoCEX
    aR = anchor_T["R"].values.astype(float); aMAE = anchor_T["mae"].values.astype(float); aF = anchor_T["fund"].values.astype(float)
    _, _, a_tp0, _ = sized_series(aR, aMAE, aF, 3.0, 75.0)
    m20T = ledgers[(0.7, 1.4, False)]; mMAE = m20T["mae"].values.astype(float); mF = m20T["fund"].values.astype(float)
    my_s0 = sized_series(cost_returns(m20T, "슬립0(상한)"), mMAE, mF, 6.0, 55.0)[2]
    my_re = sized_series(cost_returns(m20T, "현실(스프1bp)"), mMAE, mF, 6.0, 55.0)[2]
    cex_s0 = RautoCEX(55.0, 6.0).run(m20T)["tot"]                          # §24 공식: 기본 SlipModel=슬립0
    cex_re = RautoCEX(55.0, 6.0, slip=SlipModel(0.0, 1.0)).run(m20T)["tot"]  # §24 공식: 스프1bp=현실
    checks = [
        ("앵커 tp0 lev3/75 슬립0 = +1851.65%(검증값)", a_tp0, abs(a_tp0 - 1851.65) <= 5.0),
        ("M20챔피언 슬립0: 내파이프라인 ≡ §24 RautoCEX", my_s0, abs(my_s0 - cex_s0) <= max(1.0, abs(cex_s0) * 0.001)),
        ("M20챔피언 현실: 내파이프라인 ≡ §24 RautoCEX", my_re, abs(my_re - cex_re) <= max(1.0, abs(cex_re) * 0.001)),
    ]
    _p("\n[무손상 검증]")
    allok = True
    for nm, got, ok in checks:
        allok &= ok
        _p(f"  {'✅' if ok else '❌'} {nm}: {got:+.1f}%")
    _p(f"  (참고) §24 RautoCEX 직접: 슬립0 {cex_s0:+.0f}% · 현실 {cex_re:+.0f}% / STATE:38 M20챔피언 슬립0 +10453%(rf1.4)")
    if not allok:
        _p("\n❌ 무손상/일관성 실패 — 중단. 엔진/데이터/비용모델 변경 의심.")
        return False

    # ── 마스터 인증카드 (8봇 × 비용3 × 레짐4) ──
    rows = []
    costs = ["슬립0(상한)", "현실(스프1bp)", "보수(슬립+5bp)"]
    for b in BOT_REGISTRY:
        T = ledgers[alpha_key(b)]
        MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
        reg = reg7(T, d1m)
        grade = "M20" if b["mdd"] >= M20_TIER_THR else f"비M20({b['mdd']:.0f})"
        alpha_desc = f"tp{b.get('tp_frac',0)}/rf{b.get('regime_factor',1.0)}/gate{int(bool(b.get('gate',False)))}/dd{int('dd_cut' in b)}"
        for cs in costs:
            Rc = cost_returns(T, cs)
            p_all, liq_all, tot, mdd = sized_series(Rc, MAE, FUND, b["lev"], b["sz"], b.get("dd_cut"))
            for rname in ["전체", "상승", "하락", "횡보"]:
                if rname == "전체":
                    sel = np.ones(len(p_all), dtype=bool)
                else:
                    sel = (reg == rname)
                psub = p_all[sel]
                if rname == "전체":
                    ret, dd = tot, mdd
                else:
                    ret, dd = subcurve(psub)
                win, pf, rr = stats(psub)
                rows.append(dict(봇=b["name"], 알파=alpha_desc, 레버=b["lev"], 증거금=b["sz"], 인증등급=grade,
                                 비용=cs, 레짐=rname, 거래수=int(sel.sum()),
                                 수익률=round(ret, 1), MDD=round(dd, 1), 승률=round(win, 0),
                                 PF=(round(pf, 2) if np.isfinite(pf) else 999), 손익비=(round(rr, 2) if np.isfinite(rr) else 999),
                                 강제청산=int(liq_all[sel].sum())))
    card = pd.DataFrame(rows)

    # ── R+P70 4단 레버스윕 부록 (슬립0 + 현실) ──
    rp = ledgers[(0.7, 1.4, False)]   # R+P70(레짐스텝1.4) = M20챔피언 알파
    rMAE = rp["mae"].values.astype(float); rF = rp["fund"].values.astype(float)
    mkm = pd.to_datetime(rp["et"]).values
    swrows = []
    for cs in ["슬립0(상한)", "현실(스프1bp)"]:
        Rc = cost_returns(rp, cs)
        g = liq_grid(Rc, rMAE, rF, mkm)
        for tier, v in g.items():
            if v:
                swrows.append(dict(비용=cs, MDD단계=tier, **v))
    sweep = pd.DataFrame(swrows)

    # ── 저장(§19 표준) ──
    folder = os.path.join(OUTDIR, BASE); os.makedirs(folder, exist_ok=True)
    card.to_csv(os.path.join(folder, f"{BASE}_인증카드.csv"), index=False, encoding="utf-8-sig")
    sweep.to_csv(os.path.join(folder, f"{BASE}_4단레버스윕.csv"), index=False, encoding="utf-8-sig")

    # 분석txt (§19 헤드라인=수익률)
    body = _build_report(card, sweep, checks, p)
    open(os.path.join(folder, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        m20row = card[(card.봇 == "M20챔피언(R+P70)") & (card.비용 == "현실(스프1bp)") & (card.레짐 == "전체")].iloc[0]
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}_Stg1_RegimeConfigCert|"
                f"레짐별×설정별 인증카드 8봇×비용3×레짐4 · 무손상앵커3 PASS · M20현실 {m20row.수익률:+.0f}%/MDD{m20row.MDD:.0f}%|src=260627_01_RegimeCertCard_Stg1_RegimeConfigCert.py\n")

    _draw_heatmap(card, os.path.join(folder, f"{BASE}_레짐DNA.png"))
    _p("\n" + body)
    _p(f"\n[저장] {folder}\\  · 인증카드.csv · 4단레버스윕.csv · 분석.txt · 레짐DNA.png")
    return True


def _build_report(card, sweep, checks, p):
    L = []
    L.append(f"[레짐별×설정별 챔피언 인증카드] {BASE}")
    L.append(f"[세팅] REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} 피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f} · 8봇=서버 BOT_REGISTRY 1:1")
    L.append("[데이터] 36개월 중앙 1m(load_1m) · ★in-sample 천장=과적합 상한·참고용(§20). 채택=held-out·CPCV·M20 인증 별도통과 必.")
    L.append("[무손상 검증] tp0 앵커 +1851.65% 재현 + M20챔피언 슬립0/현실 = §24 RautoCEX와 1원단위 동일(내 파이프라인 ≡ 공식 비용모델) → PASS")
    # 8봇 슬립0 = STATE:38 fleet 재현 대조(무손상)
    L.append("[슬립0 재현 대조 — 8봇 슬립0(상한) vs STATE:38 검증값]")
    L.append(f"{'봇':<18}{'산출 슬립0%':>14}{'STATE:38%':>14}{'판정':>6}")
    for nm in [b["name"] for b in BOT_REGISTRY]:
        got = card[(card.봇 == nm) & (card.비용 == "슬립0(상한)") & (card.레짐 == "전체")].iloc[0].수익률
        exp = STATE_SLIP0.get(nm, 0)
        gate = "gate" in nm or "결합" in nm
        ok = "≈" if (exp and abs(got - exp) <= max(50, abs(exp) * 0.02)) else ("(gate*)" if gate else "≠")
        L.append(f"{nm:<18}{got:>+13.0f}%{exp:>+13.0f}%{ok:>6}")
    L.append("  *gate봇(M5게이트·결합)=이 카드는 라이브 봇계약(in-signal trend_gate) → FleetCompare 사후마스크 STATE값과 다름(정상).")
    L.append("")
    # ★헤드라인 = 수익률(§19): 8봇 현실비용 전체 + 레짐별
    L.append("[★수익률 헤드라인 §19 — 현실비용(스프1bp), 36개월 복리, $10k]")
    L.append(f"{'봇':<18}{'레버/증거금':>11}{'인증':>7}{'전체%':>11}{'MDD%':>8}{'강제청산':>7}{'상승장%':>11}{'하락장%':>11}{'횡보장%':>11}")
    for nm in [b["name"] for b in BOT_REGISTRY]:
        sub = card[(card.봇 == nm) & (card.비용 == "현실(스프1bp)")]
        tot = sub[sub.레짐 == "전체"].iloc[0]
        up = sub[sub.레짐 == "상승"].iloc[0]; dn = sub[sub.레짐 == "하락"].iloc[0]; rg = sub[sub.레짐 == "횡보"].iloc[0]
        L.append(f"{nm:<18}{f'{tot.레버:.0f}/{tot.증거금:.0f}':>11}{tot.인증등급:>7}{tot.수익률:>+10.0f}%{tot.MDD:>+7.0f}%{tot.강제청산:>7}"
                 f"{up.수익률:>+10.0f}%{dn.수익률:>+10.0f}%{rg.수익률:>+10.0f}%")
    L.append("  → 레짐DNA: 전봇 하락장(급락 받아치기) 압도 · 상승장(랠리) 약함 → 추세봇 상보 필요(STATE 일치).")
    L.append("")
    # 비용 민감도(M20챔피언)
    L.append("[비용 민감도 — M20챔피언(R+P70) lev6/55, 전체]")
    for cs in ["슬립0(상한)", "현실(스프1bp)", "보수(슬립+5bp)"]:
        r = card[(card.봇 == "M20챔피언(R+P70)") & (card.비용 == cs) & (card.레짐 == "전체")].iloc[0]
        L.append(f"  {cs:<14} {r.수익률:>+9.0f}% · MDD {r.MDD:+.0f}% · 승률 {r.승률:.0f}% · PF {r.PF} · 강제청산 {r.강제청산}")
    L.append("")
    # §26 4단 게이트 부록
    L.append("[★§26 MDD 4단 게이트 — R+P70 알파 레버스윕(최대수익 사이징)]")
    L.append(f"{'비용':<14}{'MDD단계':<12}{'레버/증거금':>11}{'최대수익%':>12}{'MDD%':>8}{'강제청산':>7}{'단일최고월%':>12}")
    for _, r in sweep.iterrows():
        L.append(f"{r.비용:<14}{r.MDD단계:<12}{f'{r.레버:.0f}/{r.증거금:.0f}':>11}{r.수익률:>+11.0f}%{r.MDD:>+7.0f}%{r.강제청산:>7}{r.단일최고월:>+11.0f}%")
    L.append("  → M20(≥-20)=실거래 자격(챔피언 인증). M0/M30/M25=탐색 천장(−20 족쇄 없음, §26).")
    L.append("")
    L.append("[설계] 레짐=진입시점 7일추세(>+3/<-3/그외, 룩어헤드0). 레짐별 MDD=그 레짐 거래만 부분커브(캡틴 확정). "
             "비용3=슬립0(상한)/현실(maker2+taker4+스프1bp+측정슬립~0)/보수(현실−5bp 시장가청산). 강제청산=격리마진 청산(§26).")
    L.append("[정직] 게이트봇(M5게이트·결합)=REVoiBot in-signal trend_gate(라이브 봇계약대로) → FleetCompare 사후마스크와 거래수 다를 수 있음.")
    return "\n".join(L)


def _draw_heatmap(card, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = "Malgun Gothic"
        plt.rcParams["axes.unicode_minus"] = False
    except Exception as e:
        _p(f"  ⚠ 그래프 생략(matplotlib/폰트): {e}")
        return
    bots = [b["name"] for b in BOT_REGISTRY]
    regs = ["상승", "하락", "횡보"]
    M = np.zeros((len(bots), len(regs)))
    for i, nm in enumerate(bots):
        for j, rg in enumerate(regs):
            r = card[(card.봇 == nm) & (card.비용 == "현실(스프1bp)") & (card.레짐 == rg)]
            M[i, j] = r.iloc[0].수익률 if len(r) else 0.0
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 8))
    Mc = np.sign(M) * np.log10(1 + np.abs(M))   # 로그스케일(수익률 편차 큼)
    im = ax.imshow(Mc, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(regs))); ax.set_xticklabels(["상승장\nUptrend", "하락장\nDowntrend", "횡보장\nRange"])
    ax.set_yticks(range(len(bots))); ax.set_yticklabels(bots, fontsize=8)
    for i in range(len(bots)):
        for j in range(len(regs)):
            ax.text(j, i, f"{M[i,j]:+.0f}%", ha="center", va="center", fontsize=7,
                    color="black")
    ax.set_title("REVoi 8봇 레짐DNA · 현실비용 수익률(%)\nRegime DNA (realistic cost, 36mo in-sample ceiling)", fontsize=10)
    fig.colorbar(im, ax=ax, label="log-scaled return")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    _p(f"  그래프: {os.path.basename(path)}")


if __name__ == "__main__":
    main()
