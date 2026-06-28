# -*- coding: utf-8 -*-
# [trade_diagnostics.py] 거래 사후분석 계측·분석 (Work_Order 과제A, 선행연구 MAE/MFE·Edge Ratio Sweeney 1996).
#   목적: 최강결합 V0(mom+oi)의 거래를 자동 진단분류(진입즉시SL/수익내다손절/큰수익후큰반납)하고
#         수익성 갉아먹는 원인(MDD·연속손절·손익비격감)을 수치로 확정.
#   ★1m 실체결·갭반영(낙관금지) 유지. realistic_sl_sim_regime.py 시뮬을 계측 확장.
#   심는 계측(거래별): mae·mfe·t_to_mfe·giveback·edge_ratio·entry/exit_eff·mfe_capture·
#                      exit_tag(initial_SL/trailing/maxhold 분리)·near_miss_sl·regime_at_entry(vr)·
#                      vol_at_entry·loss_streak·prev_result.
import os, sys, itertools
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008; SL_PCT = 0.02; TRAIL = 0.03; ENTRY_Q = 0.33; MAX_HOLD = 60
VR_W = 45; VR_Q = 4


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def find_data():
    # self-locating: RfRauto(이관 후) 우선, 없으면 Verify 원본
    for c in [r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv",
              r"D:\ML\Verify\Merged_Data.csv"]:
        if os.path.exists(c): return c
    raise FileNotFoundError("Merged_Data.csv 못 찾음")


def build_signal(DATA):
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["open", "high", "low"]).sort_values("t").reset_index(drop=True)
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first().dropna()
    oi8 = g["oi_zscore_24h"].last().shift(1)
    S = pd.DataFrame({"open8": o8}).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    ret8 = S["open8"].pct_change(1)
    rq = S["open8"].pct_change(VR_Q)
    S["vr"] = rq.rolling(VR_W).var() / (VR_Q * ret8.rolling(VR_W).var() + 1e-12)
    S["vol8"] = ret8.rolling(VR_W).std()
    S = S.dropna(subset=["mom_24h", "oi_z"])
    S["combo"] = (-zr(S["mom_24h"])) * 0.048 + (-zr(S["oi_z"])) * 0.037
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    return d, S


def simulate_instrumented(d, S):
    entry_side = S["side"].to_dict(); vr_of = S["vr"].to_dict(); vol_of = S["vol8"].to_dict()
    bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    trades = []; pos = 0; cur_vr = np.nan; cur_vol = np.nan
    streak = 0; prev_ret = np.nan
    entry = et = init_sl = TS = None; i_entry = 0; bars_held = 0
    hi_px = lo_px = i_hi = i_lo = None  # MFE/MAE 추적
    for i in range(len(d)):
        t = ti.iloc[i]
        if t in bar8:
            v = vr_of.get(t, np.nan); vv = vol_of.get(t, np.nan)
            if not (isinstance(v, float) and np.isnan(v)): cur_vr = v
            if not (isinstance(vv, float) and np.isnan(vv)): cur_vol = vv
        if pos == 0:
            sd = entry_side.get(t, 0)
            if t in bar8 and sd != 0:
                pos = int(sd); entry = O[i]; et = t; i_entry = i; bars_held = 0
                init_sl = entry * (1 - SL_PCT) if pos == 1 else entry * (1 + SL_PCT)
                TS = init_sl
                hi_px = H[i]; lo_px = L[i]; i_hi = i_lo = i
                entry_vr = cur_vr; entry_vol = cur_vol; entry_streak = streak; entry_prev = prev_ret
        else:
            # 보유중 MFE/MAE 갱신 (이 봉)
            if H[i] > hi_px: hi_px = H[i]; i_hi = i
            if L[i] < lo_px: lo_px = L[i]; i_lo = i
            exit_px = None; reason = None
            if pos == 1 and L[i] <= TS:
                exit_px = min(O[i], TS); reason = "stop"
            elif pos == -1 and H[i] >= TS:
                exit_px = max(O[i], TS); reason = "stop"
            if exit_px is None and t in bar8:
                bars_held += 1
                if bars_held >= MAX_HOLD:
                    exit_px = O[i]; reason = "maxhold"
            if exit_px is not None:
                realized = pos * (exit_px - entry) / entry
                ret = realized - COST
                # 계측
                if pos == 1:
                    mfe = (hi_px - entry) / entry; mae = (entry - lo_px) / entry; i_mfe = i_hi
                else:
                    mfe = (entry - lo_px) / entry; mae = (hi_px - entry) / entry; i_mfe = i_lo
                mfe = max(mfe, 0.0); mae = max(mae, 0.0)
                # exit_tag: 트레일이 초기SL 위로 올라갔나
                if reason == "maxhold":
                    tag = "maxhold"
                else:
                    moved = (TS > init_sl + 1e-9) if pos == 1 else (TS < init_sl - 1e-9)
                    tag = "trailing" if moved else "initial_SL"
                trades.append(dict(
                    et=et, xt=t, side=pos, entry=entry, exit=exit_px, ret=ret, realized=realized,
                    reason=reason, exit_tag=tag, year=pd.Timestamp(et).year,
                    mfe=mfe, mae=mae, giveback=mfe - realized,
                    edge_ratio=(mfe / mae if mae > 1e-9 else np.nan),
                    mfe_capture=(realized / mfe if mfe > 1e-9 else np.nan),
                    near_miss_sl=int(mae >= SL_PCT * 0.9),
                    t_to_mfe_min=(i_mfe - i_entry), hold_min=(i - i_entry),
                    vr=entry_vr, vol=entry_vol, loss_streak=entry_streak, prev_ret=entry_prev))
                # 시퀀스 갱신
                streak = streak + 1 if ret < 0 else 0
                prev_ret = ret; pos = 0
            else:
                if pos == 1:
                    TS = max(TS, hi_px * (1 - TRAIL))
                else:
                    TS = min(TS, lo_px * (1 + TRAIL))
    return pd.DataFrame(trades)


