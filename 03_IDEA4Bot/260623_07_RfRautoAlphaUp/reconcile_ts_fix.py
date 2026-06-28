# -*- coding: utf-8 -*-
# [reconcile_ts_fix.py] 화해 — TS만 네이티브 피보+1m로 정정, REV는 원래 청산(3%트레일) 유지. 블렌드 20/80@노출.
#   목적: +137%가 '가짜'가 아님을 숫자로 확인. 진짜 불일치는 TS(20%)뿐 → 고쳐도 거의 안 변해야 정상.
#   REV월수익 = streams_monthly.csv(원래 3%트레일·검증된 +127%) 그대로. TS월수익 = ledger_ts_1m.csv(네이티브 피보·1m).
import os, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))


def mstat(m):
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    return tot, mdd, ((1 + tot / 100) ** (12 / len(m)) - 1) * 100


def cpcv(port):
    g6 = np.array_split(np.arange(len(port)), 6); cg = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c])); cg.append(mstat(port[te])[2])
    cg = np.array(cg); return np.percentile(cg, 25), cg.min(), 100 * (cg < 0).mean()


# REV(원래 3% 트레일·검증본)
sm = pd.read_csv(os.path.join(HERE, "streams_monthly.csv"))
rev = pd.Series(sm["rev"].values, index=[pd.Period(x, "M") for x in sm["month"]])
ts_fake = pd.Series(sm["ts"].values, index=[pd.Period(x, "M") for x in sm["month"]])

# TS(네이티브 피보+1m) 월수익 — ledger_ts_1m.csv 에 사이징 적용
L = pd.read_csv(os.path.join(HERE, "ledger_ts_1m.csv"))
med = L.atr_pct.median()
sat = np.clip(med / L.atr_pct.replace(0, med), 0.25, 1.0)
soi = np.clip(1 - 0.3 * np.maximum(0, L.oi_z - 1.5), 0.25, 1.0)
L["rs"] = L.R * sat * soi
L["m"] = pd.to_datetime(L.et).dt.to_period("M")
ts_fib = L.groupby("m").rs.apply(lambda x: (1 + x).prod() - 1)

allm = sorted(set(rev.index) | set(ts_fib.index) | set(ts_fake.index))
rev_s = rev.reindex(allm, fill_value=0.0).values
ts_fake_s = ts_fake.reindex(allm, fill_value=0.0).values
ts_fib_s = ts_fib.reindex(allm, fill_value=0.0).values

print("=" * 80)
print("화해 — TS만 정정(네이티브 피보+1m), REV는 검증된 원래 청산 유지")
print("=" * 80)
tf, mf, cf = mstat(ts_fake_s); tn, mn, cn = mstat(ts_fib_s)
print(f"TS 옛가짜(3%트레일): 월복리 {tf:+.0f}% MDD {mf:.1f}%   ({(ts_fake_s!=0).sum()}개월 활성)")
print(f"TS 네이티브피보+1m : 월복리 {tn:+.0f}% MDD {mn:.1f}%   ({(ts_fib_s!=0).sum()}개월 활성)  ← 거의 동급이면 TS청산영향 작음")
rt, rm, rc = mstat(rev_s)
print(f"REV(원래 3%트레일·검증): 월복리 {rt:+.0f}% MDD {rm:.1f}%")
print("-" * 80)
print(f"{'블렌드(TS,REV청산)':<28}{'노출':>5}{'복리%':>9}{'MDD%':>8}{'CAGR%':>8}{'CPCVp25':>9}{'-20내':>6}")
for nm, ts_s in [("옛: TS가짜+REV3%트레일", ts_fake_s), ("정정: TS피보+1m + REV3%트레일", ts_fib_s)]:
    port = 0.2 * ts_s + 0.8 * rev_s
    for e in [1.0, 1.2]:
        tot, mdd, cg = mstat(port * e); p25, worst, neg = cpcv(port * e)
        ok = "O" if (tot > 0 and p25 > 0 and mdd > -20) else "X"
        print(f"{nm:<28}{e:>5.1f}{tot:>+9.0f}{mdd:>+8.1f}{cg:>+8.1f}{p25:>+9.1f}{ok:>6}")
print("-" * 80)
print("[해석] '정정' 행이 +137%/-20% 근처면 = +137%는 가짜아님(TS청산만 미세영향). REV 원래청산이 정답.")
print("[정직] REV에 피보스텝업 강제 = 부적합(별도 실험서 +12%/-30%로 확인). REV 청산은 회귀용 유지가 옳음.")
