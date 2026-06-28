# -*- coding: utf-8 -*-
# [exec_realism_REVoi.py] 지정가/시장가 실행 현실성 검증 (캡틴 지시 2026-06-25).
#   질문: ① 진입 지정가(피보 되돌림)가 1m서 실제 체결되나? 미체결(폴백)률은? ② 변동성(atr60)이 높으면 지정가 체결률↓인가?
#         ③ 청산 fibstop(=스톱=시장가)의 실슬리피지(스톱레벨 대비 1m갭)는 얼마이고 변동성에 비례하나?
#   결론: 현 모델(진입 maker2bp 고정 + 청산 taker4bp + 1m갭) 대비 '변동성조건부 지정/시장 + 슬립'이 현실적인지 판정.
import os, sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd, json
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
HERE = os.path.dirname(os.path.abspath(__file__))
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
LED = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260624_13_REVoi_MDD25_36mo_v6\260624_13_REVoi_MDD25_36mo_v6_거래원장.csv"


def _p(*a): print(*a, flush=True)


def main():
    p = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = BR.rev_trades(d1m, fund, p, capture_fills=True).sort_values("et").reset_index(drop=True)
    R = pd.read_parquet(REG); R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
    R = R.set_index("timestamp").sort_index()
    et = T["et"].values; pos = np.clip(np.searchsorted(R.index.values, et, "right")-1, 0, len(R)-1)
    T["atr60"] = R["atr60"].values[pos]

    # ── ① 진입 지정가 체결 vs 폴백 ──
    _p("="*78); _p("[① 진입 지정가(피보 되돌림) 체결 현실성]")
    leg1_base = leg_retr_fill = leg_retr_miss = 0
    for r in T.itertuples():
        fills = r.fills if isinstance(r.fills, list) else []
        if not fills: continue
        base = fills[0][1]; leg1_base += 1
        for ft, fp in fills[1:]:
            if abs(fp - base) < 1e-9: leg_retr_miss += 1   # 되돌림 미도달 → base 폴백(= 즉시 진입과 동일가)
            else: leg_retr_fill += 1                        # 되돌림 실제 체결(지정가=메이커 성립)
    tot_retr = leg_retr_fill + leg_retr_miss
    _p(f"  포지션당 3분할: 1차={leg1_base}건(신호봉 종가 '즉시' 진입) · 되돌림레그={tot_retr}건")
    _p(f"  되돌림 지정가 실제체결 {leg_retr_fill} ({100*leg_retr_fill/max(1,tot_retr):.1f}%) · 미도달폴백 {leg_retr_miss} ({100*leg_retr_miss/max(1,tot_retr):.1f}%)")
    _p(f"  → 1차레그(전체 체결의 1/3)는 '되돌림 대기 없이 즉시' = 사실상 시장성 진입. 현모델은 이걸 maker2bp로 계산.")
    _p(f"  → 되돌림레그 중 {100*leg_retr_miss/max(1,tot_retr):.0f}%는 미도달=base폴백(즉시가) → 실제 '지정가 메이커'로 잡힌 비율 = 전체의 약 {100*leg_retr_fill/(3*len(T)):.0f}%")

    # 변동성별 되돌림 체결률
    T["_q"] = pd.qcut(T["atr60"], 5, labels=["Q1","Q2","Q3","Q4","Q5"])
    _p("\n  [변동성(atr60) 분위별 되돌림레그 체결률]")
    for b, g in T.groupby("_q", observed=True):
        f = m = 0
        for r in g.itertuples():
            base = r.fills[0][1]
            for ft, fp in r.fills[1:]:
                if abs(fp-base) < 1e-9: m += 1
                else: f += 1
        _p(f"   {b}: 체결 {100*f/max(1,f+m):.0f}%  (atr60 {g.atr60.min():.4f}~{g.atr60.max():.4f})")

    # ── ③ 청산 fibstop 슬리피지(스톱레벨 대비 1m 실체결 갭) ──
    _p("\n" + "="*78); _p("[③ 청산 fibstop(스톱=시장가) 실슬리피지: 스톱레벨 대비 1m 체결갭]")
    L = pd.read_csv(LED)
    # 불리갭% = 롱:(x_int-exit)/entry, 숏:(exit-x_int)/entry  (>0=스톱보다 나쁘게 체결=갭슬립)
    L["slip_bp"] = np.where(L.side==1, (L.x_int-L.exit)/L.entry, (L.exit-L.x_int)/L.entry)*1e4
    L["et"]=pd.to_datetime(L.et); pos2=np.clip(np.searchsorted(R.index.values, L.et.values, "right")-1,0,len(R)-1)
    L["atr60"]=R["atr60"].values[pos2]
    _p(f"  전체 슬리피지 중앙값 {L.slip_bp.median():.1f}bp · 평균 {L.slip_bp.mean():.1f}bp · 90%분위 {L.slip_bp.quantile(.9):.1f}bp · 최악 {L.slip_bp.max():.1f}bp")
    _p(f"  갭발생(>1bp) 비율 {100*(L.slip_bp>1).mean():.0f}% · 무갭(스톱레벨 그대로) {100*(L.slip_bp.abs()<=1).mean():.0f}%")
    _p("\n  [변동성(atr60) 분위별 청산 슬리피지 중앙/평균 bp]")
    L["_q"]=pd.qcut(L.atr60,5,labels=["Q1","Q2","Q3","Q4","Q5"])
    for b,g in L.groupby("_q",observed=True):
        _p(f"   {b}: 중앙 {g.slip_bp.median():.1f}bp · 평균 {g.slip_bp.mean():.1f}bp · 90%분위 {g.slip_bp.quantile(.9):.1f}bp")
    cur = (BR.COST)*1e4  # 현 모델 청산비용(taker+...) 참고
    _p(f"\n  현 모델 가정: 진입 maker {0.0002*1e4:.0f}bp · 청산 taker {0.0004*1e4:.0f}bp · 스프 {0.0001*1e4:.0f}bp + 청산갭(위 슬립, 이미 R반영)")
    L.to_csv(os.path.join(HERE,"exec_realism_slip.csv"),index=False,encoding="utf-8-sig")
    _p("[저장] exec_realism_slip.csv")
    return L


if __name__ == "__main__":
    main()
