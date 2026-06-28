# -*- coding: utf-8 -*-
# [realistic_sl_sim.py] #1 — 최강 결합(mom+oi IC가중)을 SL+트레일 스텝업 손절로 시뮬.
#   ★핵심: 청산 체결을 '1m 실가·갭반영'으로(낙관 트레일레벨 체결 금지). 챔피언 +11397% 인플레의 교정판.
#   진입: 8h 그리드 combo 분위(상위=롱/하위=숏, 보유중엔 진입X). 진입가=그 8h봉 open(t에 알려진 신호).
#   청산: 초기 SL(-sl_pct) + 트레일 스텝업(고점 - trail_pct, 래칫). 1m 모니터, 무 lookahead(트레일은 직전봉까지 고점).
#   실체결: 롱 stop터치(low<=TS) → fill=min(open,TS)(갭이면 open=더나쁨). 숏 대칭. 비용 왕복8bp. 레버1(원천 엣지).
#   ※투명 최소 시뮬(§15-1: 챔피언 재현 주장 아님, 새 신호+정직체결 테스트). 파라미터 미최적화(견고성 별도 점검).
import os, sys
import numpy as np, pandas as pd
from scipy import stats

STG = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
for p in (os.path.join(STG, "bots"), STG):
    if p not in sys.path: sys.path.insert(0, p)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008          # 왕복 8bp
SL_PCT = 0.02          # 초기 손절 2%
TRAIL_PCT = 0.03       # 트레일 3%(고점 대비)
ENTRY_Q = 0.33         # 진입 분위(상/하위 1/3)
MAX_HOLD_BARS = 60     # 최대보유 60×8h=20일


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def main():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["open", "high", "low"]).sort_values("t").reset_index(drop=True)
    # 8h 그리드 신호 (open·oi_z) — t에 알려진 값
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first().dropna()
    oi8 = g["oi_zscore_24h"].last().shift(1)            # 직전 슬롯 끝값(룩어헤드 차단)
    S = pd.DataFrame({"open8": o8}).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    S = S.dropna(subset=["mom_24h", "oi_z"])
    # combo = IC가중·방향정렬 (mom·oi 둘다 음IC=reversion → -부호로 '고=고수익' 정렬)
    ic_m, ic_o = 0.048, 0.037
    S["combo"] = (-zr(S["mom_24h"])) * ic_m + (-zr(S["oi_z"])) * ic_o
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    entry_side = S["side"].to_dict()                   # 8h봉시각 → 진입방향
    bar8_set = set(S.index)
    _p(f"[신호] 8h봉 {len(S)} | 진입후보 롱 {int((S.side==1).sum())} 숏 {int((S.side==-1).sum())}")

    ts = d["t"].values; O = d["open"].values; H = d["high"].values; L = d["low"].values
    tindex = d["t"]
    # 단일패스 1m 시뮬
    trades = []; pos = 0; entry = 0.0; et = None; hwm = lwm = 0.0; TS = 0.0; bars_held = 0; entry_bar8 = None
    bar8_of = tindex.dt.floor("480min")  # 근사(원점 다름이나 진입판정은 set 매칭으로)
    for i in range(len(d)):
        t = tindex.iloc[i]
        if pos == 0:
            if t in bar8_set and entry_side.get(t, 0) != 0:
                pos = int(entry_side[t]); entry = O[i]; et = t; entry_bar8 = t
                hwm = H[i]; lwm = L[i]; bars_held = 0
                TS = entry * (1 - SL_PCT) if pos == 1 else entry * (1 + SL_PCT)
        else:
            # ── 청산 검사 먼저 (TS는 직전봉까지 갱신분) ──
            exit_px = None; reason = None
            if pos == 1 and L[i] <= TS:
                exit_px = min(O[i], TS); reason = "trail/sl"      # 갭이면 open(더나쁨)
            elif pos == -1 and H[i] >= TS:
                exit_px = max(O[i], TS); reason = "trail/sl"
            # 최대보유
            if exit_px is None and t in bar8_set:
                bars_held += 1
                if bars_held >= MAX_HOLD_BARS:
                    exit_px = O[i]; reason = "maxhold"
            if exit_px is not None:
                ret = pos * (exit_px - entry) / entry - COST
                trades.append(dict(et=et, xt=t, side=pos, entry=entry, exit=exit_px, ret=ret,
                                   reason=reason, year=pd.Timestamp(et).year))
                pos = 0
            else:
                # ── 트레일 래칫 (이 봉 고/저로 다음봉용 갱신) ──
                if pos == 1:
                    hwm = max(hwm, H[i]); TS = max(TS, hwm * (1 - TRAIL_PCT))
                else:
                    lwm = min(lwm, L[i]); TS = min(TS, lwm * (1 + TRAIL_PCT))
    T = pd.DataFrame(trades)
    _p(f"[거래] {len(T)}건 | 승률 {100*(T.ret>0).mean():.0f}% | 평균 {T.ret.mean()*100:+.2f}% | reason {dict(T.reason.value_counts())}")
    # 복리(레버1) + 지표
    eq = (1 + T["ret"]).cumprod()
    tot = (eq.iloc[-1] - 1) * 100
    peak = eq.cummax(); mdd = ((eq - peak) / peak).min() * 100
    sr = T["ret"].mean() / T["ret"].std() * np.sqrt(len(T) / 3) if T["ret"].std() > 0 else 0  # 연율 근사(거래/3년)
    _p(f"[성과 레버1·비용8bp·실체결] 복리 {tot:+.1f}% / MDD {mdd:.1f}% / 거래Sharpe근사 {sr:.2f}")
    # 연도별
    for y in sorted(T.year.unique()):
        s = T[T.year == y]; _p(f"  {int(y)}: {len(s)}거래 평균 {s.ret.mean()*100:+.2f}% 합 {((1+s.ret).prod()-1)*100:+.1f}%")
    # CPCV(거래 단위 6그룹 2조합 15경로)
    import itertools
    g6 = np.array_split(np.arange(len(T)), 6); paths = []
    for c in itertools.combinations(range(6), 2):
        idx = np.concatenate([g6[k] for k in c]); r = T["ret"].values[idx]
        paths.append(r.mean() / r.std() * np.sqrt(len(r) / 3) if r.std() > 0 else 0)
    paths = np.array(paths)
    _p(f"[CPCV 15경로] p25 {np.percentile(paths,25):+.2f} / 최악 {paths.min():+.2f} / 음수경로 {100*(paths<0).mean():.0f}%")
    T.to_csv(os.path.join(HERE, "realistic_sl_sim_trades.csv"), index=False, encoding="utf-8-sig")
    _p("[판정] 복리>0 AND CPCV p25>0 AND MDD수용 → '실행하 알파' 후보. 아니면 신호는 가능성이나 이 청산로직선 미배포.")
    _p("[정직] 미최적화 1파라미터셋. 레버1. 진입=8h open(슬립0가정). 트레일 청산은 1m 실가·갭반영(낙관 금지).")


if __name__ == "__main__":
    main()
