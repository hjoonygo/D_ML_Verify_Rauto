# -*- coding: utf-8 -*-
# [max_return_search.py] MDD 무시·수익 최고 세팅 + 월수익 최고 세팅 탐색 (캡틴 지시 2026-06-24).
#   ★주의: 선형 블렌드모델은 고노출서 강제청산 미반영 → 수익 과대(환상). MDD를 같이 표기해 정직화.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import blend_opt as BO
HERE = os.path.dirname(os.path.abspath(__file__)); TRAIN = pd.Period("2024-12", "M")


def _p(*a): print(*a, flush=True)


def cmdd(m):
    if len(m) < 2: return 0.0, 0.0, 0.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    return tot, mdd, np.mean(m) * 100


def sample(rng):
    return dict(ts_tf=int(rng.choice([240, 420, 480, 720])), rev_tf=int(rng.choice([240, 480, 720])),
                piv=int(rng.choice([20, 60, 240])), N=int(rng.integers(2, 9)),
                f1=float(rng.uniform(0.15, 0.45)), f2=float(rng.uniform(0.45, 0.65)), f3=float(rng.uniform(0.65, 0.92)),
                iam=float(rng.uniform(0.5, 3.0)), erg=float(rng.uniform(0.0, 0.4)),
                q=float(rng.uniform(0.2, 0.4)), qwin=int(rng.integers(20, 80)),
                arm=int(rng.integers(2, 12)), w=float(rng.uniform(0.4, 0.95)),
                expo=float(rng.uniform(0.5, 3.0)))


def prof(d1m, fund, p):
    port1, months, cnt = BO.blend_series(d1m, fund, p)
    if port1 is None: return None
    port = p["expo"] * port1; tr = months <= TRAIN; te = ~tr
    tot, mdd, mean = cmdd(port); _, vmdd, _ = cmdd(port[te]); vtot = cmdd(port[te])[0]
    return dict(tot=tot, mdd=mdd, mean=mean, vtot=vtot, vmdd=vmdd, nts=cnt[0], nrev=cnt[1])


def show(tag, p, r):
    _p(f"\n[{tag}]")
    _p(f"  세팅: TS_TF={p['ts_tf']} REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} "
       f"피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f} er{p['erg']:.2f}")
    _p(f"        REV분위{p['q']:.2f}/롤링{p['qwin']} arm{p['arm']} | w_rev={p['w']:.2f} 노출={p['expo']:.2f}")
    _p(f"  성적: 전체복리 {r['tot']:+.0f}% · 월평균 {r['mean']:+.2f}% · 전체MDD {r['mdd']:.0f}% · "
       f"검증OOS {r['vtot']:+.0f}%/MDD{r['vmdd']:.0f}% · TS{r['nts']}·REV{r['nrev']}거래")


def main():
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    d1m = load_1m(); fund = load_funding(); rng = np.random.default_rng(7)
    _p(f"[탐색 {NC}개] MDD무시·수익최고 + 월수익최고 (노출 0.5~3.0 포함)")
    best_tot = None; best_mean = None
    for i in range(NC):
        p = sample(rng)
        try:
            r = prof(d1m, fund, p)
        except Exception:
            r = None
        if r is None: continue
        if best_tot is None or r["tot"] > best_tot[1]["tot"]: best_tot = (p, r)
        if best_mean is None or r["mean"] > best_mean[1]["mean"]: best_mean = (p, r)
    show("① MDD무시 전체복리 최고", *best_tot)
    show("② 월평균 수익률 최고", *best_mean)
    json.dump({"max_total": best_tot[0], "max_monthly": best_mean[0]},
              open(os.path.join(HERE, "max_return_setting.json"), "w"), indent=2, ensure_ascii=False)
    _p("\n[★정직] 위 수익은 선형모델 — 고노출선 한 달 폭락이 강제청산(잔고 0)인데 모델은 -노출×%로 과대계산.")
    _p("       즉 '①복리 최고'는 실제론 청산으로 달성불가한 환상 상한. MDD가 큰 세팅일수록 더 가짜.")
    _p("       진짜 채택은 CPCV 표준6 + MDD-20(별도). 이건 '상한이 어디냐'만 보는 참고용. 저장 max_return_setting.json")


if __name__ == "__main__":
    main()
