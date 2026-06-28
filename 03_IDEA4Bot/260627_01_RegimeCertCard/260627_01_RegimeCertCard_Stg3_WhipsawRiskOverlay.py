# -*- coding: utf-8 -*-
# [260627_01_RegimeCertCard_Stg3_WhipsawRiskOverlay] ★휩소 리스크 오버레이 — §26 4단 최대수익(수익률 우선) (세션 260627_01_RegimeCertCard).
#   캡틴 지시: "임의로 MDD>-20 맞추지 말고, 휩소 등을 피하는 로직·설정값을 찾아 강제청산 확인하며
#              MDD무제한/MDD≥-25/MDD≥-20(+§26 M30)를 '수익률 우선'으로 찾아내라."
#   → R+P70 알파 베이스 + 진입 휩소-회피 로직 여러개(게이트/저변동/OI충격/저변동&OI충격/조합·skip/size↓) 각각
#     §26 4단(M0/M30/M25/M20) 레버×증거금 격자서 최대수익 사이징 탐색 + 강제청산 횟수. ON vs OFF 비교.
#   ★검증엔진 무수정 호출(§8·§15.1). 진입피처 전부 lookahead0(et시점 과거값). 비용=§24 RautoCEX 현실.
#   ★경계(§20): 36mo in-sample 천장. 채택=held-out·CPCV 별도(다음 Stg=워크포워드).
import os, sys, json
from datetime import datetime

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
import trendstack_signal_engine as TS
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK

WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
BASE = "260627_03_WhipsawRiskOverlay"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output")
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(ROOT, "00_WorkHstr", "00WorkHstr_INDEX.txt")
LEVG = [3, 4, 5, 6, 8, 10, 13, 16]
SZG = [30, 50, 55, 65, 75, 85, 100]
TIERS = [("M0(무제한)", -1e9), ("M30(≥-30)", -30.0), ("M25(≥-25)", -25.0), ("M20(≥-20)", -20.0)]
M20KEY = "M20(≥-20)"


def _p(*a):
    print(*a, flush=True)


def make_ledger(p, tp_frac, regime_factor, gate, d1m, fund):
    params = dict(p); params["tp_frac"] = tp_frac; params["regime_factor"] = regime_factor; params["gate"] = gate
    return REVoiBot(params).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)


def cost_real(T):
    R = T["R"].values.astype(float); F = T["fund"].values.astype(float)
    REA = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    fee = FeeModel(); sl = SlipModel(0.0, 1.0).market_exit_slip()
    return np.array([R[i] + MK + TK + F[i] - fee.entry_cost(False) - fee.exit_cost(REA[i]) - F[i]
                     - (sl if REA[i] != "tp" else 0.0) for i in range(len(R))])


def sized_w(Rc, MAE, FUND, lev, sz, w):
    """가중(w=1 유지/0 솎기/0.5 축소) 격리마진 사이징 → p, 강제청산mask, 전체%, MDD%."""
    exp0 = sz / 100.0 * lev; bal = 10000.0; peak = 10000.0; mdd = 0.0
    p = np.zeros(len(Rc)); liq = np.zeros(len(Rc), dtype=bool)
    for i in range(len(Rc)):
        if w[i] <= 0:
            continue                                   # 진입 솎기 = 거래 안 함(no-op)
        exp = exp0 * w[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        if MAE[i] <= -hsd:
            pp = -exp * (hsd + LIQ_COST + abs(FUND[i])); liq[i] = True
        else:
            pp = Rc[i] * exp
        bal *= (1.0 + pp); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0); p[i] = pp
    return p, liq, (bal / 1e4 - 1) * 100, mdd * 100


