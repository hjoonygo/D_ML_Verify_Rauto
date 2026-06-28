# -*- coding: utf-8 -*-
# [back2tv_rev.py] REV 단독 + 격리마진·유지증거금·강제청산 레버사이징 탐색 → 4세팅 Back2TV (캡틴 지시 2026-06-24).
#   ★청산모델 = rauto_paper_engine 1:1(검증엔진): exp=size%/100*lev; mmr; hsd=1/lev-mmr-SLIP;
#     mae<=-hsd → 강제청산 p=-exp*(hsd+COST+|fund|), else p=R*exp. → 레버 과하면 청산=수익 안 늘어 '진짜' 최적레버.
#   탐색: REV파라미터(1회생성) × (lev,size%) 격자 스윕. 4승자:
#     ①MDD무제한 36개월최고 ②MDD무제한 1개월최고(단일최고월) ③MDD≤-25 36개월최고 ④MDD≤-25 1개월최고.
#   각 승자 → make_back2tv(통합표+Pine, bt_report 재사용). 같은 seed=재현.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
HERE = os.path.dirname(os.path.abspath(__file__))
MMR_T1, MMR_T2, TIER, COST, SLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005
LEVG = [3, 5, 8, 10, 13, 16, 20, 25, 30]
SZG = [10, 20, 30, 50, 75, 100]


def _p(*a): print(*a, flush=True)


def rev_trades(d1m, fund, p, capture_fills=False):
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                        er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                        arm_bars=p["arm"],
                        tp_frac=p.get("tp_frac", 0.0),               # ★COMBO: 구조 부분익절(opt-in)
                        early_tp_pct=p.get("early_tp_pct", 0.0),     # ★COMBO: 고정% 조기익절(opt-in, 260627_02)
                        early_frac=p.get("early_frac", 0.0),
                        capture_fills=capture_fills)


def liq_eval(R, MAE, FUND, MKEY, size_pct, lev):
    """검증엔진 1:1 격리마진 청산복리. 반환 (전체복리%, MDD%, 단일최고월%, 청산횟수)."""
    exp = size_pct / 100.0 * lev
    bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0
    mfac = {}
    for i in range(len(R)):
        mmr = MMR_T2 if exp * bal > TIER else MMR_T1
        hsd = 1.0 / lev - mmr - SLIP
        if MAE[i] <= -hsd:
            p = -exp * (hsd + COST + abs(FUND[i])); nliq += 1
        else:
            p = R[i] * exp
        bal *= (1.0 + p)
        if bal > peak: peak = bal
        dd = bal / peak - 1.0
        if dd < mdd: mdd = dd
        mfac[MKEY[i]] = mfac.get(MKEY[i], 1.0) * (1.0 + p)
        if bal <= 0:  # 완전소각
            return -100.0, -100.0, -100.0, nliq
    tot = (bal / 10000.0 - 1.0) * 100.0
    best_m = (max(mfac.values()) - 1.0) * 100.0 if mfac else 0.0
    return tot, mdd * 100.0, best_m, nliq


def sample(rng):
    return dict(rev_tf=int(rng.choice([240, 480, 720])), piv=int(rng.choice([20, 60, 240])),
                N=int(rng.integers(2, 9)), f1=float(rng.uniform(0.15, 0.45)), f2=float(rng.uniform(0.45, 0.65)),
                f3=float(rng.uniform(0.65, 0.92)), iam=float(rng.uniform(0.5, 3.0)),
                q=float(rng.uniform(0.2, 0.4)), qwin=int(rng.integers(20, 80)), arm=int(rng.integers(2, 12)))


def search(d1m, fund, NC):
    rng = np.random.default_rng(7)
    # 승자: (점수, p, lev, size, tot, mdd, bestm, nliq)
    W = {"f36": None, "f1m": None, "c36": None, "c1m": None}
    def upd(k, score, *rest):
        if W[k] is None or score > W[k][0]: W[k] = (score,) + rest
    for i in range(NC):
        p = sample(rng)
        try:
            T = rev_trades(d1m, fund, p)
        except Exception:
            continue
        if len(T) < 30: continue
        R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
        MK = pd.to_datetime(T["et"]).dt.to_period("M").astype(str).values
        for lev in LEVG:
            for sz in SZG:
                tot, mdd, bm, nl = liq_eval(R, MAE, FUND, MK, sz, lev)
                base = dict(p=p, lev=lev, sz=sz, tot=tot, mdd=mdd, bm=bm, nl=nl, ntr=len(T))
                upd("f36", tot, base); upd("f1m", bm, base)
                if mdd >= -25.0:
                    upd("c36", tot, base); upd("c1m", bm, base)
        if (i + 1) % 30 == 0: _p(f"  탐색 {i+1}/{NC}")
    return {k: v[1] for k, v in W.items() if v}