def pf(r):
    g = r[r > 0].sum(); b = -r[r < 0].sum()
    return g / b if b > 1e-12 else np.inf


def main():
    DATA = find_data(); _p(f"[데이터] {DATA}")
    d, S = build_signal(DATA)
    T = simulate_instrumented(d, S)
    _p(f"[거래] {len(T)}건 | 승률 {100*(T.ret>0).mean():.0f}% | 복리 "
       f"{((1+T.ret).cumprod().iloc[-1]-1)*100:+.1f}% | PF {pf(T.ret.values):.2f}")

    # ── 1) 거래 택소노미 (3분류) ──
    _p("\n【1】 거래 택소노미 — 진입즉시SL / 수익내다손절 / 큰수익후반납")
    loss = T[T.ret < 0]; win = T[T.ret > 0]
    _p(f"  전체: 손실 {len(loss)} / 이익 {len(win)}")
    cats = [("진입즉시SL (MFE<1%)", loss[loss.mfe < 0.01]),
            ("수익내다손절 (MFE 1~3%)", loss[(loss.mfe >= 0.01) & (loss.mfe < 0.03)]),
            ("큰수익후반납 (MFE>=3%)", loss[loss.mfe >= 0.03])]
    for nm, s in cats:
        if len(s):
            _p(f"  {nm:<24} {len(s):3d}건({100*len(s)/len(loss):.0f}%) | 평균MFE {s.mfe.mean()*100:.2f}% "
               f"| 평균반납 {s.giveback.mean()*100:.2f}% | 손익합 {s.ret.sum()*100:+.1f}%p")
    _p(f"  이익거래 {len(win)}건: 평균MFE {win.mfe.mean()*100:.2f}% 평균capture {win.mfe_capture.mean()*100:.0f}% "
       f"(본 이익 중 챙긴 %) 평균반납 {win.giveback.mean()*100:.2f}%")

    # ── 2) exit_tag 분리 (initial_SL vs trailing vs maxhold) ──
    _p("\n【2】 청산 종류 분리 (진입문제 vs 청산문제)")
    for tag, g in T.groupby("exit_tag"):
        _p(f"  {tag:<12} {len(g):3d}건({100*len(g)/len(T):.0f}%) | 승률 {100*(g.ret>0).mean():.0f}% "
           f"| 평균ret {g.ret.mean()*100:+.2f}% | 손익합 {g.ret.sum()*100:+.1f}%p | 평균MAE {g.mae.mean()*100:.2f}%")

    # ── 3) Drawdown attribution ──
    _p("\n【3】 MDD 귀속 (어떤 거래가 MDD를 만드나)")
    T2 = T.reset_index(drop=True); eq = (1 + T2.ret).cumprod()
    peak = eq.cummax(); dd = (eq - peak) / peak; mi = dd.idxmin(); pi = eq[:mi+1].idxmax()
    seg = T2.iloc[pi:mi+1]
    _p(f"  MDD {dd[mi]*100:.1f}% | 구간 거래#{pi}~{mi}({len(seg)}건) | 손실 {int((seg.ret<0).sum())}/이익 {int((seg.ret>0).sum())}")
    _p(f"  구간 청산종류: {dict(seg.exit_tag.value_counts())}")
    _p(f"  구간 진입VR중앙 {seg.vr.median():.2f}(전체 {T.vr.median():.2f}) | near_miss_sl {int(seg.near_miss_sl.sum())}건")

    # ── 4) Run analysis (연속손실) ──
    _p("\n【4】 연속손실 분석 (run analysis)")
    runs = []; c = 0
    for r in T.ret.values:
        if r < 0: c += 1
        else:
            if c: runs.append(c)
            c = 0
    if c: runs.append(c)
    runs = np.array(runs)
    _p(f"  연속손실 구간 {len(runs)}개 | 최장 {runs.max()}연패 | 평균 {runs.mean():.1f} | 3연패+ {int((runs>=3).sum())}회 | 5연패+ {int((runs>=5).sum())}회")

    # ── 5) Regime-segmented PF (VR 분위별) ──
    _p("\n【5】 장세별(VR 3분위) 손익비 — '가장 잘 맞는 장세' 탐색")
    q1, q2 = T.vr.quantile(1/3), T.vr.quantile(2/3)
    for lbl, m in [("VR하(회귀)", T.vr <= q1), ("VR중", (T.vr > q1) & (T.vr < q2)), ("VR상(추세)", T.vr >= q2)]:
        s = T[m]; _p(f"  {lbl:<10} n={len(s):3d} | PF {pf(s.ret.values):.2f} | 평균ret {s.ret.mean()*100:+.2f}% "
                     f"| 승률 {100*(s.ret>0).mean():.0f}% | 손익합 {s.ret.sum()*100:+.1f}%p")

    # ── 6) Edge Ratio ──
    er = T.edge_ratio.replace([np.inf, -np.inf], np.nan).dropna()
    _p(f"\n【6】 Edge Ratio(MFE/MAE) 중앙 {er.median():.2f} | >1 비율 {100*(er>1).mean():.0f}% "
       f"(>1=셋업이 청산前 구조적우위 있음, Sweeney)")

    # 저장
    T.to_csv(os.path.join(HERE, "trade_diagnostics_ledger.csv"), index=False, encoding="utf-8-sig")

    # ── 그래프 ──
    fig, ax = plt.subplots(2, 2, figsize=(13, 10))
    # (a) MAE-MFE 산점도
    a = ax[0, 0]
    a.scatter(loss.mae*100, loss.mfe*100, s=10, c="crimson", alpha=.4, label="loss")
    a.scatter(win.mae*100, win.mfe*100, s=10, c="seagreen", alpha=.4, label="win")
    a.plot([0, 8], [0, 8], "k--", lw=.7); a.axvline(SL_PCT*100, c="gray", ls=":", lw=.8)
    a.set_xlabel("MAE % (max adverse)"); a.set_ylabel("MFE % (max favorable)")
    a.set_title("MAE vs MFE scatter (Sweeney)"); a.legend(); a.set_xlim(0, 8); a.set_ylim(0, 12)
    # (b) 택소노미 막대
    a = ax[0, 1]
    names = ["entry-stop\nMFE<1%", "give-back\n1-3%", "big-giveback\n>=3%", "winners"]
    vals = [len(loss[loss.mfe < 0.01]), len(loss[(loss.mfe >= 0.01) & (loss.mfe < 0.03)]),
            len(loss[loss.mfe >= 0.03]), len(win)]
    a.bar(names, vals, color=["crimson", "orange", "gold", "seagreen"])
    a.set_title("Trade taxonomy (count)"); a.set_ylabel("trades")
    # (c) Equity + DD
    a = ax[1, 0]
    a.plot(eq.values, c="navy", lw=1); a.axvspan(pi, mi, color="red", alpha=.15)
    a.set_title(f"Equity (MDD {dd[mi]*100:.1f}% @ red span)"); a.set_xlabel("trade #"); a.set_ylabel("equity x")
    # (d) MFE capture 분포(이익거래)
    a = ax[1, 1]
    a.hist((win.mfe_capture*100).clip(-20, 120), bins=30, color="seagreen", alpha=.7)
    a.axvline(win.mfe_capture.median()*100, c="k", ls="--", lw=1)
    a.set_title(f"Winner MFE capture % (median {win.mfe_capture.median()*100:.0f}%)")
    a.set_xlabel("captured % of MFE")
    plt.tight_layout(); plt.savefig(os.path.join(HERE, "trade_diagnostics.png"), dpi=110)
    _p("\n[저장] trade_diagnostics_ledger.csv + trade_diagnostics.png")
    _p("[판정] 진입즉시SL 비중 큼 = 진입문제 / 큰수익후반납·낮은capture 큼 = 청산문제. exit_tag로 교차확인.")
    _p("[정직] 1m 실체결·갭반영(낙관금지)·레버1·비용8bp·미최적화 1파라미터셋.")


if __name__ == "__main__":
    main()
