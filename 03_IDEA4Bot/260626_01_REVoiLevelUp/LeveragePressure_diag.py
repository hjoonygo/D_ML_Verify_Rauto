# -*- coding: utf-8 -*-
# [LeveragePressure_diag.py] 세션 260626_01_REVoiLevelUp · Stg1 (REVoi 휩소필터 1단계)
# 목적: REVoi 932거래 원장 위에서 '레버리지 과열압력(LP)' 진입솎기 휩소필터를 격자스윕.
#   ★무손상 앵커(레버3/증거금75/필터OFF = +1851.6% 슬립0) 재현 후에만 진단(§15.2 앵커대조).
#   ★강제청산 = 캡틴 정의(2026-06-26): 손실=유지증거금(size%/100)만, 수수료·슬립·펀딩 0가산.
#       → 고레버+급변동서 시장가청산 슬립보다 손실 작음 = '계좌 구하는 캡'. 횟수 의무 산출.
#   ★MDD 4단 게이트(§26): M0 무제한 / M30 ≥−30% / M25 ≥−25% / M20 ≥−20% 각 최고복리 + 강제청산 횟수.
#   ★룩어헤드0: LP 재료(atr60·oiz_s·fund_s·ls_s)는 진입시각 et '이하' 최신 1분(asof, regime_diag 방식).
#   ★1단계 한계(정직): 고정TF(4h 앵커원장) 위 레버·size·LP임계 스윕만. 스톱타이트·TF스윕은 거래재생성 필요=2단계.
import os, numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LED = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260624_13_REVoi_MDD25_36mo_v6\260624_13_REVoi_MDD25_36mo_v6_거래원장.csv"
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
MMR_T1, MMR_T2, TIER, COST, SLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005
ANCHOR_LEV, ANCHOR_SZ, ANCHOR_TOT = 3, 75, 1851.6   # §25 슬립0 앵커(+1851.6%/MDD-24.6%/청산0)
LEVG = [2, 3, 4, 5, 6, 8, 10, 12, 15]
SZG  = [50, 60, 70, 75, 80, 90, 100]
LPQ  = {"OFF": None, "상위40%": 0.60, "상위25%": 0.75, "상위10%": 0.90}  # LP_lv 이 분위 '초과' 거래는 진입 솎기(skip)
GATES = [("M0_무제한", None), ("M30", -30.0), ("M25", -25.0), ("M20", -20.0)]


def _p(*a): print(*a, flush=True)


def load():
    L = pd.read_csv(LED, parse_dates=["et", "xt"]).sort_values("et").reset_index(drop=True)
    R = pd.read_parquet(REG); R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
    R = R.set_index("timestamp").sort_index()
    pos = np.searchsorted(R.index.values, L["et"].values, side="right") - 1  # et 이하 최신 분(룩어헤드0)
    pos = np.clip(pos, 0, len(R) - 1)
    for c in ["atr60", "oiz_s", "fund_s", "ls_s"]:
        L[c] = R[c].values[pos]
    L["oiz_abs"] = L.oiz_s.abs(); L["fund_abs"] = L.fund_s.abs(); L["ls_abs"] = L.ls_s.abs()
    L["q"] = L["et"].dt.to_period("Q").astype(str)
    return L


def zc(x):
    x = np.asarray(x, float)
    z = (x - np.nanmean(x)) / (np.nanstd(x) + 1e-9)
    return np.nan_to_num(z, nan=0.0)  # NaN(초기 펀딩무) → 0(중립): LP 기여 0, 컷 마스크 NaN 오염 방지


def build_LP(L):
    # 레버리지 과열압력 = OI충격 + 펀딩극단 + 롱숏쏠림 (절대크기 z합)
    LP = zc(L.oiz_abs) + zc(L.fund_abs) + zc(L.ls_abs)
    # 저변동 가중: atr60 낮을수록 휩소위험↑. 고변동(atr60 큼)=REVoi 최고수익이라 컷 금지(§20) → -z(atr60)
    LP_lv = LP + (-zc(L.atr60))
    return LP, LP_lv


