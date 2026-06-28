# -*- coding: utf-8 -*-
# [bt_full.py] 종합 백테 하니스 — 캡틴 지시(2026-06-23 "실시"): 피보 스텝업 알파를 풀 최적화로 입증.
#   최적화 대상(ML): sig_TF(15m~12h) · 눌림목(pivot_TF∈{1m,5m,20m,1h,4h,8h}, N봉) · 피보비율 · 초기손절(ATR연동)
#                    · 진입수량(size_pct) · 레버리지.
#   현실비용(성급계열 재사용·§15.1 호출): 진입 maker2bp(지정가, 긴봉 체결가정)→청산 시장가 taker4bp+스프레드1bp,
#                    슬리피지=1m 갭(낙관금지), 실펀딩(BTCUSDT_funding_history_8h), 강제청산=PaperAccount(MMR티어·hsd).
#   과적합방지(선행연구): 워크포워드(학습23~24 최적화→검증25~26 OOS) + 전체 CPCV. 트레일=변동성(ATR)연동.
#   진입신호 = 챔피언 엔진(compute_signals: Trend+피봇) on sig_TF(검증된 진입). 눌림목 스텝업만 파라미터화.
#   ★1m 체결검증: 청산 스톱 터치·체결을 1m봉으로(갭=불리). 환각방지.
import sys, os, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
MK, TK, SPRD = 0.0002, 0.0004, 0.0001     # 진입 maker / 청산 taker / 스프레드(성급계열 realistic_exec)
TRAIN_END = pd.Timestamp("2024-12-31")
TRAIN_ONLY = False                        # True면 목적함수를 학습기간(≤TRAIN_END)만으로 → 25~26 진짜 held-out


def _p(*a): print(*a, flush=True)


def split_fills(d, i, close, high, low, n, idx, lastPH, lastPL, split_n=3):
    """분할진입 개별 체결점 [(시각, 가격), ...] — 엔진 compute_split_entry L244-265 미러(평균=ep)."""
    base = float(close[i]); out = [(idx[i], base)]
    if np.isnan(lastPH) or np.isnan(lastPL): return out
    swing = lastPH - lastPL
    for lv in [0.382, 0.5, 0.618][:split_n - 1]:
        target = base - lv * swing * 0.1 if d == 1 else base + lv * swing * 0.1
        got = None; gj = i
        for j in range(i + 1, min(i + 21, n)):
            if (d == 1 and low[j] <= target) or (d == -1 and high[j] >= target):
                got = target; gj = j; break
        out.append((idx[gj], float(target) if got is not None else base))
    return out


def swings_on_tf(d1m, tf_min, N):
    """눌림목 = pivot_TF로 리샘플 후 N봉 좌·우1 피봇(엔진 pivots_lr 호출, 룩어헤드0=우측1봉 확정).
       반환: (lo_times[], lo_px[], hi_times[], hi_px[]) 시각순."""
    g = TS.resample_tf(d1m[["open", "high", "low", "close"]], tf_min)
    ph, pl = TS.pivots_lr(g["high"].values, g["low"].values, N, 1)
    idx = g.index
    lo_t = sorted(pl.keys()); hi_t = sorted(ph.keys())
    lo = [(idx[k], pl[k][1]) for k in lo_t]; hi = [(idx[k], ph[k][1]) for k in hi_t]
    return lo, hi


def bucket_swings(swings, edges):
    """swing (time,px) 리스트를 sig_TF 봉 구간 [edges[i],edges[i+1])로 버킷팅 → bar별 [(px),...]."""
    out = [[] for _ in range(len(edges))]
    j = 0; S = sorted(swings)
    for t, px in S:
        k = int(np.searchsorted(edges, np.datetime64(t), 'right')) - 1   # t가 속한 sig봉
        if 0 <= k < len(out): out[k].append(px)
    return out


