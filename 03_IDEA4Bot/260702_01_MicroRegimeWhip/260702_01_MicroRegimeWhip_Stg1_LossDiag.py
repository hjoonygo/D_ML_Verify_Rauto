# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg1_LossDiag] ★휩소 손실지도 진단 (세션 260702_01_MicroRegimeWhip · 착수 A=진단먼저).
#   캡틴 지시(2026-07-01): 라이브 '하락'레짐서 챔피언 -2.24%인데 이름표 +39% → 7일추세 ±3% 3분류가
#     '급락(REVoi 승)'과 '휩소/약한하락(REVoi 패)'을 down 한 칸으로 묶음. 필터 만들기 전에 데이터로
#     '어느 미세레짐이 손실 무더기인지' 먼저 못박는다(WHIP_soft 과적합 증발 전례 → 진단 우선).
#   ★진단(수익률 주장 아님·in-sample 분해). 필터 확정 안 함(다음 Stg=held-out·CPCV 표준6).
#   ★검증엔진만(§8·§15.1): REVoi_bot.make_trades 호출·봇 재구현0. 원장은 '읽기'만 → 무손상.
#   ★피처 전부 causal(진입봉 직전 완성 4H봉까지·shift1 = lookahead0 = 라이브 계산가능).
#   ★config 2종 병기(캡틴): BASE(tp0/early0=앵커) + COMBO(tp_frac0.7+early_tp1.0%=§9 챔피언).
#   ★전체 36mo + post-2024(ETF후) 두 뷰(§19·memory#5/#7).
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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fib_replay_1m import load_1m, load_funding, DATA
from REVoi_bot import REVoiBot
from veri_edge import VeriEdge
import trendstack_signal_engine as TS

BASE = "260702_01_MicroRegimeWhip_Stg1_LossDiag"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", BASE)
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
ANCHOR = 1851.6491162901439            # BASE tp0/early0 lev3/sz75 슬립0 (무손상 기준값)
ETF = pd.Timestamp("2024-01-01")
W4 = 42                                 # 7일 = 42개 4H봉 (7일추세 분류기와 동일 창)


def _p(*a):
    print(*a, flush=True)


