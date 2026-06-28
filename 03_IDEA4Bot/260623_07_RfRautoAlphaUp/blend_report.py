# -*- coding: utf-8 -*-
# [blend_report.py] best_blend.json → 블렌드 결과 산출(원장·월별표·Pine) + held-out 요약 + 저장.
#   ★최적화(blend_opt.py)와 100% 동일 모델: 월수익률 블렌드 e*[(1-w)*TS + w*REV]. 같은 config=같은 결과(캡틴 신뢰규칙).
#   ★REV 신호 = 롤링정직(룩어헤드0) · ★1m 체결검증 · 스톱캡 · 실펀딩 · 현실수수료(gen_trades 내장).
#   산출: 통합원장(TS+REV 태그) CSV · 월별표(스트림별 수익률+블렌드 누적equity) · 통합 Pine(양쪽거래 TV표시) · 분석txt · INDEX.
#   사용: python blend_report.py "블렌드명칭"
import os, sys, json, itertools
from datetime import datetime
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import bt_full as B
import make_pine as MP
from blend_opt import rev_side, monthly, mstat, cpcv_p25
HERE = os.path.dirname(os.path.abspath(__file__))
WH = r"D:\ML\RfRauto\00_WorkHstr"; BTO = os.path.join(WH, "BackTest_Output"); INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
TRAIN = pd.Period("2024-12", "M"); CAP = 10000.0


def _p(*a): print(*a, flush=True)


def main():
    name = "".join(ch for ch in (sys.argv[1] if len(sys.argv) > 1 else "TSREV_Blend") if ch.isalnum() or ch in "_-")[:40]
    p = json.load(open(os.path.join(HERE, "best_blend.json")))
    d1m = load_1m(); fund = load_funding()
    _p("[블렌드 재생성] TS(추세)+REV(회귀 롤링정직) · 1m체결 · 동일모델")
    fib = (p["f1"], p["f2"], p["f3"])
    TSt = B.gen_trades(d1m, fund, p["ts_tf"], p["piv"], p["N"], fib, p["iam"], er_gate=p["erg"], capture_fills=True)
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    REVt = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], fib, p["iam"], er_gate=0.0,
                        ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"], capture_fills=True)
    w, e = p["w"], p["expo"]
    tsm = monthly(TSt); revm = monthly(REVt); allm = sorted(set(tsm.index) | set(revm.index))
    ts_s = tsm.reindex(allm, fill_value=0.0); rev_s = revm.reindex(allm, fill_value=0.0)
    blend = e * ((1 - w) * ts_s + w * rev_s)               # ★최적화와 동일
    months = pd.PeriodIndex(allm, freq="M"); tr = months <= TRAIN; te = ~tr
    eq = CAP * np.cumprod(1 + blend.values)

    # ── 1) 통합 원장(TS+REV 태그) ──
    def tag(T, s):
        L = T.drop(columns=["fills"]).copy(); L.insert(0, "스트림", s); return L
    led = pd.concat([tag(TSt, "TS"), tag(REVt, "REV")]).sort_values("et")
    today = datetime.now().strftime("%y%m%d"); tsd = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BTO, exist_ok=True); nn = len([d for d in os.listdir(BTO) if d.startswith(today + "_")]) + 1
    base = f"{today}_{nn:02d}_{name}"; folder = os.path.join(BTO, base); os.makedirs(folder, exist_ok=True)
    led.to_csv(os.path.join(folder, f"{base}_통합원장.csv"), index=False, encoding="utf-8-sig")

    # ── 2) 월별표: 스트림별 거래수·수익률 + 블렌드 수익률·누적equity ──
    tsn = tsm.reindex(allm).notna().astype(int) * 0  # placeholder
    tcnt = pd.to_datetime(pd.Series([t for t in TSt.et])).dt.to_period("M").value_counts() if len(TSt) else pd.Series(dtype=int)
    rcnt = pd.to_datetime(pd.Series([t for t in REVt.et])).dt.to_period("M").value_counts() if len(REVt) else pd.Series(dtype=int)
    rows = []
    for i, m in enumerate(allm):
        rows.append({"년월": str(m), "TS_거래수": int(tcnt.get(m, 0)), "TS_수익률(%)": round(ts_s.iloc[i] * 100, 2),
                     "REV_거래수": int(rcnt.get(m, 0)), "REV_수익률(%)": round(rev_s.iloc[i] * 100, 2),
                     "블렌드_수익률(%)": round(blend.iloc[i] * 100, 2), "블렌드_누적자본($)": round(eq[i]),
                     "구간": ("학습" if tr[i] else "검증OOS")})
    U = pd.DataFrame(rows); U.to_csv(os.path.join(folder, f"{base}_월별표.csv"), index=False, encoding="utf-8-sig")

    # ── 3) 통합 Pine(양쪽 거래 TV표시) ──
    both = pd.concat([TSt.assign(_s="TS"), REVt.assign(_s="REV")]).sort_values("et").reset_index(drop=True)
    MP.build_pine(both, e, out=os.path.join(folder, f"{base}.pine"), title=f"블렌드 {name}")

    # ── 요약 ──
    tt, tm = mstat(blend[tr].values); vt, vm = mstat(blend[te].values); ft, fm = mstat(blend.values)
    corr = np.corrcoef(ts_s.values, rev_s.values)[0, 1]
    head = (f"[블렌드명] {base}\n[config] TS_TF={p['ts_tf']} REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} "
            f"피보=({fib[0]:.2f},{fib[1]:.2f},{fib[2]:.2f}) ATR×{p['iam']:.2f} er{p['erg']:.2f} | "
            f"REV분위{p['q']:.2f}/롤링{p['qwin']} arm{p['arm']} | w_rev={w:.2f} 노출={e:.2f}\n"
            f"[조건] TS추세+REV회귀(롤링정직·룩어헤드0)·피보스텝업(공유)·1m체결·스톱캡·실펀딩·현실비용 | 월상관 {corr:+.2f}\n"
            f"[거래] TS {len(TSt)} · REV {len(REVt)} | 월수 {len(allm)}\n"
            f"[학습23~24]    복리 {tt:+.0f}% MDD {tm:.0f}%\n"
            f"[★검증OOS25~26] 복리 {vt:+.0f}% MDD {vm:.0f}%   ← 정직 held-out 진짜값\n"
            f"[전체]         복리 {ft:+.0f}% MDD {fm:.0f}% · 자본 ${eq[-1]:,.0f} · CPCV p25 {cpcv_p25(blend.values):+.1f}%\n"
            f"[판정] 검증OOS>0 = 룩어헤드 제거에도 살아남은 진짜 알파. 음수면 = 단일·블렌드 모두 미달(정직).")
    body = head + "\n\n[월별표]\n" + U.to_string(index=False)
    open(os.path.join(WH, f"{tsd}_{base}.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{base}|블렌드 TS{len(TSt)}·REV{len(REVt)}·검증OOS{vt:+.0f}%·CPCVp25{cpcv_p25(blend.values):+.0f}%|src=blend_report.py\n")
    _p("\n" + "=" * 60); _p(head); _p("=" * 60)
    _p(f"[저장] {folder}\\  ({base}_통합원장.csv · {base}_월별표.csv · {base}.pine · {base}_분석.txt)")
    _p(f"[TV] {base}.pine → BINANCE:BTCUSDT.P · UTC · 4h 붙여넣기 (TS+REV 거래 동시표시)")


if __name__ == "__main__":
    main()
