# -*- coding: utf-8 -*-
# [alpha_verification_system.py] — 알파 검증 시스템 (재사용 프레임워크)
#   목적: "이 신호에 알파가 있나?"를 ★2단 판정으로 시스템화 (캡틴 지시 2026-06-22, 참사 재발방지).
#     1) 알파 가능성(정보 존재·방향무관): WF 부호안정 + SPRT 엣지검출 (무비용 = 정보 테스트)
#        → ★방향이 정반대여도 부호가 일관되면 정보는 있다(캡틴 핵심지적). 시스템이 방향을 자동발견·정렬.
#     2) 수익률 알파(배포가능): CPCV(퍼지+엠바고 15경로) p25>0 + Deflated Sharpe + 비용차감 OOS
#   방법론 출처: CPCV/퍼지(Lopez de Prado), SPRT(순차검정), WF(OOS연결), DSR/PBO(Bailey).
#   ★데이터: 2020~2026 BTC선물(ChatGPT 지시). 펀딩=API복구(2020~). OI z=로컬 Merged(2023~만, 정직병기).
#   ★이건 신호 정보검증 시스템이지 봇 백테가 아님(§15 봇로직 재구현 안함). 룩어헤드 0(전부 과거→미래).
import os, json, itertools, urllib.request, urllib.parse
import datetime as dt
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
H8 = 8 * 3600 * 1000
PERIODS_YR = 365 * 3            # 8h 슬롯/년
COST_1WAY = 0.0004             # 4bp 편도(왕복 8bp = §7 버전B). 비용민감도용.


def _p(*a): print(*a, flush=True)


# ───────────────────────── 데이터 ─────────────────────────
def get(path, params):
    url = "https://fapi.binance.com" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "alpha-verify"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def fetch_funding(sym, a, b):
    out, cur = [], a
    while cur <= b:
        fs = get("/fapi/v1/fundingRate", {"symbol": sym, "startTime": cur, "endTime": b, "limit": 1000})
        if not fs: break
        out += [(int(x["fundingTime"]), float(x["fundingRate"])) for x in fs]
        cur = int(fs[-1]["fundingTime"]) + 1
        if len(fs) < 1000: break
    return out


def fetch_klines_8h(sym, a, b):
    out, cur = [], a
    while cur <= b:
        ks = get("/fapi/v1/klines", {"symbol": sym, "interval": "8h", "startTime": cur, "endTime": b, "limit": 1500})
        if not ks: break
        out += [(int(k[0]), float(k[1]), float(k[4])) for k in ks]   # openTime, open, close
        cur = ks[-1][0] + H8
        if len(ks) < 1500: break
    return out


