# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg2_OICVDFilter.py]
# OB Character 검증 2단계 — OI/CVD feature가 OB 성공/실패를 가르나(캡틴 핵심질문).
#   1단계 결론: OB 자체가 random 대비 +10~12%p(진입가기준 대칭, 추세무관). 토대 확정.
#   2단계 질문: OB 60%를 70%+ OB와 50% OB로 'OI/CVD'가 가를 수 있나 = 신뢰도 필터.
#   ★ChatGPT 5보완 반영: Rank IC(Spearman) · Top/Bottom 분위 · AUC · CPCV 표준6(시간순).
#   ★룩어헤드0: ① OB·swing 우측1확정 ② features=봉마감 확정값 ③ Bounce 진입=재방문봉 마감후(rev+1)
#              ④ 같은봉 stop·target 동시=stop 우선(낙관금지) ⑤ CPCV 시간순 그룹.
#   검증엔진 무수정 호출(§8): TS.resample_tf · TS.pivots_lr · TS.compute_atr.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score


def find_root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
import trendstack_signal_engine as TS

DATA = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output",
                      "260627_02_OBOICharacter_Stg2_OICVDFilter")

N_SWING = 5
OB_TFS = [240, 60]
ATR_PD = 14
MAX_OB_LOOKBACK = 10
X_ATR = 1.0            # 진입가기준 대칭 RR (1단계 공정비교와 동일)
Y_ATR = 1.0
MAX_WAIT_REVISIT = 60
MAX_HOLD_AFTER = 30
N_GROUPS, K_TEST = 6, 2     # CPCV 표준6 (15경로)


def load_data():
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "taker_buy_volume", "oi_sum", "oi_change_1h_pct", "oi_zscore_24h"]
    df = pd.read_csv(DATA, usecols=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


def extract_obs(g, atr):
    """1단계와 동일 검증로직(ICT OB, 룩어헤드0). 반환 OB dict 리스트 + 배열."""
    H = g["high"].values; L = g["low"].values; C = g["close"].values; O = g["open"].values
    idx = g.index; n = len(C)
    ph, pl = TS.pivots_lr(H, L, N_SWING, 1)
    ph_at = {k: v[1] for k, v in ph.items()}; pl_at = {k: v[1] for k, v in pl.items()}
    obs = []; last_ph = last_pl = np.nan
    for i in range(n):
        if i in ph_at: last_ph = ph_at[i]
        if i in pl_at: last_pl = pl_at[i]
        if not np.isnan(last_ph) and C[i] > last_ph:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] < O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] < O[j]:
                obs.append(dict(conf_i=i, side=1, ob_lo=float(L[j]), ob_hi=float(H[j]),
                                atr=float(atr[i]), bos_size=float(C[i] - last_ph)))
            last_ph = np.nan
        if not np.isnan(last_pl) and C[i] < last_pl:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] > O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] > O[j]:
                obs.append(dict(conf_i=i, side=-1, ob_lo=float(L[j]), ob_hi=float(H[j]),
                                atr=float(atr[i]), bos_size=float(last_pl - C[i])))
            last_pl = np.nan
    return obs, idx, H, L, C


def eval2(ob, idx, H, L, C):
    """진입가(OB경계) 대칭 RR + ★Bounce 판정 rev+1부터(재방문봉 마감후 진입=룩어헤드0)."""
    i = ob["conf_i"]; side = ob["side"]; lo = ob["ob_lo"]; hi = ob["ob_hi"]; atr = ob["atr"]
    n = len(C)
    if not (atr > 0):
        return None
    rev = None
    for j in range(i + 1, min(i + 1 + MAX_WAIT_REVISIT, n)):
        if H[j] >= lo and L[j] <= hi:
            rev = j; break
    if rev is None:
        return None
    entry = hi if side == 1 else lo
    target = entry + X_ATR * atr if side == 1 else entry - X_ATR * atr
    stop = entry - Y_ATR * atr if side == 1 else entry + Y_ATR * atr
    oc = 0
    for j in range(rev + 1, min(rev + 1 + MAX_HOLD_AFTER, n)):
        hs = (L[j] <= stop) if side == 1 else (H[j] >= stop)
        ht = (H[j] >= target) if side == 1 else (L[j] <= target)
        if hs:
            oc = -1; break
        if ht:
            oc = 1; break
    r = dict(ob); r.update(rev_j=rev, conf_time=idx[i], rev_time=idx[rev], outcome=oc)
    return r


def build_feat(df, tf):
    """OB-TF 봉별 OI/CVD/vol feature(봉마감 확정값, 룩어헤드0)."""
    d = df.copy()
    d["cvd"] = 2.0 * d["taker_buy_volume"] - d["volume"]      # taker buy - taker sell
    r = d.resample(f"{tf}min", label="left", closed="left")
    f = pd.DataFrame({
        "oi_last": r["oi_sum"].last(),
        "oi_z": r["oi_zscore_24h"].last(),
        "oi_chg1h": r["oi_change_1h_pct"].last(),
        "cvd": r["cvd"].sum(),
        "vol": r["volume"].sum(),
        "o": r["open"].first(),
        "c": r["close"].last(),
    }).dropna(subset=["oi_last"])
    f["d_oi"] = f["oi_last"].pct_change()                      # OB-TF 봉간 OI 변화율
    f["cvd_norm"] = f["cvd"] / f["vol"].replace(0, np.nan)
    f["vol_ratio"] = f["vol"] / f["vol"].rolling(20).mean()
    return f