def curve(R, MAE, FUND, MK, size, lev, skip, captain=True):
    """격리마진 청산복리. captain=True: 캡틴 캡모델(청산손실=증거금만). False: 기존 liq_eval 1:1(앵커검증).
       반환 (복리%, MDD%, 단일최고월%, 청산횟수, 진입거래수)."""
    exp = size / 100.0 * lev; bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0; ntr = 0; mfac = {}
    for i in range(len(R)):
        if skip is not None and skip[i]:
            continue
        ntr += 1
        mmr = MMR_T2 if exp * bal > TIER else MMR_T1
        if captain:
            trig = 1.0 / lev - mmr                       # 캡틴: 슬립 무관 청산선
            if MAE[i] <= -trig:
                p = -exp * (1.0 / lev); nliq += 1        # ★증거금만(비용·슬립·펀딩 0)
            else:
                p = R[i] * exp
        else:
            hsd = 1.0 / lev - mmr - SLIP                  # 기존 liq_eval 1:1
            if MAE[i] <= -hsd:
                p = -exp * (hsd + COST + abs(FUND[i])); nliq += 1
            else:
                p = R[i] * exp
        bal *= (1.0 + p)
        if bal > peak: peak = bal
        dd = bal / peak - 1.0
        if dd < mdd: mdd = dd
        mfac[MK[i]] = mfac.get(MK[i], 1.0) * (1.0 + p)
        if bal <= 0:
            return -100.0, -100.0, -100.0, nliq, ntr
    tot = (bal / 10000.0 - 1.0) * 100.0
    bm = (max(mfac.values()) - 1.0) * 100.0 if mfac else 0.0
    return tot, mdd * 100.0, bm, nliq, ntr


def sweep(R, MAE, FUND, MK, skip):
    """레버×size 격자 → 4단 MDD 게이트별 최고복리 세팅. 반환 dict(gate -> (lev,size,tot,mdd,nliq,ntr))."""
    rows = []
    for lev in LEVG:
        for sz in SZG:
            tot, mdd, bm, nl, nt = curve(R, MAE, FUND, MK, sz, lev, skip, captain=True)
            rows.append((lev, sz, tot, mdd, bm, nl, nt))
    best = {}
    for gname, gmdd in GATES:
        cand = [r for r in rows if (gmdd is None or r[3] >= gmdd)]
        if not cand:
            best[gname] = None; continue
        best[gname] = max(cand, key=lambda r: r[2])  # 최고복리
    return best, rows