def floor8(ms): return (ms // H8) * H8


def load_oi_8h():
    """로컬 Merged_Data.csv(REPAIRED, oi_zscore_24h shift(1)=룩어헤드세이프) → 8h 그리드 asof."""
    try:
        d = pd.read_csv(os.path.join(ROOT, "Merged_Data.csv"), usecols=["timestamp", "oi_zscore_24h"])
    except Exception as e:
        _p("  (OI 로드 실패, 펀딩만:", e, ")"); return None
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d["slot"] = (d["t"].astype("int64") // 10**6 // H8) * H8
    d["oi_zscore_24h"] = pd.to_numeric(d["oi_zscore_24h"], errors="coerce")
    return d.groupby("slot")["oi_zscore_24h"].last()    # 슬롯내 마지막값(과거)


def build_panel():
    a = int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    b = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    _p(f"[수집] BTC 펀딩+8h가격 2020-01 ~ now")
    fund = pd.DataFrame(fetch_funding("BTCUSDT", a, b), columns=["ms", "fund"]).drop_duplicates("ms")
    fund["slot"] = fund["ms"].map(floor8)
    f = fund.groupby("slot")["fund"].last()
    kl = pd.DataFrame(fetch_klines_8h("BTCUSDT", a, b), columns=["slot", "open", "close"]).drop_duplicates("slot").set_index("slot")
    P = pd.DataFrame({"fund": f}).join(kl, how="inner")
    oi = load_oi_8h()
    P = P.join(oi.rename("oi_z")) if oi is not None else P.assign(oi_z=np.nan)
    P = P.sort_index()
    P.index = pd.to_datetime(P.index, unit="ms", utc=True)
    P["fund_slope"] = P["fund"].diff()
    # ★룩어헤드 차단: oi_z(슬롯끝값)를 1슬롯 shift → 신호는 't 직전'에만 알려진 값으로 [t,t+8h) 예측.
    #   (펀딩은 슬롯시작 00:00에 정산되어 shift 불필요; OI는 1m 연속이라 끝값=미래라 shift 필수)
    P["oi_z"] = P["oi_z"].shift(1)
    # 선행수익(8h open 기준, 비중첩) = t시점 진입 → t+8h
    P["fwd_8h"] = P["open"].shift(-1) / P["open"] - 1.0
    P = P.dropna(subset=["fwd_8h"])
    _p(f"[패널] {len(P)} 8h슬롯 | {P.index.min().date()} ~ {P.index.max().date()} | "
       f"펀딩유효 {P['fund'].notna().sum()} | OI유효 {P['oi_z'].notna().sum()}")
    return P


# ───────────────────────── 신호→포지션 ─────────────────────────
def positions(sig, direction, lo=0.30, hi=0.70):
    """신호 분위 → 롱(상위)/숏(하위) ±1, 중간 0. direction(+1/-1)로 발견된 방향 정렬."""
    r = sig.rank(pct=True)
    pos = pd.Series(0.0, index=sig.index)
    pos[r >= hi] = 1.0
    pos[r <= lo] = -1.0
    return pos * direction


def positions_extreme(sig, direction, q=0.10):
    """극단진입·저회전: 신호 상/하위 q(예 10%)일 때만 ±1, 평소 0(무포지션)."""
    r = sig.rank(pct=True)
    pos = pd.Series(0.0, index=sig.index)
    pos[r >= 1 - q] = 1.0
    pos[r <= q] = -1.0
    return pos * direction


def strat_returns(sig, fwd, direction, cost=0.0, mode="quantile", q=0.10):
    pos = positions_extreme(sig, direction, q) if mode == "extreme" else positions(sig, direction)
    gross = pos * fwd
    turn = pos.diff().abs().fillna(pos.abs())
    return gross - cost * turn, pos


def turnover(pos):
    return float(pos.diff().abs().fillna(pos.abs()).mean())


def cost_sweep(sig, fwd, direction, mode, costs=(0.0, 0.0002, 0.0004, 0.0008)):
    """비용 0/2/4/8bp(편도)별 net Sharpe·총수익·회전율. 견고성=비용 올려도 Sharpe>0 유지."""
    out = []
    for c in costs:
        r, pos = strat_returns(sig, fwd, direction, cost=c, mode=mode)
        out.append(dict(cost_bp=c * 1e4, sharpe=sharpe(r.values),
                        total=float((1 + r.fillna(0)).prod() - 1), turn=turnover(pos)))
    return out


def sharpe(r):
    r = r[np.isfinite(r)]
    if len(r) < 10 or r.std() == 0: return 0.0
    return float(r.mean() / r.std() * np.sqrt(PERIODS_YR))


# ───────────────────────── 검증 방법 ─────────────────────────
def spearman_ic(sig, fwd):
    m = sig.notna() & fwd.notna()
    if m.sum() < 30: return np.nan, np.nan
    rho, p = stats.spearmanr(sig[m], fwd[m]); return float(rho), float(p)


def walk_forward(sig, fwd, n_folds=8, mode="quantile"):
    """롤링 WF: 각 폴드의 train에서 방향발견 → test에서 OOS IC·수익. OOS 연결."""
    idx = sig.dropna().index
    if len(idx) < n_folds * 40: n_folds = max(3, len(idx) // 60)
    folds = np.array_split(np.arange(len(idx)), n_folds + 1)
    oos_ic, oos_ret, dirs = [], [], []
    for i in range(1, len(folds)):
        tr = idx[np.concatenate(folds[:i])]; te = idx[folds[i]]
        d = np.sign(spearman_ic(sig.loc[tr], fwd.loc[tr])[0] or 0.0) or 1.0
        ic_te, _ = spearman_ic(sig.loc[te], fwd.loc[te])
        r, _ = strat_returns(sig.loc[te], fwd.loc[te], d, mode=mode)
        oos_ic.append((ic_te or 0.0) * d)        # 방향정렬 IC(>0이면 train방향이 OOS서도 유지)
        oos_ret.append(r); dirs.append(d)
    oos = pd.concat(oos_ret) if oos_ret else pd.Series(dtype=float)
    aligned = np.array(oos_ic)
    sign_stab = float((aligned > 0).mean()) if len(aligned) else 0.0
    return dict(fold_ic=aligned, sign_stability=sign_stab, oos_ret=oos, oos_sharpe=sharpe(oos.values))


def cpcv(sig, fwd, direction, n_groups=6, k=2, horizon=1, embargo=2, cost=0.0, mode="quantile"):
    """조합 퍼지 CV: N그룹 중 k개 test, 퍼지+엠바고. C(6,2)=15경로 → 경로별 Sharpe/수익 분포."""
    idx = sig.dropna().index
    g = np.array_split(np.arange(len(idx)), n_groups)
    paths = []
    for combo in itertools.combinations(range(n_groups), k):
        te_pos = np.concatenate([g[c] for c in combo])
        te_mask = np.zeros(len(idx), bool); te_mask[te_pos] = True
        # 퍼지+엠바고: test 경계 ±(horizon+embargo) train제외(여기선 방향발견용 train)
        block = te_mask.copy()
        for s in range(1, horizon + embargo + 1):
            block |= np.r_[te_mask[s:], [False] * s]
            block |= np.r_[[False] * s, te_mask[:-s]]
        tr_idx = idx[~block]
        d = direction or (np.sign(spearman_ic(sig.loc[tr_idx], fwd.loc[tr_idx])[0] or 0.0) or 1.0)
        te_idx = idx[te_mask]
        r, _ = strat_returns(sig.loc[te_idx], fwd.loc[te_idx], d, cost, mode=mode)
        paths.append((sharpe(r.values), float(r.sum())))
    sh = np.array([p[0] for p in paths]); ret = np.array([p[1] for p in paths])
    return dict(path_sharpe=sh, path_ret=ret, p25=float(np.percentile(sh, 25)),
                worst=float(sh.min()), frac_neg=float((sh < 0).mean()))


def sprt(aligned_ret, sharpe_h1=0.5, alpha=0.05, beta=0.05):
    """순차확률비검정: H0 엣지=0 vs H1 연Sharpe=sharpe_h1. 조기 엣지판정 + 궤적."""
    r = aligned_ret[np.isfinite(aligned_ret)]
    if len(r) < 30: return dict(decision="표본부족", traj=np.array([]), A=0, B=0, n_stop=0)
    sd = r.std(); mu1 = sharpe_h1 / np.sqrt(PERIODS_YR) * sd      # H1 효과크기(주기평균)
    incr = (mu1 / sd**2) * (r - mu1 / 2.0)                        # 정규 LLR 증분
    S = np.cumsum(incr)
    A = np.log((1 - beta) / alpha); B = np.log(beta / (1 - alpha))
    dec, n_stop = "미결(엣지 약)", len(S)
    hitA = np.where(S >= A)[0]; hitB = np.where(S <= B)[0]
    first = min([h[0] for h in (hitA, hitB) if len(h)], default=None)
    if first is not None:
        n_stop = int(first + 1)
        dec = "엣지 있음(H1)" if S[first] >= A else "엣지 없음(H0)"
    return dict(decision=dec, traj=S, A=A, B=B, n_stop=n_stop)


def deflated_sharpe(r, n_trials):
    """PSR/DSR: 관측 Sharpe가 다중검정(n_trials) 보정 후에도 >0일 확률."""
    r = r[np.isfinite(r)]
    if len(r) < 30 or r.std() == 0: return dict(sr=0.0, psr0=np.nan, dsr=np.nan)
    n = len(r); sr = r.mean() / r.std()        # 주기 Sharpe(비연율)
    sk = float(stats.skew(r)); ku = float(stats.kurtosis(r, fisher=False))
    denom = np.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4.0 * sr**2))
    psr0 = float(stats.norm.cdf(sr * np.sqrt(n - 1) / denom))     # SR*>0 확률
    # 기대 최대 Sharpe(귀무 N시도) ≈ E[max] → DSR
    if n_trials > 1:
        e = np.e; g = 0.5772
        z = (1 - g) * stats.norm.ppf(1 - 1.0 / n_trials) + g * stats.norm.ppf(1 - 1.0 / (n_trials * e))
        sr_star = (r.std(ddof=1) * 0) + z * (1.0 / np.sqrt(n))    # SR* 기준점(주기단위 근사)
    else:
        sr_star = 0.0
    dsr = float(stats.norm.cdf((sr - sr_star) * np.sqrt(n - 1) / denom))
    return dict(sr=float(sr * np.sqrt(PERIODS_YR)), psr0=psr0, dsr=dsr)


# ───────────────────────── 시나리오 실행 ─────────────────────────
def verify_signal(name, sig, fwd, n_trials, cost=COST_1WAY, mode="quantile"):
    sig, fwd = sig.dropna(), fwd
    common = sig.index.intersection(fwd.dropna().index)
    sig, fwd = sig.loc[common], fwd.loc[common]
    ic, ic_p = spearman_ic(sig, fwd)
    direction = np.sign(ic) if ic == ic and ic != 0 else 1.0     # 발견된 방향(정반대면 -1로 정렬)
    wf = walk_forward(sig, fwd, mode=mode)
    # 알파가능성: 무비용 방향정렬 수익으로 SPRT
    r_info, _ = strat_returns(sig, fwd, direction, cost=0.0, mode=mode)
    sp = sprt(r_info.values)
    cv = cpcv(sig, fwd, direction, cost=cost, mode=mode)
    r_net, pos_net = strat_returns(sig, fwd, direction, cost=cost, mode=mode)
    dsr = deflated_sharpe(r_net.values, n_trials)
    # ★3단 판정 (캡틴 정의 반영)
    #  ① 알파가능성 = 방향정보 존재(WF 부호안정 >=62.5%). 방향 정반대여도 일관되면 정보 있음.
    #  ② 엣지확정 = SPRT가 Sharpe0.5 엣지를 통계적으로 검출.
    #  ③ 배포가능 = 가능성 AND 비용후 CPCV p25>0 AND DSR>0.95 AND 비용후Sharpe>0.
    possibility = wf["sign_stability"] >= 0.625
    edge_confirmed = (sp["decision"] == "엣지 있음(H1)")
    nsh = sharpe(r_net.values)
    deployable = possibility and (cv["p25"] > 0) and (dsr["dsr"] is not None and dsr["dsr"] > 0.95) and (nsh > 0)
    return dict(name=name, n=len(sig), ic=ic, ic_p=ic_p, direction=float(direction), mode=mode,
                wf=wf, sprt=sp, cpcv=cv, dsr=dsr, net_sharpe=nsh, turnover=turnover(pos_net),
                info_sharpe=sharpe(r_info.values), oos_net=r_net,
                possibility=bool(possibility), edge_confirmed=bool(edge_confirmed), deployable=bool(deployable))


def plot_scenario(res, path):
    fig, ax = plt.subplots(2, 2, figsize=(13, 8))
    fig.suptitle(f"Alpha Verification: {res['name']}  (IC={res['ic']:+.3f}, dir={'+' if res['direction']>0 else '-'})", fontsize=13)
    # A: WF OOS IC by fold
    fic = res["wf"]["fold_ic"]
    ax[0,0].bar(range(len(fic)), fic, color=["#2c7" if x>0 else "#c44" for x in fic])
    ax[0,0].axhline(0, color="k", lw=.8); ax[0,0].set_title(f"A. Walk-Forward OOS IC (sign-aligned)  stability={res['wf']['sign_stability']:.0%}")
    ax[0,0].set_xlabel("fold"); ax[0,0].set_ylabel("direction-aligned IC")
    # B: CPCV path Sharpe dist
    sh = res["cpcv"]["path_sharpe"]
    ax[0,1].hist(sh, bins=12, color="#48a", edgecolor="w")
    ax[0,1].axvline(0, color="k", lw=.8); ax[0,1].axvline(res["cpcv"]["p25"], color="#e80", lw=2, label=f"p25={res['cpcv']['p25']:.2f}")
    ax[0,1].axvline(res["cpcv"]["worst"], color="#c44", lw=1.5, ls="--", label=f"worst={res['cpcv']['worst']:.2f}")
    ax[0,1].set_title(f"B. CPCV 15-path Sharpe (cost-adj)  neg={res['cpcv']['frac_neg']:.0%}"); ax[0,1].legend(fontsize=8); ax[0,1].set_xlabel("annual Sharpe")
    # C: SPRT trajectory
    tr = res["sprt"]["traj"]
    ax[1,0].plot(tr, color="#333")
    ax[1,0].axhline(res["sprt"]["A"], color="#2c7", ls="--", label="accept edge (H1)")
    ax[1,0].axhline(res["sprt"]["B"], color="#c44", ls="--", label="reject edge (H0)")
    _DEC = {"엣지 있음(H1)": "EDGE (H1)", "엣지 없음(H0)": "NO EDGE (H0)", "미결(엣지 약)": "INCONCLUSIVE", "표본부족": "INSUFFICIENT"}
    ax[1,0].set_title(f"C. SPRT: {_DEC.get(res['sprt']['decision'], res['sprt']['decision'])}  (n_stop={res['sprt']['n_stop']})"); ax[1,0].legend(fontsize=8); ax[1,0].set_xlabel("8h sample"); ax[1,0].set_ylabel("cum log-LR")
    # D: OOS cumulative equity (cost-adj)
    eq = (1 + res["oos_net"].fillna(0)).cumprod()
    ax[1,1].plot(res["oos_net"].index, eq.values, color="#258")
    ax[1,1].axhline(1, color="k", lw=.8)
    ax[1,1].set_title(f"D. Cost-adj equity (net Sharpe={res['net_sharpe']:.2f}, DSR={res['dsr']['dsr']:.2f})"); ax[1,1].set_ylabel("growth x")
    fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    P = build_panel()
    P24 = P[P.index >= P.index.max() - pd.Timedelta(days=365*3)]   # OI 가용창(2023~)용 참조

    scenarios = []
    scenarios.append(("Funding_level (2020-26)", P["fund"], P["fwd_8h"]))
    scenarios.append(("Funding_slope (2020-26)", P["fund_slope"], P["fwd_8h"]))
    oi = P["oi_z"].dropna()
    if len(oi) > 500:
        Poi = P.loc[oi.index]
        scenarios.append(("OI_zscore (2023-26)", Poi["oi_z"], Poi["fwd_8h"]))
        combo = (Poi["oi_z"].rank(pct=True) + (-Poi["fund"]).rank(pct=True)) / 2   # OI높음+펀딩낮음 결합
        scenarios.append(("OI_x_Funding combo (2023-26)", combo, Poi["fwd_8h"]))
    N = len(scenarios)

    _p("\n" + "=" * 96)
    _p("알파 검증 시스템 — 3단 판정 (①가능성=방향정보 / ②엣지=SPRT확정 / ③배포=비용후 견고)")
    _p("=" * 96)
    _p(f"{'시나리오':<30}{'IC':>8}{'방향':>5}{'WF안정':>7}{'net SR':>7}{'CPCV p25':>9}{'DSR':>6}{'①가능성':>8}{'②엣지':>6}{'③배포':>6}")
    _p("-" * 96)
    rows = []
    for nm, s, f in scenarios:
        res = verify_signal(nm, s, f, n_trials=N)
        plot_scenario(res, os.path.join(HERE, f"AV_{nm.split()[0]}.png"))
        _p(f"{nm:<30}{res['ic']:>+8.3f}{'+' if res['direction']>0 else '-':>5}"
           f"{res['wf']['sign_stability']:>6.0%}{res['net_sharpe']:>7.2f}"
           f"{res['cpcv']['p25']:>9.2f}{res['dsr']['dsr']:>6.2f}"
           f"{'O' if res['possibility'] else 'X':>7}{'O' if res['edge_confirmed'] else 'X':>6}{'O' if res['deployable'] else 'X':>6}")
        rows.append(dict(scenario=nm, ic=res['ic'], ic_p=res['ic_p'], direction=res['direction'],
                         wf_stability=res['wf']['sign_stability'], wf_oos_sharpe=res['wf']['oos_sharpe'],
                         sprt=res['sprt']['decision'], sprt_nstop=res['sprt']['n_stop'],
                         cpcv_p25=res['cpcv']['p25'], cpcv_worst=res['cpcv']['worst'], cpcv_fracneg=res['cpcv']['frac_neg'],
                         net_sharpe=res['net_sharpe'], info_sharpe=res['info_sharpe'],
                         dsr=res['dsr']['dsr'], psr0=res['dsr']['psr0'],
                         possibility=res['possibility'], edge_confirmed=res['edge_confirmed'], deployable=res['deployable']))
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "AV_results.csv"), index=False, encoding="utf-8-sig")

    # ───── 정제: 저회전 극단진입 + 비용민감도 (회전율↓로 배포선 넘나?) ─────
    _p("\n" + "-" * 96)
    _p("[정제] 저회전 극단진입(±decile만, 평소 무포지션) vs 기존(8h매번 30/70). 회전율↓로 비용 견디나?")
    _p("-" * 96)
    _p(f"{'시나리오 · 모드':<32}{'회전율':>7}{'net SR(8bp)':>12}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'③배포':>6}")
    refine = [(nm, s, f) for nm, s, f in scenarios if nm.startswith("Funding_level") or nm.startswith("OI_zscore")]
    sweep_data = {}
    for nm, s, f in refine:
        for mode, lab in [("quantile", "기존30/70"), ("extreme", "극단decile")]:
            r = verify_signal(nm, s, f, n_trials=N, mode=mode)
            _p(f"{(nm.split()[0] + ' · ' + lab):<32}{r['turnover']:>7.2f}{r['net_sharpe']:>12.2f}"
               f"{r['cpcv']['p25']:>10.2f}{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
        cm = s.dropna().index.intersection(f.dropna().index); ss, ff = s.loc[cm], f.loc[cm]
        d = np.sign(spearman_ic(ss, ff)[0] or 0.0) or 1.0
        sweep_data[nm.split()[0]] = dict(quantile=cost_sweep(ss, ff, d, "quantile"),
                                         extreme=cost_sweep(ss, ff, d, "extreme"))
    fig, ax = plt.subplots(1, len(sweep_data), figsize=(7 * len(sweep_data), 4.6), squeeze=False)
    for j, (kk, vv) in enumerate(sweep_data.items()):
        for mode, col, lab in [("quantile", "#c44", "quantile 30/70 (high turnover)"),
                               ("extreme", "#258", "extreme decile (low turnover)")]:
            xs = [dd["cost_bp"] * 2 for dd in vv[mode]]; ys = [dd["sharpe"] for dd in vv[mode]]
            ax[0][j].plot(xs, ys, "o-", color=col, label=lab)
        ax[0][j].axhline(0, color="k", lw=.8)
        ax[0][j].set_title(f"{kk}: net Sharpe vs round-trip cost"); ax[0][j].set_xlabel("round-trip cost (bp)")
        ax[0][j].set_ylabel("annual Sharpe"); ax[0][j].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "AV_cost_sensitivity.png"), dpi=110); plt.close(fig)
    _p("[저장] AV_cost_sensitivity.png (회전율·비용 견고성)")

    # 요약 그래프
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    c = ["#2c7" if d else "#c44" for d in df["deployable"]]
    ax[0].barh(df["scenario"], df["cpcv_p25"], color=c); ax[0].axvline(0, color="k", lw=.8)
    ax[0].set_title("CPCV p25 Sharpe (green=deployable)"); ax[0].set_xlabel("p25 annual Sharpe (cost-adj)")
    ax[1].barh(df["scenario"], df["wf_stability"], color=["#28a" if p else "#aaa" for p in df["possibility"]])
    ax[1].axvline(0.625, color="#e80", ls="--", label="possibility gate 62.5%"); ax[1].set_xlim(0,1)
    ax[1].set_title("WF sign stability (blue=alpha-possibility)"); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "AV_summary.png"), dpi=110); plt.close(fig)
    _p(f"\n[저장] AV_results.csv + AV_*.png (시나리오별 4패널 + 요약)")
    _p("[판정기준] ①가능성=WF부호안정>=62.5%(방향정보,정반대여도OK) ②엣지=SPRT가 Sharpe0.5 검출 ③배포=가능성+CPCV p25>0+DSR>0.95+비용후Sharpe>0.")
    _p("[정직] OI는 2023~만(로컬 z). 펀딩은 2020~. 비용=4bp편도(왕복8bp). IC≠수익. 2각도(WF+CPCV) 독립.")


if __name__ == "__main__":
    main()