def entry_features(T, d1m, rev_tf):
    """진입시점(et) 피처 — 전부 과거값(lookahead0): 7일추세·ATR분위(rev_tf)·oi_z(24h)·추세역행."""
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000).astype("int64")
    mt = (d1m.index.values.astype("int64") // 1_000_000).astype("int64")
    oiz_arr = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce").values
    c = d1m["close"].values
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    tr = (dfx["high"] - dfx["low"]) / dfx["close"]
    atr = tr.rolling(14, min_periods=5).mean()
    atrp = atr.rolling(720, min_periods=120).rank(pct=True).values
    dfx_ms = (dfx.index.values.astype("int64") // 1_000_000).astype("int64")
    side = T["side"].astype(int).values
    n = len(T); oiz = np.zeros(n); apct = np.full(n, 0.5); trend = np.empty(n, dtype=object)
    for i in range(n):
        j = max(0, int(np.searchsorted(mt, et_ms[i], "right")) - 1)
        oiz[i] = oiz_arr[j] if not np.isnan(oiz_arr[j]) else 0.0
        ch = (c[j] / c[max(0, j - 10080)] - 1.0) * 100.0 if j > 0 else 0.0
        trend[i] = "up" if ch > 3 else ("down" if ch < -3 else "range")
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        apct[i] = atrp[k] if (k < len(atrp) and not np.isnan(atrp[k])) else 0.5
    ctr = np.array([(trend[i] == "up" and side[i] == -1) or (trend[i] == "down" and side[i] == 1) for i in range(n)])
    return dict(oiz=oiz, apct=apct, trend=trend, side=side, ctr=ctr)


def overlay_w(F, logic, Q=0.30, Z=1.0):
    """휩소-회피 로직 → 진입 가중 w. Q=저변동 ATR분위 임계, Z=OI충격 |oi_z| 임계."""
    n = len(F["side"]); w = np.ones(n)
    lowv = F["apct"] <= Q
    shock = np.abs(F["oiz"]) >= Z
    whip = lowv & shock                                   # ★저변동 AND OI충격 동시(WO 표적)
    ctr = F["ctr"]
    if logic == "OFF":
        pass
    elif logic == "GATE(역행솎기)":
        w[ctr] = 0
    elif logic == "LOWVOL(저변동솎기)":
        w[F["apct"] <= 0.20] = 0
    elif logic == "OISHOCK(OI충격솎기)":
        w[np.abs(F["oiz"]) >= 1.5] = 0
    elif logic == "WHIP(저변동&OI충격솎기)":
        w[whip] = 0
    elif logic == "GATE+WHIP(조합솎기)":
        w[ctr | whip] = 0
    elif logic == "WHIP_soft(축소0.5)":
        w[whip] = 0.5
    elif logic == "GATE_soft(역행축소0.5)":
        w[ctr] = 0.5
    elif logic == "GATE+WHIP_soft":
        w[ctr | whip] = 0.5
    return w


def tier_sweep(Rc, MAE, FUND, w):
    """레버×증거금 격자 → §26 4단 각 최대수익 사이징."""
    best = {k: None for k, _ in TIERS}
    for lev in LEVG:
        for sz in SZG:
            p, liq, tot, mdd = sized_w(Rc, MAE, FUND, lev, sz, w)
            for k, cap in TIERS:
                if mdd >= cap and (best[k] is None or tot > best[k]["tot"]):
                    best[k] = dict(lev=lev, sz=sz, tot=round(tot, 0), mdd=round(mdd, 1), nliq=int(liq.sum()), ntr=int((w > 0).sum()))
    return best


def main():
    _p(f"[{BASE}] 휩소 리스크 오버레이 — §26 4단 최대수익(수익률 우선)·강제청산 확인·MDD 임의클램프 금지")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    rev_tf = int(p["rev_tf"])
    # 베이스 = R+P70(rf1.0) 알파(최고 정직 단일 +8669%). 비교용 exit-tighten = rf1.4.
    T10 = make_ledger(p, 0.7, 1.0, False, d1m, fund); Rc10 = cost_real(T10)
    MAE10 = T10["mae"].values.astype(float); F10 = T10["fund"].values.astype(float)
    T14 = make_ledger(p, 0.7, 1.4, False, d1m, fund); Rc14 = cost_real(T14)
    MAE14 = T14["mae"].values.astype(float); F14 = T14["fund"].values.astype(float)
    _p(f"  베이스 R+P70(rf1.0) {len(T10)}거래 · exit-tighten(rf1.4) {len(T14)}거래")
    F = entry_features(T10, d1m, rev_tf)
    # 진입피처 분포(휩소 표적 확인)
    lowv = F["apct"] <= 0.30; shock = np.abs(F["oiz"]) >= 1.0; whip = lowv & shock
    _p(f"  진입피처: 저변동(≤Q30) {lowv.mean()*100:.0f}% · OI충격(|z|≥1) {shock.mean()*100:.0f}% · 저변동&OI충격 {whip.mean()*100:.0f}% · 추세역행 {F['ctr'].mean()*100:.0f}%")

    # 무손상: rf1.0 OFF M0천장 = ? (앵커는 tp0; 여기선 베이스 일관성만 확인 — OFF 전체수익 lev6/55)
    _, _, base_tot, base_mdd = sized_w(Rc10, MAE10, F10, 6.0, 55.0, np.ones(len(T10)))
    _p(f"  [무손상] R+P70 OFF lev6/55 현실 = {base_tot:+.0f}%/MDD{base_mdd:.0f}% (Stg1 카드 R+P70단순 +8669%/-21% 일치 기대)")
    if abs(base_tot - 8669) > 200:
        _p("  ❌ 무손상 경고 — 베이스 불일치. 중단."); return False

    LOGICS = ["OFF", "GATE(역행솎기)", "LOWVOL(저변동솎기)", "OISHOCK(OI충격솎기)", "WHIP(저변동&OI충격솎기)",
              "GATE+WHIP(조합솎기)", "WHIP_soft(축소0.5)", "GATE_soft(역행축소0.5)", "GATE+WHIP_soft"]
    rows = []
    for lg in LOGICS:
        w = overlay_w(F, lg)
        b = tier_sweep(Rc10, MAE10, F10, w)
        rows.append((lg, b))
    # exit-tighten(rf1.4) 참고 — 자체 오버레이라 OFF만
    b14 = tier_sweep(Rc14, MAE14, F14, np.ones(len(T14)))
    rows.append(("EXIT_TIGHTEN(rf1.4)", b14))

    # ── 보고(§19 헤드라인=수익률, §26 4단·강제청산) ──
    L = []
    L.append(f"[휩소 리스크 오버레이 — §26 4단 최대수익(수익률 우선)] {BASE}")
    L.append("[조건] 베이스=R+P70(rf1.0) 알파 · 진입 휩소-회피 오버레이(lookahead0) · 현실비용(§24 RautoCEX) · 36mo in-sample 천장(§20)")
    L.append("[지시준수] MDD 임의클램프 안 함 — 각 로직의 레버×증거금 격자서 §26 4단 각 '최대수익' 사이징 탐색 + 강제청산 횟수.")
    L.append(f"[휩소 표적] 저변동(ATR≤Q30) & OI충격(|oi_z|≥1) 동시 = 진입의 {whip.mean()*100:.0f}% · 추세역행 {F['ctr'].mean()*100:.0f}%")
    L.append("")
    L.append("[★§26 4단 최대수익 — 로직별 (수익률% /MDD /강제청산 /레버·증거금)]")

    def cell(v):
        if not v:
            return "-"
        return f"{v['tot']:+.0f}% /{v['mdd']:.0f}/청{v['nliq']} L{v['lev']:.0f}/{v['sz']:.0f}"
    hdr = f"{'휩소-회피 로직':<22}"
    for k, _ in TIERS:
        hdr += f"{k:>27}"
    L.append(hdr)
    for lg, b in rows:
        line = f"{lg:<22}"
        for k, _ in TIERS:
            line += f"{cell(b[k]):>27}"
        L.append(line)
    L.append(f"  거래수: OFF {rows[0][1][M20KEY]['ntr'] if rows[0][1][M20KEY] else '-'} → 솎기로직별 상이(거래수↓=솎은 것).")
    L.append("")
    # M20(인증) 챔피언 로직 선정
    m20 = [(lg, b[M20KEY]["tot"], b[M20KEY]) for lg, b in rows if b[M20KEY]]
    m20.sort(key=lambda x: -x[1])
    off20 = next((b[M20KEY]["tot"] for lg, b in rows if lg == "OFF" and b[M20KEY]), None)
    L.append("[★M20(실거래자격) 최대수익 순위 — 수익률 우선]")
    for lg, tot, v in m20[:5]:
        d = (tot - off20) if off20 is not None else 0
        L.append(f"  {lg:<22} {tot:+.0f}% · MDD{v['mdd']:.0f}% · 강제청산{v['nliq']} · L{v['lev']:.0f}/{v['sz']:.0f} · 거래{v['ntr']}  (OFF대비 {d:+.0f}%p)")
    L.append("")
    L.append("[판정]")
    bestlg = m20[0]
    L.append(f"  · ★M20 최대수익 로직 = {bestlg[0]} ({bestlg[1]:+.0f}%/MDD{bestlg[2]['mdd']:.0f}%/강제청산{bestlg[2]['nliq']}) vs OFF {off20:+.0f}% → {'개선' if bestlg[1] > (off20 or 0) else '개선못함'}")
    L.append("  · ★MDD를 억지로 맞춘 게 아니라 '휩소-회피 로직 + 레버 사이징'으로 4단 천장을 본 것(캡틴 지시).")
    L.append("  · ★경계: in-sample 천장 = 과적합 상한. 채택 = held-out·CPCV 표준6 별도통과(다음 Stg=워크포워드 정직검증).")
    body = "\n".join(L)

    folder = os.path.join(OUTDIR, BASE); os.makedirs(folder, exist_ok=True)
    csv_rows = []
    for lg, b in rows:
        for k, _ in TIERS:
            v = b[k]
            if v:
                csv_rows.append(dict(로직=lg, MDD단계=k, 수익률=v["tot"], MDD=v["mdd"], 강제청산=v["nliq"], 레버=v["lev"], 증거금=v["sz"], 거래수=v["ntr"]))
    pd.DataFrame(csv_rows).to_csv(os.path.join(folder, f"{BASE}_4단최대수익.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(folder, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|휩소 리스크 오버레이 §26 4단 최대수익(수익률우선·강제청산확인): "
                f"M20최대 {bestlg[0]} {bestlg[1]:+.0f}%/MDD{bestlg[2]['mdd']:.0f}% vs OFF {off20:+.0f}%|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {folder}\\  · 4단최대수익.csv · 분석.txt")
    return True


if __name__ == "__main__":
    main()