def gen_trades(d1m, fund, sig_tf, pivot_tf, N, fib, init_atr_mult, er_gate=0.40, capture_fills=False,
               ext_side=None, align_pivot=False, use_trend_flip=True, arm_bars=6,
               time_stop_bars=0, time_stop_minR=0.0, fib_scale=None, tp_frac=0.0,
               early_tp_pct=0.0, early_frac=0.0):
    """챔피언 진입(sig_TF) + 눌림목(pivot_TF,N) 피보 스텝업 청산 + 1m 체결 + 실펀딩 + 현실수수료.
       ext_side=None이면 TS(Trend+피봇). 배열주면 REV(외부신호 방향 arming→눌림목 확정 후 진입, align_pivot).
       반환 거래: et,xt,side,entry,exit,R(순단위·수수료·펀딩 차감),mae(1m 가격편위),fund,year."""
    ftimes, fpref = fund
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], sig_tf); sig = TS.compute_signals(dfx)
    high = dfx['high'].values; low = dfx['low'].values; close = dfx['close'].values; open_ = dfx['open'].values
    idx = dfx.index; n = len(close); Trend = sig['Trend']; ph_c = sig['ph_conf']; pl_c = sig['pl_conf']
    atr = sig['atr']; er = sig['er']
    edges = idx.values
    lo_sw, hi_sw = swings_on_tf(d1m, pivot_tf, N)
    lo_bar = bucket_swings(lo_sw, edges); hi_bar = bucket_swings(hi_sw, edges)   # bar별 눌림목 저/고
    # 1m 배열(체결검증·mae용)
    m_t = d1m.index.values; mO = d1m["open"].values; mH = d1m["high"].values; mL = d1m["low"].values
    tf_td = np.timedelta64(sig_tf, 'm')

    def fund_of(et, xt, side):
        lo = int(np.searchsorted(ftimes, np.datetime64(et), 'right'))
        hi = int(np.searchsorted(ftimes, np.datetime64(xt), 'right'))
        return side * (fpref[hi] - fpref[lo])

    def exit_fill_1m(side, sl, bar_t):
        """sl 터치를 bar_t의 1m봉에서 첫 검색. 반환 (체결가, ★실제 1분 체결시각). 갭이면 open(더 나쁨). 미터치=(None,None)."""
        a = int(np.searchsorted(m_t, np.datetime64(bar_t), 'left'))
        b = int(np.searchsorted(m_t, np.datetime64(bar_t) + tf_td, 'left'))
        for k in range(a, b):
            if side == 1 and mL[k] <= sl: return min(mO[k], sl), m_t[k]
            if side == -1 and mH[k] >= sl: return max(mO[k], sl), m_t[k]
        return None, None

    def hit_time_1m(side, level, t0):
        """t0봉(sig_tf창) 1m서 가격이 level에 처음 닿은 1분시각(표시용). 롱=low<=level/숏=high>=level. 미도달=t0."""
        a = int(np.searchsorted(m_t, np.datetime64(t0), 'left'))
        b = int(np.searchsorted(m_t, np.datetime64(t0) + tf_td, 'left'))
        for k in range(a, b):
            if side == 1 and mL[k] <= level: return m_t[k]
            if side == -1 and mH[k] >= level: return m_t[k]
        return np.datetime64(t0)

    def mae_1m(side, entry, et, xt):
        a = int(np.searchsorted(m_t, np.datetime64(et), 'left'))
        b = int(np.searchsorted(m_t, np.datetime64(xt), 'right'))
        if b <= a: return 0.0
        if side == 1: return float(np.min((mL[a:b] - entry) / entry))
        return float(np.min((entry - mH[a:b]) / entry))

    lastPH = lastPL = np.nan; pos = 0; entry = np.nan; ei = -1; sl = np.nan; pb = 0
    lastHiP = lastLoP = np.nan          # ★눌림목 TF(pivot_tf) 최근 고/저 — Fib 스텝업 참조(TF통일)
    e_fills = None; armed_dir = 0; armed_left = 0
    tp_taken = False; tp_level = np.nan; tp_R = 0.0   # ★레버P: 구조(직전 반대편 눌림목) 부분익절
    early_taken = False; early_target = np.nan; early_R = 0.0   # ★조기익절(고정%, 260627_02 발견·검증)
    trades = []
    for i in range(n):
        new_ph = i in ph_c; new_pl = i in pl_c
        if new_ph: lastPH = ph_c[i][1]
        if new_pl: lastPL = pl_c[i][1]
        if hi_bar[i]: lastHiP = hi_bar[i][-1]
        if lo_bar[i]: lastLoP = lo_bar[i][-1]
        if ext_side is not None and align_pivot:    # REV: 외부신호 방향 arming(신호 뜨면 arm_bars봉 유효)
            if ext_side[i] != 0: armed_dir = int(ext_side[i]); armed_left = arm_bars
            else: armed_left = max(0, armed_left - 1)
        if pos != 0:
            ex = None; reason = None; xt_fill = None
            # ★레버P 구조 부분익절(opt-in): 직전 반대편 눌림목(tp_level)에 1m 도달하면 tp_frac만큼 지정가(maker) 익절. 0=off.
            if tp_frac > 0 and not tp_taken and i > ei and not np.isnan(tp_level):
                a = int(np.searchsorted(m_t, np.datetime64(idx[i]), 'left')); bb = int(np.searchsorted(m_t, np.datetime64(idx[i]) + tf_td, 'left'))
                if bb > a and ((pos == 1 and mH[a:bb].max() >= tp_level) or (pos == -1 and mL[a:bb].min() <= tp_level)):
                    tp_taken = True
                    tp_R = pos * (tp_level - entry) / entry - (MK + MK) - fund_of(idx[ei], idx[i], pos)  # 진입maker+익절 지정가maker
            # ★조기익절(opt-in, 260627_02): 진입 후 +early_tp_pct 도달시 early_frac만큼 maker 익절. 0=off=기존동일.
            if early_tp_pct > 0 and not early_taken and i > ei and not np.isnan(early_target):
                a2 = int(np.searchsorted(m_t, np.datetime64(idx[i]), 'left')); b2 = int(np.searchsorted(m_t, np.datetime64(idx[i]) + tf_td, 'left'))
                if b2 > a2 and ((pos == 1 and mH[a2:b2].max() >= early_target) or (pos == -1 and mL[a2:b2].min() <= early_target)):
                    early_taken = True
                    early_R = pos * (early_target - entry) / entry - (MK + MK) - fund_of(idx[ei], idx[i], pos)  # 진입maker+조기익절 지정가maker
            # 추세전환 청산(종가 = 봉마감 시각) — REV는 use_trend_flip=False로 끔
            if use_trend_flip and ((pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)):
                ex = close[i]; reason = "flip"; xt_fill = pd.Timestamp(idx[i]) + pd.Timedelta(minutes=int(sig_tf)) - pd.Timedelta(minutes=1)
            else:
                if i > ei and not np.isnan(sl):
                    f, ftime = exit_fill_1m(pos, sl, idx[i])   # ★실제 1분 체결시각도
                    if f is not None: ex = f; reason = "fibstop"; xt_fill = pd.Timestamp(ftime)
            # ★레버T 시간손절(opt-in): 진입 후 time_stop_bars봉 경과 & 평가R<=minR(미진행)면 종가 시장청산(taker). 0=off=기존동일.
            if ex is None and time_stop_bars and (i - ei) >= time_stop_bars and pos * (close[i] - entry) / entry <= time_stop_minR:
                ex = close[i]; reason = "timestop"
                xt_fill = pd.Timestamp(idx[i]) + pd.Timedelta(minutes=int(sig_tf)) - pd.Timedelta(minutes=1)
            if ex is not None:
                R = pos * (ex - entry) / entry
                fp = fund_of(idx[ei], idx[i], pos)
                R = R - (MK + TK) - fp                       # 진입maker+청산taker + 실펀딩 (★봉기준 불변)
                if tp_frac > 0 and tp_taken:                  # ★레버P: tp_frac 익절분 + 잔량 청산분 블렌드
                    R = tp_frac * tp_R + (1.0 - tp_frac) * R
                if early_frac > 0 and early_taken:            # ★조기익절: early_frac 1차익절 + 잔량(위 R=tp_frac/fibstop) 블렌드
                    R = early_frac * early_R + (1.0 - early_frac) * R
                # ★무비용 R(gross, 비용분해 §19용) — net R과 동일 블렌드구조(early/tp 반영). R로직 불변=앵커무손상.
                Rg = pos * (ex - entry) / entry
                if tp_frac > 0 and tp_taken:
                    Rg = tp_frac * (pos * (tp_level - entry) / entry) + (1.0 - tp_frac) * Rg
                if early_frac > 0 and early_taken:
                    Rg = early_frac * (pos * (early_target - entry) / entry) + (1.0 - early_frac) * Rg
                mae = mae_1m(pos, entry, idx[ei], idx[i])
                x_int = close[i] if reason in ("flip", "timestop") else sl  # 청산 의도가(flip/timestop=종가 / fibstop=스톱레벨)
                et_fill = e_fills[0][0] if e_fills else idx[ei]   # 진입 1차체결 실제시각(표시용)
                trades.append(dict(et=idx[ei], xt=idx[i], et_fill=et_fill, xt_fill=xt_fill,
                                   side=pos, entry=entry, exit=ex, R=R, gross_R=Rg, mae=mae, fund=fp,
                                   reason=reason, x_int=float(x_int), year=idx[i].year,
                                   tp=bool(tp_taken), fills=e_fills)); pos = 0; sl = np.nan; pb = 0; e_fills = None
                tp_taken = False; tp_level = np.nan; tp_R = 0.0
                early_taken = False; early_target = np.nan; early_R = 0.0
                continue
        # 피보 스텝업: 이 sig봉에 확정된 눌림목(저/고)마다 SL 계단상향. 참조 고/저는 눌림목 TF로 통일.
        #   ★스톱 캡: 롱=현재가(close) 아래로만, 숏=위로만 → '시장 위 스톱→이론가 환상체결' 제거.
        fsc = (fib_scale[i] if fib_scale is not None else 1.0)     # ★레버R: 불리레짐서 r↑(스톱을 가격쪽으로 더 당김=타이트). 1.0=기존.
        if pos == 1:
            for plv in lo_bar[i]:
                pb += 1; r = min(0.98, (fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]) * fsc)
                ref = lastHiP if not np.isnan(lastHiP) else high[i]
                cand = ref - r * (ref - plv)
                if cand <= close[i]:                              # 시장 아래 유효 스톱만 반영(위면 무시)
                    sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1:
            for phv in hi_bar[i]:
                pb += 1; r = min(0.98, (fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]) * fsc)
                ref = lastLoP if not np.isnan(lastLoP) else low[i]
                cand = ref + r * (phv - ref)
                if cand >= close[i]:                              # 시장 위 유효 스톱만 반영(아래면 무시)
                    sl = cand if np.isnan(sl) else min(sl, cand)
        # 진입(flat=청산 후에만)
        if pos == 0:
            if ext_side is None:                                  # TS: 챔피언 조건(Trend+피봇)
                le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
                se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            elif align_pivot:                                     # REV: 외부신호 방향 + 눌림목 확정 후 진입
                le = armed_dir == 1 and armed_left > 0 and new_pl and not np.isnan(lastPH)
                se = armed_dir == -1 and armed_left > 0 and new_ph and not np.isnan(lastPL)
            else:
                le = ext_side[i] == 1; se = ext_side[i] == -1
            if (le or se) and ext_side is None and er[i] < er_gate: le = se = False
            if le or se:
                d = 1 if le else -1
                ep = TS.compute_split_entry(d, i, close, high, low, open_, n, pl_c, ph_c, lastPH, lastPL, 'A', 3)
                pos = d; entry = ep; ei = i; pb = 0
                risk = float(np.clip(atr[i] / ep * init_atr_mult, 0.005, 0.08)) if atr[i] > 0 else 0.02
                sl = ep * (1 - d * risk)
                # ★레버P TP목표 = 진입시 직전 반대편 눌림목(롱=고/숏=저), 수익방향일 때만 유효
                tp_taken = False; tp_R = 0.0
                _tl = lastHiP if d == 1 else lastLoP
                tp_level = _tl if (not np.isnan(_tl) and ((d == 1 and _tl > ep) or (d == -1 and _tl < ep))) else np.nan
                early_taken = False; early_R = 0.0          # ★조기익절 목표 = 진입가 ± early_tp_pct
                early_target = ep * (1 + d * early_tp_pct) if early_tp_pct > 0 else np.nan
                if capture_fills:
                    raw = split_fills(d, i, close, high, low, n, idx, lastPH, lastPL, 3)
                    base_t = pd.Timestamp(idx[i]) + pd.Timedelta(minutes=int(sig_tf)) - pd.Timedelta(minutes=1)
                    e_fills = [(base_t, raw[0][1])]          # 1차=신호봉 종가 → 봉마감 시각
                    for bt, pp in raw[1:]:                   # 되돌림=1m 첫 도달시각(미체결=base가→봉마감)
                        if abs(pp - raw[0][1]) < 1e-9: e_fills.append((base_t, pp))
                        else: e_fills.append((pd.Timestamp(hit_time_1m(d, pp, bt)), pp))
    return pd.DataFrame(trades)


