# -*- coding: utf-8 -*-
# [realistic_sl_sim_regime.py] #다음1수 — VR<1(회귀)레짐 게이트 + 레짐인지 청산을 #1 실체결시뮬에 적용.
#   목적: #1 결과(+90.4%/MDD-39.0%)의 MDD가 §0 -20% 위반 → 원인=신호 아닌 *청산*(2025 IC정상인데 트레일 휩쏘).
#         레짐(VR<1=회귀 / VR>=1=추세)으로 진입게이트 + 청산을 조절해 -39% MDD를 -20% 안으로 들이는지 확인.
#   기존 realistic_sl_sim.py 무수정 보존(§1). 체결은 동일하게 1m 실가·갭 반영(낙관 트레일레벨 체결 금지).
#   VR = 분산비(8h, q=4·W=45 과거롤링, 룩어헤드0): >1 추세 / <1 회귀. regime_persistence_analysis.py와 동일 수식.
#   변형: V0 베이스 / V1 진입게이트(VR<1만) / V2 레짐인지청산(추세전환시 트레일 타이트) / V3 V1+V2.
import os, sys, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008          # 왕복 8bp
SL_PCT = 0.02          # 초기 손절 2%
TRAIL_LOOSE = 0.03     # 회귀레짐 트레일 3%(고점 대비)
TRAIL_TIGHT = 0.015    # 추세레짐(레짐인지) 트레일 1.5% = 깨지면 빨리 보호
ENTRY_Q = 0.33         # 진입 분위(상/하위 1/3)
MAX_HOLD_BARS = 60     # 최대보유 60×8h=20일
VR_W = 45              # 분산비 롤링창 45×8h=15일
VR_Q = 4               # 분산비 q


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def build_signal():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["open", "high", "low"]).sort_values("t").reset_index(drop=True)
    # 8h 그리드 신호 (open·oi_z) — t에 알려진 값
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first().dropna()
    oi8 = g["oi_zscore_24h"].last().shift(1)            # 직전 슬롯 끝값(룩어헤드 차단)
    S = pd.DataFrame({"open8": o8}).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    # ── VR(분산비) 레짐: 과거 롤링, 진입가 open8(t)까지만 사용 = 룩어헤드0 ──
    ret8 = S["open8"].pct_change(1)
    rq = S["open8"].pct_change(VR_Q)
    S["vr"] = rq.rolling(VR_W).var() / (VR_Q * ret8.rolling(VR_W).var() + 1e-12)
    S = S.dropna(subset=["mom_24h", "oi_z"])
    # combo = IC가중·방향정렬 (mom·oi 둘다 음IC=reversion → -부호로 '고=고수익' 정렬)
    ic_m, ic_o = 0.048, 0.037
    S["combo"] = (-zr(S["mom_24h"])) * ic_m + (-zr(S["oi_z"])) * ic_o
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    return d, S


def simulate(d, S, *, gate=False, regime_exit=False):
    """1m 단일패스. gate=진입 VR<1만 / regime_exit=추세레짐(VR>=1)서 트레일 타이트."""
    entry_side = S["side"].to_dict()
    vr_of = S["vr"].to_dict()
    bar8_set = set(S.index)
    tindex = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    trades = []; pos = 0; entry = 0.0; et = None; hwm = lwm = 0.0; TS = 0.0
    bars_held = 0; cur_vr = np.nan
    for i in range(len(d)):
        t = tindex.iloc[i]
        if t in bar8_set:
            v = vr_of.get(t, np.nan)
            if not (isinstance(v, float) and np.isnan(v)): cur_vr = v   # 8h마다 현재레짐 갱신
        if pos == 0:
            side = entry_side.get(t, 0)
            if t in bar8_set and side != 0:
                if gate and not (cur_vr < 1.0):   # 회귀(VR<1)일 때만 진입; NaN/추세는 회피
                    continue
                pos = int(side); entry = O[i]; et = t
                hwm = H[i]; lwm = L[i]; bars_held = 0
                TS = entry * (1 - SL_PCT) if pos == 1 else entry * (1 + SL_PCT)
        else:
            trail = TRAIL_TIGHT if (regime_exit and cur_vr >= 1.0) else TRAIL_LOOSE
            exit_px = None; reason = None
            if pos == 1 and L[i] <= TS:
                exit_px = min(O[i], TS); reason = "trail/sl"      # 갭이면 open(더나쁨)
            elif pos == -1 and H[i] >= TS:
                exit_px = max(O[i], TS); reason = "trail/sl"
            if exit_px is None and t in bar8_set:
                bars_held += 1
                if bars_held >= MAX_HOLD_BARS:
                    exit_px = O[i]; reason = "maxhold"
            if exit_px is not None:
                ret = pos * (exit_px - entry) / entry - COST
                # MFE = 보유중 최대 유리이동(롱=고점, 숏=저점) / 반납 = MFE - 실현(비용전)
                mfe = (hwm - entry) / entry if pos == 1 else (entry - lwm) / entry
                realized = pos * (exit_px - entry) / entry
                trades.append(dict(et=et, xt=t, side=pos, entry=entry, exit=exit_px, ret=ret,
                                   reason=reason, year=pd.Timestamp(et).year, vr=cur_vr,
                                   mfe=mfe, giveback=mfe - realized))
                pos = 0
            else:
                if pos == 1:
                    hwm = max(hwm, H[i]); TS = max(TS, hwm * (1 - trail))
                else:
                    lwm = min(lwm, L[i]); TS = min(TS, lwm * (1 + trail))
    return pd.DataFrame(trades)


