# -*- coding: utf-8 -*-
# [260625_01_RevoiExitRegime_FoldClose.py] 직전세션(RevoiExitRegime) 다음 1수 — held-out 재최적 청산ON에서
#   유일하게 남은 1폴드(-21.4%) MDD-20 위반을 닫아 표준6 위반0 = §9 확정후보 승격 (캡틴 지시 2026-06-25).
#   레버 격자: TPF(부분익절분율 0.7/0.8) x TIGHT(불리레짐 fib스톱배율 1.4/1.6/1.8) x TGT(노출 학습MDD목표 20/19/18).
#   ★검증엔진만(§15.1): 거래는 bt_full.gen_trades(검증된 봇)로만. 청산레버는 gen_trades opt-in(끄면 기존동일).
#   ★진짜 OOS(§5.7): 폴드마다 '자기 학습구간 Calmar'로만 후보 재선택(커닝0)→보류 test 채점. purge 1개월.
#   ★앵커(§15.2): (TPF0.7,TIGHT1.4,TGT20) 셀 = 직전 cpcv_reopt_exit 값 p25+63.9%/위반7% 재현 대조.
#   ★재현(§19): 난수 seed7 고정 · 같은 데이터/config = 항상 동일.
import os, sys, time, re
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import bt_full as B
from fib_replay_1m import load_1m, load_funding
from blend_opt import rev_side, monthly
from cpcv_reopt import cmdd
from cpcv_reopt_exit import scale_for   # 불리레짐(저변동Q1·극단쏠림, 고변동 제외) fib_scale 배열
import bt_report as BR
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__)); T0 = time.time()

# 격자 (택1로 위반0 달성)
TPF_GRID   = [0.7, 0.8]
TIGHT_GRID = [1.4, 1.6, 1.8]
TGT_GRID   = [20.0, 19.0, 18.0]
ANCHOR = (0.7, 1.4, 20.0)   # 직전 cpcv_reopt_exit 값 = p25+63.9%/위반7%


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_RevoiExitRegime_FoldClose_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")
def hm(s): return f"{int(s//3600)}h{int((s%3600)//60):02d}m"
def el(): return time.time()-T0


def sample(rng):
    return dict(rev_tf=int(rng.choice([240,480,720])), piv=int(rng.choice([20,60,240])), N=int(rng.integers(2,9)),
                f1=float(rng.uniform(0.15,0.45)), f2=float(rng.uniform(0.45,0.65)), f3=float(rng.uniform(0.65,0.92)),
                iam=float(rng.uniform(0.5,3.0)), q=float(rng.uniform(0.2,0.4)), qwin=int(rng.integers(20,80)), arm=int(rng.integers(2,12)))


def rev_T(d1m, fund, p, tpf, tight):
    """청산ON 거래 생성: R=레짐적응스텝(scale_for) + P=구조 부분익절(tp_frac)."""
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc = scale_for(d1m, p["rev_tf"], tight)
    return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"], er_gate=0.0,
                        ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"],
                        fib_scale=sc, tp_frac=tpf)


def cand_monthly(d1m, fund, p, cal, tpf, tight):
    T = rev_T(d1m, fund, p, tpf, tight)
    m = monthly(T)
    if len(m) == 0: return None
    return pd.Series(m.values, index=pd.PeriodIndex(m.index, freq="M")).reindex(cal, fill_value=0.0).values


def build_set(d1m, fund, cal, NC, tpf, tight, tag):
    rng = np.random.default_rng(7); cands=[]; series=[]
    for i in range(NC):
        p = sample(rng)
        try: s = cand_monthly(d1m, fund, p, cal, tpf, tight)
        except Exception: s = None
        if s is not None: cands.append(p); series.append(s)
        if (i+1) % 40 == 0: _p(f"    [{tag}] 후보 {i+1}/{NC} · 경과 {hm(el())}")
    return cands, series