def make_back2tv(d1m, fund, w, name):
    """승자 1개 → REV거래 재생성(capture_fills) → bt_report 통합표+Pine 저장(Back2TV)."""
    import bt_report as BR, make_pine as MP, make_cases as MC
    from datetime import datetime
    p = w["p"]; cfg = dict(sig_tf=p["rev_tf"], pivot_tf=p["piv"], N=p["N"], fib1=p["f1"], fib2=p["f2"], fib3=p["f3"],
                           init_atr_mult=p["iam"], er_gate=0.0, size_pct=float(w["sz"]), lev=float(w["lev"]))
    T = rev_trades(d1m, fund, p, capture_fills=True)
    expo = cfg["size_pct"] / 100.0 * cfg["lev"]
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = len([d for d in os.listdir(BR.BTO) if d.startswith(today + "_")]) + 1
    base = f"{today}_{nn:02d}_{name}"; folder = os.path.join(BR.BTO, base); os.makedirs(folder, exist_ok=True)
    T.drop(columns=["fills"]).to_csv(os.path.join(folder, f"{base}_거래원장.csv"), index=False, encoding="utf-8-sig")
    L, an, ag = BR.per_trade(T, cfg); U = BR.unified_table(L)
    U.to_csv(os.path.join(folder, f"{base}_월별통합표.csv"), index=False, encoding="utf-8-sig")
    nemb, _, _, ntot = MP.build_pine(T, expo, out=os.path.join(folder, f"{base}.pine"), title=f"REV {name}")
    # ★거래 예시 6선(영문/한글 병기 + 고딩해설) — TV가시범위(=Pine 임베드 최근분)만. 캡틴 TV대조용(2026-06-25).
    cpng, ctxt, csel = MC.build_cases(T, p, d1m, folder, base, max_embed=nemb)
    if cpng is None: _p("  ⚠ 사례6선 생략: TV가시범위 거래<5 (침묵금지)")
    else: _p(f"  사례6선: {os.path.basename(cpng)} (채택 {[c[0][:6] for c in csel]})")
    ret, mdd, cal = an.metrics()
    def pf(s): g = s[s > 0].sum(); b = -s[s < 0].sum(); return g / b if b > 0 else np.inf
    head = (f"[Back2TV·REV단독] {base}\n[세팅] REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} "
            f"피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f} | REV분위{p['q']:.2f}/롤링{p['qwin']} arm{p['arm']}\n"
            f"[사이징] 레버={w['lev']}배 · 증거금={w['sz']}% · 노출={expo:.1f} (격리마진·유지증거금·강제청산)\n"
            f"[성적] 거래{len(L)}·승률{100*(L.net>0).mean():.0f}%·PF{pf(L.net):.2f}·복리{ret:+.0f}%(${an.bal:,.0f})"
            f"·MDD{mdd:.0f}%·강제청산{an.n_liq}회·단일최고월 +{w['bm']:.0f}%\n"
            f"[비용] 순손익${L.net.sum():+,.0f} = 손익금(무비용)${L.gross.sum():+,.0f} − 총비용${L.gross.sum()-L.net.sum():,.0f}")
    body = head + "\n\n[월별 통합표]\n" + U.to_string(index=False)
    open(os.path.join(BR.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{base}|Back2TV REV단독 레버{w['lev']}·복리{ret:+.0f}%·MDD{mdd:.0f}%·청산{an.n_liq}|src=back2tv_rev.py\n")
    _p("\n" + head)
    _p(f"[저장] {folder}\\  ·  Pine: {base}.pine → TV BTCUSDT.P·UTC·{p['rev_tf']//60 if p['rev_tf']%60==0 else p['rev_tf']}")
    return base


def main():
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    d1m = load_1m(); fund = load_funding()
    _p(f"[REV 단독 탐색 {NC}개] 격리마진 청산모델 · 레버{LEVG} × 증거금{SZG}")
    W = search(d1m, fund, NC)
    names = {"f36": "REV_MDDfree_36mo", "f1m": "REV_MDDfree_1mo", "c36": "REV_MDD25_36mo", "c1m": "REV_MDD25_1mo"}
    _p("\n===== 4승자 요약 =====")
    for k in ["f36", "f1m", "c36", "c1m"]:
        if k in W:
            w = W[k]; _p(f"[{names[k]}] 레버{w['lev']}·증거금{w['sz']}% → 복리{w['tot']:+.0f}%·MDD{w['mdd']:.0f}%·단일최고월+{w['bm']:.0f}%·청산{w['nl']}·거래{w['ntr']}")
    json.dump({names[k]: W[k] for k in W}, open(os.path.join(HERE, "back2tv_rev_winners.json"), "w"), default=float, indent=2, ensure_ascii=False)
    _p("\n===== Back2TV 4종 생성 =====")
    for k in ["f36", "f1m", "c36", "c1m"]:
        if k in W: make_back2tv(d1m, fund, W[k], names[k])


if __name__ == "__main__":
    main()