# feature 이름(생성시 gen_*, 재방문시 rev_*)
FEATS = ["gen_oi_z", "gen_oi_chg1h", "gen_d_oi", "gen_cvd_norm", "gen_vol_ratio",
         "gen_bos_atr", "rev_d_oi_since", "rev_cvd_norm", "rev_gap", "rev_depth", "rev_ret_atr"]


def make_rows(evals, f, idx):
    """OB 이벤트 + feature 부착. 룩어헤드0: 생성시=conf봉, 재방문시=rev봉(마감확정)."""
    rows = []
    fi = f.index
    for e in evals:
        ct, rt = e["conf_time"], e["rev_time"]
        if ct not in f.index or rt not in f.index:
            continue
        fc = f.loc[ct]; fr = f.loc[rt]
        oi_c = fc["oi_last"]; oi_r = fr["oi_last"]
        if not (oi_c == oi_c and oi_r == oi_r and oi_c != 0):
            continue
        depth = ((e["ob_hi"] - L_at(e, "rev")) if e["side"] == 1 else (H_at(e, "rev") - e["ob_lo"]))
        rng = max(1e-9, e["ob_hi"] - e["ob_lo"])
        row = {
            "conf_time": ct, "side": e["side"], "outcome": e["outcome"],
            "gen_oi_z": fc["oi_z"], "gen_oi_chg1h": fc["oi_chg1h"], "gen_d_oi": fc["d_oi"],
            "gen_cvd_norm": fc["cvd_norm"] * e["side"],          # side정렬: 방향대비 흡수부호
            "gen_vol_ratio": fc["vol_ratio"], "gen_bos_atr": e["bos_size"] / max(1e-9, e["atr"]),
            "rev_d_oi_since": oi_r / oi_c - 1.0,                 # ★재방문 OI 유지/감소(캡틴 핵심)
            "rev_cvd_norm": fr["cvd_norm"] * e["side"],          # ★재방문 CVD 흡수/반대
            "rev_gap": float(e["rev_j"] - e["conf_i"]),
            "rev_depth": float(np.clip(depth / rng, 0, 1)),
            "rev_ret_atr": (fr["c"] - fr["o"]) / max(1e-9, e["atr"]) * e["side"],   # 재방문봉 가격모멘텀(통제용)
        }
        rows.append(row)
    return pd.DataFrame(rows)


# depth용 보조(rev봉 저/고) — eval2가 rev_j 보유, 배열 접근 위해 클로저 대체
_ARR = {}
def L_at(e, which):
    return _ARR["L"][e["rev_j"]]
def H_at(e, which):
    return _ARR["H"][e["rev_j"]]


def quantile_split(x, y, q=0.3):
    """feature 상위/하위 분위 성공률(미결 제외 y=0/1)."""
    m = ~np.isnan(x)
    x, y = x[m], y[m]
    if len(x) < 20:
        return float("nan"), float("nan")
    lo_th, hi_th = np.quantile(x, q), np.quantile(x, 1 - q)
    lo = y[x <= lo_th]; hi = y[x >= hi_th]
    return (100 * hi.mean() if len(hi) else float("nan"),
            100 * lo.mean() if len(lo) else float("nan"))