# ── causal 미세레짐 4H 피처 (진입봉 직전 완성봉까지 = shift1 = lookahead0) ──
def build_feat4(d1m, rev_tf):
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    c4 = dfx["close"]; ret4 = c4.pct_change()
    # ① 추세강도 = Kaufman 효율비 ER = |순변화| / Σ|봉변화| (0~1, 高=일방추세/低=톱니휩소) ★핵심 판별자
    ER = (c4 - c4.shift(W4)).abs() / c4.diff().abs().rolling(W4).sum()
    # ② 휩소율 = 최근창 4H수익 부호전환 빈도(0~1, 高=방향 갈팡질팡)
    sgn = np.sign(ret4)
    whip = (sgn != sgn.shift(1)).astype(float).rolling(W4).mean()
    # ③ 실현변동성 = 4H수익 표준편차(창)
    rv = ret4.rolling(W4).std()
    # ④ 점프강도 = 창 내 |4H수익|>3% 대형봉 수
    jump = (ret4.abs() > 0.03).astype(float).rolling(W4).sum()
    # ⑤ 7일추세 = (c/c[-7d]-1)*100 (라이브 챔피언 분류기 = 이 값 ±3%)
    trend = (c4 / c4.shift(W4) - 1.0) * 100.0
    # ⑥ ATR분위(rev_tf) = 저변동 판별(Stg3와 동일)
    tr = (dfx["high"] - dfx["low"]) / dfx["close"]
    atr = tr.rolling(14, min_periods=5).mean()
    atrp = atr.rolling(720, min_periods=120).rank(pct=True)
    feat = pd.DataFrame({"ER": ER, "whip": whip, "rv": rv, "jump": jump, "trend": trend, "atrp": atrp})
    feat = feat.shift(1)                # ★직전 완성봉까지 = 진입시점 lookahead0
    return feat, (dfx.index.values.astype("int64") // 1_000_000)


# ── taker 델타(CVD 불균형) 4H — 항상 존재하는 taker_buy_volume/volume로 산출 ──
def build_cvd4(rev_tf):
    dtk = pd.read_csv(DATA, usecols=["timestamp", "volume", "taker_buy_volume"])
    dtk["t"] = pd.to_datetime(dtk["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    dtk = dtk.dropna(subset=["volume"]).set_index("t").sort_index()
    r = f"{rev_tf}min"
    buy = dtk["taker_buy_volume"].resample(r).sum()
    vol = dtk["volume"].resample(r).sum()
    imb = (2.0 * buy / vol - 1.0).replace([np.inf, -np.inf], np.nan)   # +1=전량 매수공격 / -1=전량 매도공격
    imb = imb.shift(1)                  # lookahead0
    return imb


def attach_features(T, feat4, dfx_ms, oiz_arr, mt, cvd4):
    """거래원장 T에 진입시점 causal 피처 부착(전부 과거값)."""
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000)
    n = len(T)
    cols = {k: np.full(n, np.nan) for k in ["ER", "whip", "rv", "jump", "trend", "atrp", "oiz", "cvd"]}
    fv = feat4.values; fc = {c: i for i, c in enumerate(feat4.columns)}
    cvd_ms = (cvd4.index.values.astype("int64") // 1_000_000); cvd_v = cvd4.values
    for i in range(n):
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        if k < len(fv):
            for c in ["ER", "whip", "rv", "jump", "trend", "atrp"]:
                cols[c][i] = fv[k, fc[c]]
        kc = max(0, int(np.searchsorted(cvd_ms, et_ms[i], "right")) - 1)
        cols["cvd"][i] = cvd_v[kc] if kc < len(cvd_v) else np.nan
        j = max(0, int(np.searchsorted(mt, et_ms[i], "right")) - 1)
        v = oiz_arr[j]; cols["oiz"][i] = v if not np.isnan(v) else 0.0
    for c in cols:
        T[c] = cols[c]
    return T


# ── 미세레짐 taxonomy (7일추세 방향 × ER/변동성 세분) ──
def micro_regime(row, er_hi, rv_hi):
    tr = row["trend"]; er = row["ER"]; rv = row["rv"]
    if np.isnan(tr):
        return "미정"
    if tr <= -3:                                   # 하락(라이브 분류기의 down)
        if er >= er_hi and rv >= rv_hi:
            return "1_급락(SharpDrop)"             # 일방·고변동 = REVoi 받아치기 승 가설
        if er < er_hi:
            return "2_휩소하락(WhipDown)"          # 톱니 = REVoi fibstop 잘림 패 가설
        return "3_약한하락(WeakDown)"
    if tr >= 3:                                     # 상승
        return "6_랠리(Rally)"
    if rv >= rv_hi:                                 # 횡보
        return "5_고변동횡보(HiVolRange)"
    return "4_저변동횡보(LoVolRange)"


def perf(sub):
    """원장 부분집합 → 언사이즈드 성과지표."""
    R = sub["R"].values.astype(float)
    if len(R) == 0:
        return dict(n=0, win=0.0, meanR=0.0, sumR=0.0, pf=0.0, plr=0.0)
    wins = R[R > 0]; loss = R[R <= 0]
    pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else float("inf")
    plr = (wins.mean() / abs(loss.mean())) if len(wins) and len(loss) else 0.0
    return dict(n=len(R), win=(R > 0).mean() * 100, meanR=R.mean() * 100, sumR=R.sum() * 100,
                pf=pf, plr=plr)


def quint_table(sub, col, nb=5):
    """피처 col을 nb분위로 → 분위별 성과(단조성=판별력 확인)."""
    s = sub.dropna(subset=[col]).copy()
    if len(s) < nb * 5:
        return None
    try:
        s["_q"] = pd.qcut(s[col], nb, labels=False, duplicates="drop")
    except Exception:
        return None
    rows = []
    for q in sorted(s["_q"].dropna().unique()):
        g = s[s["_q"] == q]; pf = perf(g)
        rng = (g[col].min(), g[col].max())
        rows.append(dict(분위=f"Q{int(q)+1}", 범위=f"{rng[0]:.3f}~{rng[1]:.3f}", **pf))
    return pd.DataFrame(rows)


def analyze(name, T, feat4, dfx_ms, oiz_arr, mt, cvd4, L):
    T = attach_features(T.copy(), feat4, dfx_ms, oiz_arr, mt, cvd4)
    # 임계(설명용·중앙값) — in-sample 서술 bin
    er_hi = np.nanmedian(T["ER"].values); rv_hi = np.nanmedian(T["rv"].values)
    T["mreg"] = T.apply(lambda r: micro_regime(r, er_hi, rv_hi), axis=1)
    views = {"전체36mo": T, "post-2024": T[pd.to_datetime(T["et"]) >= ETF]}
    tax_csv = []; quint_csv = []
    for vname, V in views.items():
        L.append("")
        L.append(f"  ┌─ [{name} · {vname}] {len(V)}거래 · 전체 언사이즈드 성과: " +
                 f"승률{perf(V)['win']:.0f}% 평균R{perf(V)['meanR']:+.2f}% ΣR{perf(V)['sumR']:+.0f}% PF{perf(V)['pf']:.2f}")
        # ── 미세레짐별 손실지도 ──
        tot_neg = V[V["R"] <= 0]["R"].sum()
        L.append(f"  │ [미세레짐별] (ER中앙{er_hi:.2f}·rv中앙{rv_hi:.4f}로 하락 세분)")
        L.append(f"  │  {'레짐':<20}{'거래':>5}{'승률':>7}{'평균R':>8}{'ΣR':>9}{'PF':>6}{'손익비':>7}{'손실기여':>8}")
        for rg in sorted(V["mreg"].unique()):
            g = V[V["mreg"] == rg]; pfd = perf(g)
            negshare = (g[g["R"] <= 0]["R"].sum() / tot_neg * 100) if tot_neg != 0 else 0.0
            L.append(f"  │  {rg:<20}{pfd['n']:>5}{pfd['win']:>6.0f}%{pfd['meanR']:>+7.2f}%{pfd['sumR']:>+8.0f}%"
                     f"{pfd['pf']:>6.2f}{pfd['plr']:>7.2f}{negshare:>7.0f}%")
            tax_csv.append(dict(config=name, 뷰=vname, 미세레짐=rg, 거래=pfd['n'], 승률=round(pfd['win'], 1),
                                평균R=round(pfd['meanR'], 3), 합R=round(pfd['sumR'], 1), PF=round(pfd['pf'], 3),
                                손익비=round(pfd['plr'], 3), 손실기여pct=round(negshare, 1)))
        # ── '하락' 내부 급락 vs 휩소 대조(헤드라인 가설) ──
        dn = V[V["trend"] <= -3]
        if len(dn) >= 20:
            sharp = dn[dn["ER"] >= er_hi]; whipy = dn[dn["ER"] < er_hi]
            ps, pw = perf(sharp), perf(whipy)
            L.append(f"  │ [★하락장 내부] 일방(ER≥{er_hi:.2f}) {ps['n']}거래 승{ps['win']:.0f}%/평균R{ps['meanR']:+.2f}%"
                     f"  ↔  톱니휩소(ER<{er_hi:.2f}) {pw['n']}거래 승{pw['win']:.0f}%/평균R{pw['meanR']:+.2f}%")
        # ── 피처별 분위 단조성(어느 피처가 승패를 가르나) ──
        L.append(f"  │ [피처 분위별 평균R(%) — 단조↓면 판별력]")
        for col, lab in [("ER", "효율비ER"), ("whip", "휩소율"), ("rv", "실현변동성"),
                          ("atrp", "ATR분위"), ("oiz", "OI충격z"), ("jump", "점프수"), ("cvd", "테이커델타")]:
            qt = quint_table(V, col)
            if qt is None:
                continue
            arr = "  ".join(f"{r['meanR']:+.1f}" for _, r in qt.iterrows())
            L.append(f"  │   {lab:<10} Q1→Q5: {arr}")
            for _, r in qt.iterrows():
                quint_csv.append(dict(config=name, 뷰=vname, 피처=lab, **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}))
        L.append("  └─")
    return T, pd.DataFrame(tax_csv), pd.DataFrame(quint_csv)


def make_graph(TB, TC, path):
    """미세레짐별 평균R 막대(BASE vs COMBO, post-2024) — 손실 무더기 시각화."""
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, (nm, T) in zip(axes, [("BASE (anchor)", TB), ("COMBO (champion)", TC)]):
        V = T[pd.to_datetime(T["et"]) >= ETF]
        regs = sorted(V["mreg"].unique())
        vals = [perf(V[V["mreg"] == r])["meanR"] for r in regs]
        ns = [int((V["mreg"] == r).sum()) for r in regs]
        colors = ["#c0392b" if v < 0 else "#1a7f37" for v in vals]
        ax.bar(range(len(regs)), vals, color=colors)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(range(len(regs)))
        ax.set_xticklabels([r.split("(")[-1].rstrip(")") for r in regs], rotation=30, ha="right", fontsize=9)
        ax.set_ylabel("Mean R per trade (%)")
        ax.set_title(f"{nm}  post-2024  mean R by micro-regime\n(red=loss pile / n above bar)")
        for i, (v, c) in enumerate(zip(vals, ns)):
            ax.text(i, v + (0.05 if v >= 0 else -0.15), f"n={c}", ha="center", fontsize=8)
    fig.suptitle("REVoi loss map by micro-regime (WhipDown = whipsaw loss pile hypothesis)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _p(f"[{BASE}] 휩소 손실지도 진단 — 검증엔진만·causal 피처·BASE+COMBO·36mo+post2024")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    _p(f"  데이터 {len(d1m):,}행 · {d1m.index.min()}~{d1m.index.max()}")

    # ── 무손상 앵커 게이트(§15.2) ── BASE 원장 재현 → +1851.6491%
    TB = REVoiBot(dict(p)).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    a = VeriEdge(TB).anchor_check(75, 3, ANCHOR, tol=1.0)
    _p(f"  [무손상] BASE lev3/sz75 슬립0 = {a['got_%']}% (기준 +1851.6%) → {'✅ PASS' if a['pass'] else '❌ FAIL'}")
    if not a["pass"]:
        _p("  ❌ 앵커 불일치 → 진단 무효(§15.2). 중단."); return False
    # COMBO 원장(§9 챔피언)
    combo_p = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    TC = REVoiBot(combo_p).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    _p(f"  원장: BASE {len(TB)}거래 · COMBO {len(TC)}거래")

    # ── 피처 준비(1회) ──
    rev_tf = int(p["rev_tf"])
    feat4, dfx_ms = build_feat4(d1m, rev_tf)
    cvd4 = build_cvd4(rev_tf)
    oiz_arr = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce").values
    mt = (d1m.index.values.astype("int64") // 1_000_000)

    L = []
    L.append("=" * 100)
    L.append(f"[휩소 손실지도 진단] {BASE}")
    L.append("[성격] ★진단(in-sample 분해·수익률 주장 아님). 필터 미확정(다음 Stg=held-out·CPCV 표준6).")
    L.append("[방법] 검증엔진 REVoi_bot.make_trades 호출(재구현0)·피처 전부 진입 직전 완성 4H봉까지(shift1·lookahead0=라이브 계산가능).")
    L.append(f"[무손상] BASE lev3/sz75 슬립0 = {a['got_%']}% = 앵커 +1851.6% 재현 ✅")
    L.append("[피처] ①ER효율비(高=일방/低=톱니휩소·★핵심) ②휩소율(부호전환) ③실현변동성 ④점프수 ⑤7일추세(라이브분류기) ⑥ATR분위 ⑦OI충격z ⑧테이커델타")
    L.append("[가설] 라이브 down 한 칸 = 급락(REVoi 승) + 휩소하락(REVoi 패) 혼재 → 손실 무더기 = 휩소하락(저ER)일 것.")

    TBf, taxB, quB = analyze("BASE", TB, feat4, dfx_ms, oiz_arr, mt, cvd4, L)
    TCf, taxC, quC = analyze("COMBO", TC, feat4, dfx_ms, oiz_arr, mt, cvd4, L)

    # ── 판정 요약(post-2024 기준) ──
    L.append("")
    L.append("[★판정 — post-2024(ETF후) 미세레짐 진단]")
    for nm, Tf in [("BASE", TBf), ("COMBO", TCf)]:
        V = Tf[pd.to_datetime(Tf["et"]) >= ETF]
        neg_tot = V[V["R"] <= 0]["R"].sum()
        rows = []
        for rg in sorted(V["mreg"].unique()):
            g = V[V["mreg"] == rg]; pfd = perf(g)
            negshare = (g[g["R"] <= 0]["R"].sum() / neg_tot * 100) if neg_tot else 0.0
            rows.append((rg, pfd, negshare))
        best = max(rows, key=lambda x: x[1]["meanR"])
        weak = min(rows, key=lambda x: x[1]["meanR"])
        pile = max(rows, key=lambda x: x[2])
        nm_ = lambda r: r.split("_")[-1]
        L.append(f"  · {nm}: 최고EV={nm_(best[0])}({best[1]['meanR']:+.2f}%/승{best[1]['win']:.0f}%) · "
                 f"최저EV={nm_(weak[0])}({weak[1]['meanR']:+.2f}%/승{weak[1]['win']:.0f}%) · "
                 f"최대손실기여={nm_(pile[0])}(gross손실의{pile[2]:.0f}%·EV{pile[1]['meanR']:+.2f}%)")
    L.append("[해석] '손실기여'=그로스 음수R 점유율(net 아님). net 음수 레짐은 없음(REVoi 전체 +) → 병목은 '순손실'이 아니라 '저EV 역주행 군집'(레버·군집 시 드로다운·바닥↓).")
    L.append("[★경계] 위 수치는 in-sample 분해(수익률 주장 아님). '필터하면 +X%'는 다음 Stg에서 held-out·CPCV로만.")
    body = "\n".join(L)

    # ── 저장 ──
    taxALL = pd.concat([taxB, taxC], ignore_index=True)
    quALL = pd.concat([quB, quC], ignore_index=True)
    taxALL.to_csv(os.path.join(OUTDIR, f"{BASE}_미세레짐표.csv"), index=False, encoding="utf-8-sig")
    quALL.to_csv(os.path.join(OUTDIR, f"{BASE}_피처분위표.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(OUTDIR, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    make_graph(TBf, TCf, os.path.join(OUTDIR, f"{BASE}_손실지도.png"))
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|휩소 손실지도 진단(진단·in-sample): "
                f"검증엔진·causal피처·BASE+COMBO·미세레짐 급락↔휩소하락 분리|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {OUTDIR}\\  · 분석.txt · 미세레짐표.csv · 피처분위표.csv · 손실지도.png")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