def main():
    L = load()
    R = L["R"].values.astype(float); MAE = L["mae"].values.astype(float); FUND = L["fund"].values.astype(float)
    MK = L["et"].dt.to_period("M").astype(str).values
    _p("=" * 86)
    _p(f"[REVoi 레버리지 과열압력(LP) 휩소필터 — 1단계] 거래 {len(L)} · 데이터 {L.et.min().date()}~{L.et.max().date()}")

    # ── 관문0: 무손상 앵커 재현(필터 OFF, 레버3/size75) ──
    a_orig = curve(R, MAE, FUND, MK, ANCHOR_SZ, ANCHOR_LEV, None, captain=False)
    a_capt = curve(R, MAE, FUND, MK, ANCHOR_SZ, ANCHOR_LEV, None, captain=True)
    _p("\n[관문0 · 무손상 앵커 재현] 레버3/증거금75/노출2.25/필터OFF")
    _p(f"   기존 liq_eval 1:1 : 복리 {a_orig[0]:+.1f}% · MDD {a_orig[1]:.1f}% · 청산 {a_orig[3]}회  (앵커 기준 +{ANCHOR_TOT}%)")
    _p(f"   캡틴 캡모델       : 복리 {a_capt[0]:+.1f}% · MDD {a_capt[1]:.1f}% · 청산 {a_capt[3]}회")
    diff = a_orig[0] - ANCHOR_TOT
    ok = abs(diff) < 5.0  # ±5%p 이내면 무손상(미세 비용/원장버전 차)
    _p(f"   → 앵커 일치: {'✅ 무손상' if ok else '⚠️ 불일치(원인규명 필요)'} (차이 {diff:+.1f}%p) · 두 모델 동일(청산0): {'예' if abs(a_orig[0]-a_capt[0])<1.0 else '아니오'}")

    # ── LP 합성 ──
    LP, LP_lv = build_LP(L)
    L["LP"] = LP; L["LP_lv"] = LP_lv

    # ── 손실거래가 LP 과열에 몰렸나(진단) ──
    win = L.R > 0; los = L.R <= 0
    _p("\n[LP 진단] LP_lv(레버리지 과열+저변동) 평균 — 승/패 거래 대조")
    _p(f"   승 거래({win.sum()}): LP_lv {L.LP_lv[win].mean():+.3f} · 패 거래({los.sum()}): LP_lv {L.LP_lv[los].mean():+.3f}  (패>승면 휩소필터 유효)")

    # ── 관문: 4단 MDD 게이트 × LP임계 ──
    _p("\n" + "=" * 86)
    _p("[4단 MDD 게이트 × LP 진입솎기] 각 칸 = 최고복리 세팅 (레버/증거금 → 복리% / MDD% / 강제청산회 / 진입수)")
    head = f"{'LP임계':<8}" + "".join([f"{g[0]:>22}" for g in GATES])
    _p(head)
    out_rows = []
    for lpname, q in LPQ.items():
        if q is None:
            skip = None; nskip = 0
        else:
            thr = np.quantile(LP_lv, q); skip = (LP_lv > thr); nskip = int(skip.sum())
        best, _ = sweep(R, MAE, FUND, MK, skip)
        line = f"{lpname:<8}"
        for gname, _g in GATES:
            b = best[gname]
            if b is None:
                line += f"{'-':>22}"
            else:
                line += f"{f'L{b[0]}/{b[1]}%→{b[2]:+.0f}/{b[3]:.0f}/{b[5]}/{b[6]}':>22}"
            if b is not None:
                out_rows.append(dict(LP임계=lpname, 솎은거래=nskip, 게이트=gname, 레버=b[0], 증거금=b[1],
                                     복리=round(b[2], 1), MDD=round(b[3], 1), 강제청산=b[5], 진입수=b[6]))
        _p(line + f"   (솎음 {nskip})")

    df = pd.DataFrame(out_rows)
    os.makedirs(HERE, exist_ok=True)
    df.to_csv(os.path.join(HERE, "LP_4gate_sweep.csv"), index=False, encoding="utf-8-sig")

    # ── 분기 수익률: OFF vs ON (M20 게이트 최고복리 세팅끼리, 헤드라인=수익률 §19) ──
    def quarterly(skip, lev, sz):
        sub = L.copy()
        keep = np.ones(len(L), bool) if skip is None else ~skip
        exp = sz / 100.0 * lev
        rows = []
        for qn, g in sub[keep].groupby("q"):
            idx = g.index.values
            # 사이즈드 P&L 근사(복리는 위 curve가 정밀, 여기선 분기 비교용 R합 사이즈드)
            longR = g[g.side > 0].R.sum() * exp * 100; shortR = g[g.side < 0].R.sum() * exp * 100
            rows.append((qn, len(g), round(longR + shortR, 1), round(longR, 1), round(shortR, 1)))
        return pd.DataFrame(rows, columns=["분기", "거래", "총_R%(사이즈드)", "롱_R%", "숏_R%"])

    off_b = None; on_b = None
    for r in out_rows:
        if r["게이트"] == "M20" and r["LP임계"] == "OFF": off_b = r
        if r["게이트"] == "M20" and r["LP임계"] == "상위25%": on_b = r
    _p("\n" + "=" * 86)
    _p("[분기 수익률 · M20 게이트] (헤드라인=수익률 §19)")
    if off_b:
        _p(f"\n  [OFF] 레버{off_b['레버']}/증거금{off_b['증거금']}% (필터 없음)")
        _p(quarterly(None, off_b["레버"], off_b["증거금"]).to_string(index=False))
    if on_b:
        thr = np.quantile(LP_lv, 0.75); skip_on = LP_lv > thr
        _p(f"\n  [ON·상위25% 솎음] 레버{on_b['레버']}/증거금{on_b['증거금']}%")
        _p(quarterly(skip_on, on_b["레버"], on_b["증거금"]).to_string(index=False))

    # ── ★순수 LP 효과 분리: 같은 (레버,size) 고정 OFF vs 상위25% 솎기 (노출효과 제거) ──
    _p("\n" + "=" * 86)
    _p("[★순수 LP 효과 — 같은 노출 고정 OFF vs ON(상위25% 솎기)] 노출효과 제거 = LP 알파만")
    thr25 = np.quantile(LP_lv, 0.75); skip25 = (LP_lv > thr25)
    _p(f"{'레버/증거금':<11}{'노출':>5}{'OFF복리%':>11}{'OFF_MDD':>9}{'ON복리%':>11}{'ON_MDD':>9}{'Δ복리%p':>10}{'Δ청산':>7}")
    for lev, sz in [(2, 80), (3, 75), (4, 70), (5, 60), (6, 50), (3, 100), (5, 100), (8, 80)]:
        o = curve(R, MAE, FUND, MK, sz, lev, None, captain=True)
        n = curve(R, MAE, FUND, MK, sz, lev, skip25, captain=True)
        flag = "↑" if n[0] > o[0] else "↓"
        _p(f"{f'L{lev}/{sz}%':<11}{sz/100*lev:>5.1f}{o[0]:>11.0f}{o[1]:>9.1f}{n[0]:>11.0f}{n[1]:>9.1f}{n[0]-o[0]:>9.0f}{flag}{o[3]-n[3]:>7}")
    _p("  해설: 같은 노출에서 ON복리>OFF복리(Δ>0)면 = 순수 LP 알파(노출효과 아님). MDD도 ON이 얕으면 휩소필터 진짜.")

    _p("\n[저장] LP_4gate_sweep.csv")
    _p("[정직 注] 1단계=고정4h원장 위 레버·size·LP임계만. 스톱타이트·TF(2/6/8h)스윕=거래재생성 2단계. 채택=Back2TV·4관문·CPCV 별도.")


if __name__ == "__main__":
    main()