def cpcv(X, y, order):
    """CPCV 표준6(시간순 6그룹, test 2그룹 → 15경로). OOS AUC + 순효과(top-half 성공률 − 전체)."""
    order_idx = np.argsort(order)
    groups = np.array_split(order_idx, N_GROUPS)
    aucs, effs = [], []
    for tg in combinations(range(N_GROUPS), K_TEST):
        test = np.concatenate([groups[g] for g in tg])
        train = np.concatenate([groups[g] for g in range(N_GROUPS) if g not in tg])
        if len(np.unique(y[train])) < 2 or len(np.unique(y[test])) < 2:
            continue
        sc = StandardScaler().fit(X[train])
        clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(sc.transform(X[train]), y[train])
        p = clf.predict_proba(sc.transform(X[test]))[:, 1]
        aucs.append(roc_auc_score(y[test], p))
        med = np.median(p)
        top = y[test][p >= med]
        effs.append(100 * top.mean() - 100 * y[test].mean())
    return np.array(aucs), np.array(effs)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    df = load_data()
    print(f"[데이터] {len(df):,}행 | {df.index[0]} ~ {df.index[-1]}", flush=True)
    print(f"[설정] 진입가기준 대칭 RR(X=Y={X_ATR}) · Bounce=rev+1 · CPCV 표준{N_GROUPS}({K_TEST}test)", flush=True)
    all_rows = []
    for tf in OB_TFS:
        g = TS.resample_tf(df, tf)
        atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
        obs, idx, H, L, C = extract_obs(g, atr)
        _ARR["H"], _ARR["L"] = H, L
        evals = [e for e in (eval2(o, idx, H, L, C) for o in obs) if e]
        f = build_feat(df, tf)
        R = make_rows(evals, f, idx)
        R["ob_tf"] = tf
        dec = R[R["outcome"] != 0].copy()       # 결판(성공1/실패-1) → y=1/0
        dec["y"] = (dec["outcome"] == 1).astype(int)
        base = 100 * dec["y"].mean()
        tfh = f"{tf}m({tf // 60}h)"
        print("\n" + "=" * 70, flush=True)
        print(f"### OB-TF {tfh} | 결판 OB {len(dec)}개 | 기저 성공률 {base:.1f}%", flush=True)
        # (A) 단변량 Rank IC + 분위
        print("  [feature]            RankIC    p      상위30%  하위30%  (성공률)", flush=True)
        for ft in FEATS:
            x = dec[ft].values.astype(float); y = dec["y"].values
            m = ~np.isnan(x)
            if m.sum() < 20:
                continue
            ic, pv = spearmanr(x[m], y[m])
            hi_wr, lo_wr = quantile_split(x, y)
            star = "★" if pv < 0.05 and abs(ic) > 0.05 else " "
            print(f"  {star}{ft:18s}  {ic:+.3f}  {pv:.3f}   {hi_wr:5.1f}%  {lo_wr:5.1f}%", flush=True)
        # (B) 다변량 OOS: 시간순 70/30
        Xall = dec[FEATS].values.astype(float)
        good = ~np.isnan(Xall).any(axis=1)
        Xv = Xall[good]; yv = dec["y"].values[good]; ordv = dec["conf_time"].values[good].astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(ordv); cut = int(len(o) * 0.7)
        tr, te = o[:cut], o[cut:]
        if len(np.unique(yv[tr])) == 2 and len(np.unique(yv[te])) == 2:
            sc = StandardScaler().fit(Xv[tr])
            clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(sc.transform(Xv[tr]), yv[tr])
            p = clf.predict_proba(sc.transform(Xv[te]))[:, 1]
            auc = roc_auc_score(yv[te], p)
            med = np.median(p); topwr = 100 * yv[te][p >= med].mean(); botwr = 100 * yv[te][p < med].mean()
            print(f"  (B) 다변량 시간순 OOS(30%): AUC={auc:.3f} | 상위절반 성공 {topwr:.1f}% vs 하위절반 {botwr:.1f}% (기저 {100*yv[te].mean():.1f}%)", flush=True)
        # (C) CPCV 표준6 + ★Ablation(무엇이 진짜 알파인가 / rev_depth 동어반복 점검)
        SUBSETS = {
            "ALL(전체)": FEATS,
            "GEN_only(사전예측)": ["gen_oi_z", "gen_oi_chg1h", "gen_d_oi", "gen_cvd_norm", "gen_vol_ratio", "gen_bos_atr"],
            "OI_only(캡틴질문)": ["gen_oi_z", "gen_oi_chg1h", "gen_d_oi", "rev_d_oi_since"],
            "no_depth(동어반복제거)": [f for f in FEATS if f != "rev_depth"],
            "depth_only": ["rev_depth"],
            "cvd_only": ["rev_cvd_norm"],
            "ret_only(가격모멘텀)": ["rev_ret_atr"],
            "cvd+ret(독립기여?)": ["rev_cvd_norm", "rev_ret_atr"],
        }
        print(f"  (C) CPCV 표준{N_GROUPS} Ablation — AUC 중앙/p25 · 순효과 중앙", flush=True)
        for nm, sub in SUBSETS.items():
            cols = [FEATS.index(f) for f in sub]
            aucs, effs = cpcv(Xv[:, cols], yv, ordv)
            if len(aucs):
                print(f"     {nm:22s} AUC {np.median(aucs):.3f}/p25 {np.percentile(aucs,25):.3f}"
                      f"  순효과 {np.median(effs):+5.1f}%p  (>0.5 {100*np.mean(aucs>0.5):.0f}%)", flush=True)
        all_rows.append(R)
    out = pd.concat(all_rows, ignore_index=True)
    csv = os.path.join(OUTDIR, "260627_02_OBOICharacter_Stg2_OB_features.csv")
    out.to_csv(csv, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 70, flush=True)
    print(f"[산출] OB+feature 원장: {csv} ({len(out)}행)", flush=True)
    print("[해석] RankIC|0.05|+ & 분위차 큼 = 그 feature가 OB 가른다. CPCV AUC>0.55·순효과+ = OI/CVD 필터 가치.", flush=True)
    print("       전부 ~0.5/0%p면 = OI/CVD는 OB 신뢰도도 못 가름 → '에너지' 재확인, 필터 폐기.", flush=True)


if __name__ == "__main__":
    main()