def metrics(T):
    eq = (1 + T["ret"]).cumprod()
    tot = (eq.iloc[-1] - 1) * 100
    peak = eq.cummax(); mdd = ((eq - peak) / peak).min() * 100
    sr = T["ret"].mean() / T["ret"].std() * np.sqrt(len(T) / 3) if T["ret"].std() > 0 else 0
    g6 = np.array_split(np.arange(len(T)), 6); paths = []
    for c in itertools.combinations(range(6), 2):
        idx = np.concatenate([g6[k] for k in c]); r = T["ret"].values[idx]
        paths.append(r.mean() / r.std() * np.sqrt(len(r) / 3) if r.std() > 0 else 0)
    paths = np.array(paths)
    return dict(n=len(T), win=100*(T.ret > 0).mean(), tot=tot, mdd=mdd, sr=sr,
                p25=np.percentile(paths, 25), worst=paths.min(), negpct=100*(paths < 0).mean())


def main():
    d, S = build_signal()
    _p(f"[신호] 8h봉 {len(S)} | 진입후보 롱 {int((S.side==1).sum())} 숏 {int((S.side==-1).sum())} "
       f"| VR 중앙 {S.vr.median():.2f} | 회귀(VR<1) 비중 {100*(S.vr<1).mean():.0f}%")
    VARIANTS = [("V0 베이스(무게이트)", dict(gate=False, regime_exit=False)),
                ("V1 진입게이트 VR<1", dict(gate=True, regime_exit=False)),
                ("V2 레짐인지청산", dict(gate=False, regime_exit=True)),
                ("V3 V1+V2", dict(gate=True, regime_exit=True))]
    _p(f"\n{'변형':<22}{'거래':>5}{'승률':>6}{'복리%':>9}{'MDD%':>8}{'Sharpe':>8}{'CPCVp25':>9}{'최악':>7}{'음수%':>6}{'-20내':>6}")
    _p("-" * 92)
    rows = []
    for nm, kw in VARIANTS:
        T = simulate(d, S, **kw)
        if len(T) < 10:
            _p(f"{nm:<22} 거래 {len(T)}건 — 표본부족"); continue
        m = metrics(T)
        ok = "O" if (m["tot"] > 0 and m["p25"] > 0 and m["mdd"] > -20) else "X"
        _p(f"{nm:<22}{m['n']:>5}{m['win']:>5.0f}%{m['tot']:>+9.1f}{m['mdd']:>+8.1f}"
           f"{m['sr']:>8.2f}{m['p25']:>+9.2f}{m['worst']:>+7.2f}{m['negpct']:>5.0f}%{ok:>6}")
        T.to_csv(os.path.join(HERE, f"regime_sim_{nm.split()[0]}.csv"), index=False, encoding="utf-8-sig")
        rows.append((nm, m))
    # 연도별 분해 (게이트 효과가 2025 휩쏘 잡는지)
    _p("\n[연도별 합손익 %] (2025=추세레짐 휩쏘 의심구간)")
    _p(f"{'변형':<22}" + "".join(f"{y:>9}" for y in [2023, 2024, 2025, 2026]))
    for nm, kw in VARIANTS:
        T = simulate(d, S, **kw)
        if len(T) < 10: continue
        cells = []
        for y in [2023, 2024, 2025, 2026]:
            s = T[T.year == y]
            cells.append(f"{((1+s.ret).prod()-1)*100:>+9.1f}" if len(s) else f"{'-':>9}")
        _p(f"{nm:<22}" + "".join(cells))
    _p("\n[판정] 합격 = 복리>0 AND CPCV p25>0 AND MDD>-20%. 베이스 V0 대비 MDD 개선폭이 레짐로직 가치.")
    _p("[정직] 미최적화 파라미터(SL2%·트레일3%/1.5%·VR_W45·q4). 레버1·비용8bp. 체결=1m 실가·갭(낙관금지).")


if __name__ == "__main__":
    main()
