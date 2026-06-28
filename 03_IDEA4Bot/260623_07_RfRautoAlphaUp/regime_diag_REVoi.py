# -*- coding: utf-8 -*-
# [regime_diag_REVoi.py] REVoi 932거래를 '진입시점 과거전용 레짐'으로 버킷팅 → 어디서 잃는지 진단 (캡틴 지시 2026-06-25 "진단부터").
#   ★룩어헤드0: 진단·라이브 컷용 피처는 과거전용(atr60·oiz·absoi1h·|fund|·ls·cvd)만. fwd_*(미래)는 '결과 라벨'로만 참고표시.
#   산출: 레짐 분위(5분위)별 거래수·승률·R합·평균R + 최악 MDD창의 레짐 구성 + 월별 손실클러스터 대조.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
LED = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260624_13_REVoi_MDD25_36mo_v6\260624_13_REVoi_MDD25_36mo_v6_거래원장.csv"
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
EXPO = 2.25  # 레버3×증거금75% (MDD-25 세팅과 동일 노출)


def _p(*a): print(*a, flush=True)


def main():
    L = pd.read_csv(LED, parse_dates=["et", "xt"]).sort_values("et").reset_index(drop=True)
    R = pd.read_parquet(REG)
    R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
    R = R.set_index("timestamp").sort_index()
    # 진입시점(et) 직전 확정 레짐값(과거전용) — asof로 et 이하 최신 분(룩어헤드0)
    et = L["et"].values
    feat_bw = ["atr60", "absoi1h", "oiz_s", "cvd_s", "fund_s", "ls_s"]   # 과거전용
    feat_fw = ["fwd_vol60", "fwd_jump60", "fwd_ret60"]                    # 미래참조(라벨, 참고만)
    Ridx = R.index.values
    pos = np.searchsorted(Ridx, et, side="right") - 1   # et 이하 최신 분
    pos = np.clip(pos, 0, len(R) - 1)
    for c in feat_bw + feat_fw:
        L[c] = R[c].values[pos]
    L["oiz_abs"] = L["oiz_s"].abs(); L["fund_abs"] = L["fund_s"].abs()
    L["ls_abs"] = L["ls_s"].abs(); L["cvd_abs"] = L["cvd_s"].abs()
    L["m"] = L["et"].dt.to_period("M").astype(str)

    _p("=" * 78)
    _p(f"[REVoi 932거래 레짐 진단] 노출{EXPO}(레버3×증거금75) · 진입시점 과거전용 레짐 · 룩어헤드0")
    _p(f"  전체: 거래{len(L)} 승률{100*(L.R>0).mean():.1f}% R합{L.R.sum()*100:+.0f}% 평균R{L.R.mean()*100:+.3f}%")

    def bucket_report(col, label, q=5):
        _p(f"\n[{label}] ({col}) — 5분위 (Q1=낮음 … Q5=높음)")
        try:
            L["_b"] = pd.qcut(L[col], q, labels=[f"Q{i+1}" for i in range(q)], duplicates="drop")
        except Exception:
            _p("  (분위 실패)"); return
        rows = []
        for b, g in L.groupby("_b", observed=True):
            rows.append((str(b), len(g), 100*(g.R>0).mean(), g.R.sum()*100, g.R.mean()*100,
                         g[col].min(), g[col].max(), g.fwd_vol60.mean()*100))
        df = pd.DataFrame(rows, columns=["분위","거래수","승률%","R합%","평균R%","경계_low","경계_hi","실현변동%(라벨)"])
        _p(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    bucket_report("atr60", "변동성(60분 ATR)")
    bucket_report("oiz_abs", "OI 충격 절대크기(|oi_z|)")
    bucket_report("absoi1h", "OI 1h 변화량")
    bucket_report("fund_abs", "펀딩 극단도(|fund|)")
    bucket_report("ls_abs", "롱숏 쏠림 절대도(|ls|)")
    bucket_report("cvd_abs", "CVD 절대크기(|cvd|)")

    # ── 최악 MDD 창의 레짐 구성 ──
    _p("\n" + "=" * 78); _p("[최악 MDD 창의 레짐 구성]")
    bal = 10000.0; eq = []
    for r in L.itertuples():
        bal *= (1.0 + r.R * EXPO); eq.append(bal)
    eq = np.array(eq); peak = np.maximum.accumulate(eq); dd = eq/peak - 1.0
    trough = int(dd.argmin()); top = int(np.argmax(eq[:trough+1]))
    win = L.iloc[top:trough+1]
    _p(f"  MDD {dd.min()*100:.1f}% | 창=거래#{top}~{trough} ({L.et.iloc[top].date()}~{L.et.iloc[trough].date()}) {len(win)}거래")
    _p(f"  창內 승률{100*(win.R>0).mean():.0f}% R합{win.R.sum()*100:+.0f}%")
    for c, lab in [("atr60","변동성"),("oiz_abs","OI충격"),("fund_abs","펀딩극단"),("ls_abs","롱숏쏠림")]:
        med_all = L[c].median(); med_win = win[c].median()
        _p(f"   - {lab}({c}) 창中앙값 {med_win:.4f} vs 전체中앙값 {med_all:.4f}  ({'↑높음' if med_win>med_all else '↓낮음'})")

    # ── 월별 손실클러스터 ↔ 레짐 대조 ──
    _p("\n" + "=" * 78); _p("[월별 R합 ↔ 진입레짐 중앙값] (손실月이 특정레짐인지)")
    mg = L.groupby("m").agg(거래수=("R","size"), 승률=("R", lambda x:100*(x>0).mean()),
                            R합=("R", lambda x:x.sum()*100), atr60中=("atr60","median"),
                            OI충격中=("oiz_abs","median"), 펀딩中=("fund_abs","median")).reset_index()
    mg["손실月"] = np.where(mg["R합"]<0, "★손실", "")
    _p(mg.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    los = mg[mg["R합"]<0]; win_m = mg[mg["R합"]>=0]
    _p(f"\n  손실月({len(los)}) atr60中앙값 {los.atr60中.median():.4f} · OI충격 {los.OI충격中.median():.3f} · 펀딩 {los.펀딩中.median():.4f}")
    _p(f"  수익月({len(win_m)}) atr60中앙값 {win_m.atr60中.median():.4f} · OI충격 {win_m.OI충격中.median():.3f} · 펀딩 {win_m.펀딩中.median():.4f}")

    out = os.path.join(HERE, "regime_diag_REVoi_table.csv")
    L[["et","m","side","R","reason"]+feat_bw+["oiz_abs","fund_abs","ls_abs","cvd_abs"]+feat_fw].to_csv(out, index=False, encoding="utf-8-sig")
    mg.to_csv(os.path.join(HERE, "regime_diag_REVoi_monthly.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] regime_diag_REVoi_table.csv (거래별 레짐) · regime_diag_REVoi_monthly.csv (월별)")


if __name__ == "__main__":
    main()