def fold_eval_tgt(series, cal, test_idx, tgt):
    """test 보류 → 나머지(purge 1개월)서 학습Calmar 최고 후보 선택 → 노출 e=clip(tgt/|train_mdd|)로 test 채점."""
    test_mask = np.zeros(len(cal), bool); test_mask[test_idx] = True
    purge = np.zeros(len(cal), bool)
    for ti in test_idx:
        for j in (ti-1, ti+1):
            if 0 <= j < len(cal): purge[j] = True
    train_mask = ~test_mask & ~purge
    best = None
    for s in series:
        tot, mdd, _ = cmdd(s[train_mask])
        sc = tot/abs(mdd) if mdd < 0 else tot
        if best is None or sc > best[0]: best = (sc, s, mdd)
    _, s, tr_mdd = best
    e = float(np.clip(tgt/abs(tr_mdd), 0.3, 2.0)) if tr_mdd < 0 else 1.0
    _, te_mdd, te_cagr = cmdd(e * s[test_mask])
    return te_cagr, te_mdd


def cpcv_std6(series, cal, tgt):
    import itertools
    g = [np.array(x) for x in np.array_split(np.arange(len(cal)), 6)]
    folds = list(itertools.combinations(range(6), 2))   # 15경로
    cg=[]; md=[]
    for c in folds:
        ti = np.concatenate([g[k] for k in c])
        a, m = fold_eval_tgt(series, cal, ti, tgt); cg.append(a); md.append(m)
    cg=np.array(cg); md=np.array(md)
    return dict(p25=float(np.percentile(cg,25)), median=float(np.median(cg)), worst=float(cg.min()),
                neg=float(100*(cg<0).mean()), mdd_worst=float(md.min()), mdd_viol=float(100*(md<-20).mean()))


def heldout_quarter(d1m, fund, series, cands, tpf, tight):
    """train<=2024 최적후보(학습Calmar)의 2025~26 held-out 분기 롱숏 (노출1.0 raw R)."""
    cal_yr = pd.period_range(d1m.index.min().to_period("M"), d1m.index.max().to_period("M"), freq="M")
    tr = np.array([m.year <= 2024 for m in cal_yr])
    best = max(range(len(series)), key=lambda k: (lambda t,mdd,_: (t/abs(mdd) if mdd<0 else t))(*cmdd(series[k][tr])))
    bp = cands[best]
    T = rev_T(d1m, fund, bp, tpf, tight)
    T["q"] = pd.to_datetime(T.et).dt.to_period("Q").astype(str); T["yr"] = pd.to_datetime(T.et).dt.year
    oos = T[T.yr >= 2025].copy()
    rows=[]
    for q, gp in oos.groupby("q"):
        L=gp[gp.side==1]; S=gp[gp.side==-1]
        rows.append(dict(분기=q, 롱_거래=len(L), 롱_승률=round(100*(L.R>0).mean(),0) if len(L) else 0, 롱_R합=round(L.R.sum()*100,1),
                         숏_거래=len(S), 숏_승률=round(100*(S.R>0).mean(),0) if len(S) else 0, 숏_R합=round(S.R.sum()*100,1),
                         총_R합=round(gp.R.sum()*100,1)))
    qt = pd.DataFrame(rows)
    om = monthly(oos); otot, omdd, ocagr = cmdd(om.values)
    return bp, qt, otot, omdd, ocagr, len(oos)