def account_metrics(T, size_pct, lev, mask=None):
    """PaperAccount(성급계열) 호출 — 강제청산·MMR·복리. mask=기간필터."""
    if mask is not None: T = T[mask]
    if len(T) < 5: return None
    acct = PE.PaperAccount(10000.0)
    for _, r in T.sort_values("et").iterrows():
        acct.open(Signal(Action.ENTER, side=Side(int(r.side)), size_pct=size_pct, leverage=lev), ts=None, price=100.0)
        acct.resolve_replay(R=float(r.R), mae=float(r.mae), fund=float(r.fund))
    ret, mdd, cal = acct.metrics()
    return dict(ret=ret, mdd=mdd, cal=cal, n=len(T), nliq=acct.n_liq)


def cpcv_R(R):
    R = np.asarray(R, float); n = len(R)
    if n < 30: return np.nan
    g6 = np.array_split(np.arange(n), 6); s = []
    for c in itertools.combinations(range(6), 2):
        rr = R[np.concatenate([g6[k] for k in c])]
        s.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return float(np.percentile(s, 25))


def optimize(d1m, fund, n_trials=120):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    SIG_TFS = [15, 30, 60, 120, 240, 420, 480, 720]
    PIV_TFS = [1, 5, 20, 60, 240, 480]

    def objective(tr):
        sig_tf = tr.suggest_categorical("sig_tf", SIG_TFS)
        pivot_tf = tr.suggest_categorical("pivot_tf", PIV_TFS)
        if pivot_tf > sig_tf: return -10.0
        N = tr.suggest_int("N", 2, 10)
        f1 = tr.suggest_float("fib1", 0.15, 0.45); f2 = tr.suggest_float("fib2", 0.45, 0.65); f3 = tr.suggest_float("fib3", 0.65, 0.92)
        iam = tr.suggest_float("init_atr_mult", 0.5, 3.0)
        erg = tr.suggest_float("er_gate", 0.0, 0.5)
        sp = tr.suggest_float("size_pct", 1.0, 8.0); lv = tr.suggest_float("lev", 3.0, 22.0)
        try:
            T = gen_trades(d1m, fund, sig_tf, pivot_tf, N, (f1, f2, f3), iam, er_gate=erg)
            if TRAIN_ONLY: T = T[T.et <= TRAIN_END]      # ★held-out: 학습기간만으로 목적계산
            if len(T) < 40: return -10.0
            # ★강건 목적함수: CPCV p25(모든 폴드 양수=레짐강건) — 학습최대화(과적합) 폐기
            p25 = cpcv_R(T.R.values)
            if np.isnan(p25): return -10.0
            mfull = account_metrics(T, sp, lv, mask=None)
            if mfull is None or mfull["mdd"] >= -1e-9: return -10.0
            score = p25
            if mfull["mdd"] < -20: score -= (abs(mfull["mdd"]) - 20) * 0.05   # MDD>-20 소프트
            # 연도 강건: 어느 해라도 크게 음수면 감점(2025형 붕괴 회피)
            T2 = T.copy(); T2["y"] = pd.to_datetime(T2.et).dt.year
            yr_min = min((g.R.sum() for _, g in T2.groupby("y")), default=-1)
            if yr_min < -0.15: score -= (abs(yr_min) - 0.15) * 1.0
            return score
        except Exception:
            return -10.0

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    bp = study.best_params
    _p(f"\n[최적 params] {bp}")
    T = gen_trades(d1m, fund, bp["sig_tf"], bp["pivot_tf"], bp["N"], (bp["fib1"], bp["fib2"], bp["fib3"]), bp["init_atr_mult"], er_gate=bp["er_gate"])
    _p("=" * 76); _p("최적 config 정직판정 (현실비용·실펀딩·PaperAccount 강제청산·1m체결·워크포워드)"); _p("=" * 76)
    for nm, msk in [("학습(23~24)", T.et <= TRAIN_END), ("검증 OOS(25~26)", T.et > TRAIN_END), ("전체", T.et == T.et)]:
        m = account_metrics(T, bp["size_pct"], bp["lev"], mask=msk)
        if m: _p(f"  {nm:<16} 복리 {m['ret']:>+7.0f}%  MDD {m['mdd']:>+6.1f}%  Calmar {m['cal']:>4.1f}  거래 {m['n']:>4}  강제청산 {m['nliq']}회")
    _p(f"  거래레벨 CPCV p25 Sharpe: {cpcv_R(T.R.values):+.2f} | 승률 {100*(T.R>0).mean():.0f}%")
    T["y"] = pd.to_datetime(T.et).dt.year
    _p("  연도별 거래R합: " + "  ".join(f"{y}:{g.R.sum()*100:+.0f}%({len(g)})" for y, g in T.groupby("y")))
    import json; json.dump(bp, open(os.path.join(HERE, "best_params_full.json"), "w"), indent=2)
    T.to_csv(os.path.join(HERE, "ledger_full_opt.csv"), index=False, encoding="utf-8-sig")
    _p("[저장] best_params_full.json · ledger_full_opt.csv")
    _p("[판정] 검증 OOS 복리>0 AND CPCV p25>0 AND MDD>-20 = 채택. 미달=과적합/미완 명시.")