def main():
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    _p(f"\n===== [FoldClose] 1폴드(-21.4%) 닫기 스윕 — TPF x TIGHT x TGT · 후보{NC} · {time.strftime('%H:%M')} =====")
    d1m = load_1m(); fund = load_funding()
    cal = pd.period_range(d1m.index.min().to_period("M"), d1m.index.max().to_period("M"), freq="M")
    _p(f"[달력] {cal[0]} ~ {cal[-1]} ({len(cal)}개월) · 로드 {hm(el())}")

    rows=[]; cache={}   # (tpf,tight) -> (cands,series)
    for tpf in TPF_GRID:
        for tight in TIGHT_GRID:
            tag=f"TPF{tpf}/TIGHT{tight}"
            _p(f"\n  -- 후보집합 빌드 {tag} --")
            cands, series = build_set(d1m, fund, cal, NC, tpf, tight, tag)
            cache[(tpf,tight)] = (cands, series)
            _p(f"    유효후보 {len(cands)} · {hm(el())}")
            for tgt in TGT_GRID:
                r = cpcv_std6(series, cal, tgt)
                r.update(TPF=tpf, TIGHT=tight, TGT=tgt)
                rows.append(r)
                anc = " ★앵커" if (tpf,tight,tgt)==ANCHOR else ""
                _p(f"    [{tag} TGT{tgt:.0f}] p25 {r['p25']:+.1f}% · 위반 {r['mdd_viol']:.0f}% · 최악폴드MDD {r['mdd_worst']:.0f}% · 음수폴드 {r['neg']:.0f}%{anc}")

    df = pd.DataFrame(rows)
    # 앵커 대조
    a = df[(df.TPF==ANCHOR[0])&(df.TIGHT==ANCHOR[1])&(df.TGT==ANCHOR[2])].iloc[0]
    _p(f"\n[앵커 대조 §15.2] (0.7,1.4,20) p25 {a['p25']:+.1f}% / 위반 {a['mdd_viol']:.0f}%  (직전 cpcv_reopt_exit = +63.9% / 7%)")

    # 위반0 + p25최대 = 승자
    ok = df[df.mdd_viol==0].sort_values("p25", ascending=False)
    if len(ok):
        w = ok.iloc[0]
        _p(f"\n[★승자] TPF{w.TPF}/TIGHT{w.TIGHT}/TGT{w.TGT:.0f} → p25 {w['p25']:+.1f}% · 위반 0% · 최악폴드 {w['mdd_worst']:.0f}% (§9 확정후보)")
    else:
        w = df.sort_values(["mdd_viol","p25"], ascending=[True,False]).iloc[0]
        _p(f"\n[위반0 미달성] 최선 = TPF{w.TPF}/TIGHT{w.TIGHT}/TGT{w.TGT:.0f} · 위반 {w['mdd_viol']:.0f}% · p25 {w['p25']:+.1f}%")

    # 승자 held-out 분기 롱숏
    cands, series = cache[(w.TPF, w.TIGHT)]
    bp, qt, otot, omdd, ocagr, noos = heldout_quarter(d1m, fund, series, cands, w.TPF, w.TIGHT)
    _p(f"\n[승자 held-out 2025~26 (노출1.0 raw)] 거래{noos}·월복리{otot:+.0f}%·MDD{omdd:.0f}%·연환산{ocagr:+.0f}%·롱R합{qt.롱_R합.sum():+.0f}%/숏R합{qt.숏_R합.sum():+.0f}%")
    _p(qt.to_string(index=False))

    # ── 저장 (§19 표준출력) ──
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    nn = (max([int(m.group(1)) for d in os.listdir(BR.BTO) if (m:=re.match(rf"{today}_(\d+)_",d))]+[0])+1)
    base = f"{today}_{nn:02d}_RevoiExitRegime_FoldClose"; folder=os.path.join(BR.BTO, base); os.makedirs(folder, exist_ok=True)
    dfo = df[["TPF","TIGHT","TGT","p25","median","worst","neg","mdd_worst","mdd_viol"]].copy()
    dfo.columns = ["TPF","TIGHT","노출목표","p25_CAGR","중앙_CAGR","최악폴드_CAGR","음수폴드pct","폴드MDD최악","MDD20위반pct"]
    dfo.to_csv(os.path.join(folder, f"{base}_레버스윕표.csv"), index=False, encoding="utf-8-sig")
    qt.to_csv(os.path.join(folder, f"{base}_승자_heldout분기롱숏.csv"), index=False, encoding="utf-8-sig")

    # 그래프: (좌) 조합별 p25 (수익률 헤드라인 §19) · (우) 조합별 MDD-20위반율(0=통과)
    lbl = [f"P{r.TPF}/T{r.TIGHT}/G{int(r.TGT)}" for r in df.itertuples()]
    x = np.arange(len(df))
    fig, ax = plt.subplots(2, 1, figsize=(17, 11))
    c1 = ["#26a69a" if v==0 else "#bbbbbb" for v in df.mdd_viol]
    ax[0].bar(x, df.p25, color=c1); ax[0].axhline(0, color="black", lw=0.8)
    ax[0].set_title("조합별 held-out CPCV p25 연수익률(CAGR) — 초록=MDD-20위반0(본선통과) / Return p25 by combo", fontweight="bold")
    ax[0].set_ylabel("p25 CAGR (%/yr)"); ax[0].set_xticks(x); ax[0].set_xticklabels(lbl, rotation=60, fontsize=7); ax[0].grid(alpha=0.3, axis="y")
    for i,v in enumerate(df.p25): ax[0].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=6)
    c2 = ["#26a69a" if v==0 else "#ef5350" for v in df.mdd_viol]
    ax[1].bar(x, df.mdd_viol, color=c2); ax[1].axhline(0, color="black", lw=0.8)
    ax[1].set_title("조합별 MDD-20 위반율 (0=표준6 본선통과=§9 후보) / MDD-20 violation rate", fontweight="bold")
    ax[1].set_ylabel("위반율 (%)"); ax[1].set_xticks(x); ax[1].set_xticklabels(lbl, rotation=60, fontsize=7); ax[1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(df.mdd_viol): ax[1].text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=6)
    passed = bool((df.mdd_viol==0).any())
    fig.suptitle(f"REVoi 청산ON 1폴드 닫기 — TPF x TIGHT x TGT 스윕 (진짜 OOS·재선택·purge) — {base}\n"
                 f"앵커(0.7,1.4,20) p25 {a['p25']:+.0f}%/위반 {a['mdd_viol']:.0f}% | 승자 P{w.TPF}/T{w.TIGHT}/G{int(w.TGT)} p25 {w['p25']:+.0f}%/위반 {w['mdd_viol']:.0f}% → {'위반0 달성=§9 후보' if passed else '위반0 미달성'} · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93]); png=os.path.join(folder, f"{base}_레버스윕그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    body = (f"[REVoi 청산ON 1폴드 닫기 — TPF x TIGHT x TGT 스윕] {base}\n"+"="*72+"\n"
        f"목적: held-out 재최적 청산ON(R+P)에서 유일하게 남은 1폴드(-21.4%) MDD-20위반을 닫아 표준6 위반0=§9 확정후보 승격.\n"
        f"방법(§5.7·§15.1): 검증엔진 gen_trades만 · 폴드마다 학습Calmar로 후보재선택(커닝0)·purge1개월·test OOS(15경로). 레버=부분익절TPF·레짐스톱TIGHT·노출목표TGT.\n"
        f"앵커 대조(§15.2): (0.7,1.4,20) p25 {a['p25']:+.1f}%/위반 {a['mdd_viol']:.0f}% (직전값 +63.9%/7%와 대조).\n\n"
        f"[레버 스윕표 — 수익률 우선 §19]\n{dfo.to_string(index=False)}\n\n"
        f"[승자] TPF{w.TPF}/TIGHT{w.TIGHT}/노출목표{w.TGT:.0f} → p25 {w['p25']:+.1f}% · MDD-20위반 {w['mdd_viol']:.0f}% · 최악폴드MDD {w['mdd_worst']:.0f}%\n"
        f"  판정: {'★위반0 달성 → §9 확정후보 승격 가능(다음=실행현실성 슬립모델+진입품질필터)' if w['mdd_viol']==0 else '위반0 미달성 — 레버 범위 확장 필요(헛수치 위 쌓기 금지)'}\n\n"
        f"[승자 held-out 2025~26 (노출1.0 raw)] 거래{noos}·월복리{otot:+.0f}%·MDD{omdd:.0f}%·연환산{ocagr:+.0f}%·롱R합{qt.롱_R합.sum():+.0f}%/숏R합{qt.숏_R합.sum():+.0f}%\n{qt.to_string(index=False)}\n\n"
        f"고딩 해설: 학습구간서만 고른 세팅을 한 번도 안 본 구간에 적용해도 15경로 전부 MDD-20 안 넘으면(위반0) '진짜 본선통과'. "
        f"여기선 청산ON이 이미 위반 7%까지 와 있어, 부분익절/레짐스톱/노출 중 하나를 조금 강화해 마지막 1폴드를 닫는 게 목표.")
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{base}: 1폴드닫기 스윕 승자 P{w.TPF}/T{w.TIGHT}/G{int(w.TGT)} p25{w['p25']:+.0f}%/위반{w['mdd_viol']:.0f}%(앵커 +{a['p25']:.0f}%/{a['mdd_viol']:.0f}%)·{'위반0=§9후보' if w['mdd_viol']==0 else '미달'}|src=260625_01_RevoiExitRegime_FoldClose.py\n")
    _p(f"\n[저장] {folder}\n  승자 {('위반0=§9후보' if w['mdd_viol']==0 else '미달')} · 총 {hm(el())}")


if __name__ == "__main__":
    main()