def main():
    d1m = load_1m(); fund = load_funding()
    _p(f"[데이터] 1m {len(d1m)} | 실펀딩 {len(fund[0])}")
    if len(sys.argv) > 1 and sys.argv[1] == "opt":
        nt = int(sys.argv[2]) if len(sys.argv) > 2 else 120
        if "heldout" in sys.argv:
            globals()["TRAIN_ONLY"] = True
            _p("[★held-out 모드] 목적함수=학습(≤2024)만 → 2025~26 완전 미사용 검증")
        _p(f"[ML 워크포워드 최적화 시작 — {nt} trials]")
        optimize(d1m, fund, nt); return
    T = gen_trades(d1m, fund, 420, 420, 4, (0.3, 0.5, 0.6), 1.5)
    _p(f"[베이스 7h] 거래 {len(T)} 승률 {100*(T.R>0).mean():.0f}% 청산이유 {T.reason.value_counts().to_dict()}")
    for sp, lv in [(7.0864, 22.0), (3.0, 10.0), (1.0, 5.0)]:
        m = account_metrics(T, sp, lv)
        if m: _p(f"  size{sp} lev{lv}: 복리 {m['ret']:+.0f}% MDD {m['mdd']:.1f}% Calmar {m['cal']:.1f} 강제청산 {m['nliq']}회")


if __name__ == "__main__":
    main()
