# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg1_DualBotIntegBacktest.py
# 코드길이: 약 300줄 | 내부버전: 06Prj_Ch6_Stg1_DualBotIntegBacktest_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   목적(딱 한 가지 로직): "추세봇 + 횡보봇을 한 계좌(자본 70/30)에 올리면 '진짜' 합산 수익률·MDD가 얼마인가?"
#     - 지난 채팅의 '+9.66% 단순합산'은 단위가 다른 두 봇 수익률을 그냥 더한 것이라 실제 계좌 수익이 아니었다.
#       이번엔 두 봇 거래를 '시간순'으로 한 자본곡선에 태워, 회계적으로 성립하는 합산 수익률·MDD를 만든다.
#   엔진 무수정: 두 엔진은 손대지 않고(해시 대조), 바깥에서 신호/거래결과만 읽는다.
#   ★중요 라벨: 파라미터는 '현재값(스누핑 포함)' 그대로 → 이 숫자는 '낙관 상한치'다.
#               월목표 판단에 쓸 '결정용 숫자'는 다음 단계 Stg2(파라미터 동결+워크포워드) 이후에 나온다.
#   ★사장님 통찰 반영: 연도별·장세별로 두 봇 '각각의' 기여도를 따로 출력 → 2025 같은 횡보장을
#                      횡보봇이 실제로 얼마나 받쳐주는지 눈으로 확인한다.
#
#   [통합 모델 — 가정 전부 명시, 전부 상수로 조정 가능]
#     · 자본배분 동결: 추세 70% / 횡보 30% (CAP_SPLIT_TREND=0.70). ← 동결값. 이 비율 자체는 최적화하지 않는다.
#     · 독립 슬리브: 각 봇은 '자기 몫 자본' 위에서만 복리. → 두 봇이 동시 보유해도 증거금 충돌이 없다(보수적·안전).
#       (대신 자본효율은 희생. '한 자본 공유' 더 공격적 모델은 향후 변형으로 둠.)
#     · 노출(실효노출): 인계서가 확정한 안전노출 추세E=1.2 / 횡보E=5.0을 기준값으로. 작은 그리드로 MDD 한계만 매핑.
#       노출은 알파가 아니다(PF 불변, 수익·MDD만 비례 스케일) → 'MDD -35% 안에 드는 최대 노출' 고르기는
#       과최적화가 아니라 '위험 사이징' 규칙이다.
#     · R 의미 차이 정확 반영(엔진 코드 직접 확인함):
#         - 추세봇 t['R']=원시 → 여기서 비용(COST_RT)·펀딩을 차감해 순R로 재계산(Stg13~15와 동일).
#         - 횡보봇 t['R']=엔진이 이미 비용·펀딩·포지션크기까지 반영한 순손익 → 그대로 사용(재계산 금지).
#
#   [Lookahead 차단] 봇 진입/청산은 엔진 그대로(미래참조 없음, 전 채팅 검증). label_smc_8은 '분석 태깅 전용'(봇 입력 아님).
#
# [PATH] 실행: D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg1_DualBotIntegBacktest\ . 데이터: 상위 D:\ML\verify (4종).
# [OUTPUT] combined_equity.csv / by_year.csv / by_regime.csv / exposure_frontier.csv / overlap.csv / summary.csv + .stg1_metric
#
# [사용 파일/함수/변수 In/Out 태그]
#   엔진(무수정):
#     champ.load_data(path)->df1m / champ.resample_tf(df,tf)->dftf / champ.compute_signals(dftf)->sig(dict)
#     champ.load_oi_8h(oipath,idx)->oi / champ.load_bb_8h(datapath,idx)->bb
#     champ.run_strategy(...)->trades[list[dict: entry_t,exit_t,side,entry,exit,R,reason]]
#     champ.NOMINAL/START_CAP/MIN_CAP/TF_MIN (상수)
#     sdca.load_1m(path)->s1 / sdca.resample_tf(s1,tf)->df8 / sdca.precompute(df8)->ssig
#     sdca.build_1m_map(s1,df8)->(ss,se) / sdca.run_bot_honest(...)->(trades,...) [trade R=순손익]
#     sdca.load_funding(path)->(ft,fr) / sdca.funding_sum(ft,fr,a_ns,b_ns)->float|None
#     sdca.BEST_PAR/DEFAULT_SLMULT/TF_MIN (상수)
#   본 코드 함수:
#     load_engine(p,nm)->module        : In 엔진경로,이름 / Out 임포트 모듈
#     find_file(cands)->path|None       : In 후보명리스트 / Out 존재경로
#     regime_lookup(DATA)->Series       : In 데이터경로 / Out timestamp->장세명(분석태깅 전용)
#     metrics(R)->dict                  : In R배열 / Out n,PF,ret%,payoff,win%
#     get_trend_trades(...)->list[dict] : Out 추세거래(순R,year,regime,entry_t,exit_t)
#     get_sideway_trades(...)->list[dict]: Out 횡보거래(순R,year,regime,entry_t,exit_t)
#     combined_equity(tT,tS,Et,Es,split)->dict : Out 합산 ret%,mdd%,liq,final,curve
#     overlap_hours(tT,tS)->dict        : Out 두 봇 동시보유 시간/비율
#   주요 변수:
#     CAP_SPLIT_TREND=0.70(동결) / E_TREND_BASE=1.2 / E_SW_BASE=5.0 / MDD_LIMIT=-35.0 / COST_RT=0.0014
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")

# ── 동결 상수(데이터 보기 전 확정, 이후 변경 금지) ──
CAP_SPLIT_TREND = 0.70          # 추세 70% / 횡보 30% (동결, 최적화 안 함)
E_TREND_BASE = 1.2              # 추세봇 안전노출(인계서 Stg1 확정)
E_SW_BASE = 5.0                 # 횡보봇 안전노출(인계서 Stg1 확정)
MDD_LIMIT = -35.0               # 절대 위험선
COST_RT = 0.0014                # 추세봇 왕복비용(0.14%). 횡보봇은 엔진 내부에서 비용처리.
E_TREND_GRID = [1.0, 1.2, 1.5]  # 노출 프런티어 매핑용(작은 고정 그리드 = 위험 사이징)
E_SW_GRID = [2.5, 5.0]
REGIME_MAP = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
NAME2INT = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def regime_lookup(DATA):
    # label_smc_8(정답지)을 '분석 태깅 전용'으로만 읽는다(봇 입력 아님). 1분봉 인덱스에 이미 ffill돼 있음.
    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    if lbl is None:
        return None
    s = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)[lbl]
    if getattr(s.index, 'tz', None) is not None:
        s.index = s.index.tz_localize(None)
    return s.sort_index()


def tag_regime(reg_series, ts):
    if reg_series is None:
        return 'unknown'
    try:
        pos = reg_series.index.searchsorted(pd.Timestamp(ts), side='right') - 1
        if pos < 0:
            return 'unknown'
        v = reg_series.iloc[pos]
        if isinstance(v, str):
            return v if v in NAME2INT else 'unknown'
        return REGIME_MAP.get(int(v), 'unknown')
    except Exception:
        return 'unknown'


def get_trend_trades(champ, sdca, DATA, OIPATH, FUND, reg_series):
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None

    def fund_pay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    # 현재 챔피언 설정 그대로: ER게이트0.45 + OI무덤필터 + 분할A
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        out.append(dict(bot='trend', entry_t=pd.Timestamp(t['entry_t']), exit_t=pd.Timestamp(t['exit_t']),
                        side=int(t['side']), R=float(R), year=pd.Timestamp(t['entry_t']).year,
                        regime=tag_regime(reg_series, t['entry_t'])))
    return out, (ft is not None)


def get_sideway_trades(champ, sdca, DATA, FUND, reg_series):
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    s1 = sdca.load_1m(DATA); df8 = sdca.resample_tf(s1, sdca.TF_MIN); ssig = sdca.precompute(df8)
    ss, se = sdca.build_1m_map(s1, df8)
    mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
    mT = s1.index.values.astype('datetime64[ns]').astype('int64')
    res = sdca.run_bot_honest(df8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT)
    trades = res[0] if isinstance(res, tuple) else res
    out = []
    for t in (trades or []):
        et = t.get('entry_t'); xt = t.get('exit_t')
        if et is None or xt is None:
            continue
        out.append(dict(bot='sideway', entry_t=pd.Timestamp(et), exit_t=pd.Timestamp(xt),
                        side=int(t.get('side', 0)), R=float(t.get('R', 0.0)),  # ★엔진 순R 직접사용(재계산 금지)
                        year=pd.Timestamp(et).year, regime=tag_regime(reg_series, et)))
    return out, (ft is not None)


def combined_equity(tT, tS, Et, Es, split_trend, start_cap, min_cap):
    # 두 봇 거래를 '청산시점' 기준 시간순으로 한 계좌(독립 슬리브)에 태운다.
    ev = [(t['exit_t'], 'T', t['R']) for t in tT] + [(t['exit_t'], 'S', t['R']) for t in tS]
    ev.sort(key=lambda x: x[0])
    cap_t = start_cap * split_trend
    cap_s = start_cap * (1.0 - split_trend)
    peak = cap_t + cap_s; mdd = 0.0; liq = False; curve = []
    for ts, who, R in ev:
        if who == 'T':
            f = 1.0 + R * Et
            cap_t = cap_t * f if f > 0 else 0.0
            if cap_t <= 0:
                liq = True
        else:
            f = 1.0 + R * Es
            cap_s = cap_s * f if f > 0 else 0.0
            if cap_s <= 0:
                liq = True
        total = cap_t + cap_s
        peak = max(peak, total)
        if peak > 0:
            mdd = min(mdd, (total - peak) / peak)
        curve.append((pd.Timestamp(ts), round(cap_t, 1), round(cap_s, 1), round(total, 1)))
        if total <= min_cap or liq:
            liq = True; break
    final = cap_t + cap_s
    return dict(ret_pct=round((final - start_cap) / start_cap * 100, 2), mdd_pct=round(mdd * 100, 1),
                liq=bool(liq), final=round(final, 0), curve=curve)


def overlap_hours(tT, tS):
    # 두 봇이 동시에 포지션을 들고 있는 시간(겹침) 측정. 독립슬리브에선 안전하지만, 공유자본 모델 판단용 참고치.
    def hours(trs):
        return sum((t['exit_t'] - t['entry_t']).total_seconds() for t in trs) / 3600.0
    hT = hours(tT); hS = hours(tS)
    iv = sorted([(t['entry_t'], t['exit_t']) for t in tT])
    ov = 0.0
    for t in tS:
        a, b = t['entry_t'], t['exit_t']
        for c, d in iv:
            lo = max(a, c); hi = min(b, d)
            if hi > lo:
                ov += (hi - lo).total_seconds() / 3600.0
    return dict(trend_h=round(hT, 1), sw_h=round(hS, 1), overlap_h=round(ov, 1),
                ov_pct_of_trend=round(100 * ov / hT, 1) if hT > 0 else 0.0,
                ov_pct_of_sw=round(100 * ov / hS, 1) if hS > 0 else 0.0)


def main():
    print("[Stg1] 두 봇 한 계좌 통합백테 (자본 70/30, 독립슬리브) — 현재파라미터=낙관상한치")
    open(os.path.join(HERE, ".run_start"), "w").close()
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data (Merged_Data_with_Regime_Features.csv 필요)'}]).to_csv(
            os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
    START_CAP = champ.START_CAP; MIN_CAP = champ.MIN_CAP

    reg_series = regime_lookup(DATA)
    tT, fT = get_trend_trades(champ, sdca, DATA, OIPATH, FUND, reg_series)
    tS, fS = get_sideway_trades(champ, sdca, DATA, FUND, reg_series)
    print(f"[거래추출] 추세봇 {len(tT)}건 / 횡보봇 {len(tS)}건 | 펀딩 추세{'O' if fT else 'X'} 횡보{'O' if fS else 'X'}")

    # ── 기준노출 합산 ──
    base = combined_equity(tT, tS, E_TREND_BASE, E_SW_BASE, CAP_SPLIT_TREND, START_CAP, MIN_CAP)
    pd.DataFrame(base['curve'], columns=['timestamp', 'cap_trend', 'cap_sw', 'total']).to_csv(
        os.path.join(HERE, "combined_equity.csv"), index=False, encoding='utf-8-sig')

    # ── 노출 프런티어(위험 사이징: MDD -35% 안에 드는 최대노출 매핑) ──
    fr_rows = []
    for et in E_TREND_GRID:
        for es in E_SW_GRID:
            r = combined_equity(tT, tS, et, es, CAP_SPLIT_TREND, START_CAP, MIN_CAP)
            fr_rows.append(dict(E_trend=et, E_sw=es, ret_pct=r['ret_pct'], mdd_pct=r['mdd_pct'],
                                liq=('YES' if r['liq'] else 'NO'),
                                within_mdd=('YES' if (r['mdd_pct'] >= MDD_LIMIT and not r['liq']) else 'NO')))
    fr_df = pd.DataFrame(fr_rows); fr_df.to_csv(os.path.join(HERE, "exposure_frontier.csv"), index=False, encoding='utf-8-sig')
    ok = fr_df[fr_df.within_mdd == 'YES']
    rec = ok.sort_values(['E_trend', 'E_sw'], ascending=False).iloc[0].to_dict() if len(ok) else None

    # ── 연도별 두 봇 기여도(단순 R합·비복리, 기준노출) — 2025 횡보장 업사이드 확인 ──
    def by_key(trs, key, E):
        d = {}
        for t in trs:
            d.setdefault(t[key], []).append(t['R'] * E)
        return {k: round(float(np.sum(v)) * 100, 2) for k, v in d.items()}
    years = sorted(set([t['year'] for t in tT] + [t['year'] for t in tS]))
    yr_rows = []
    yt = by_key(tT, 'year', E_TREND_BASE); ysw = by_key(tS, 'year', E_SW_BASE)
    for y in years:
        a = yt.get(y, 0.0); b = ysw.get(y, 0.0)
        yr_rows.append(dict(year=y, trend_Rsum_pct=a, sw_Rsum_pct=b, sum_pct=round(a + b, 2),
                            n_trend=sum(1 for t in tT if t['year'] == y), n_sw=sum(1 for t in tS if t['year'] == y)))
    pd.DataFrame(yr_rows).to_csv(os.path.join(HERE, "by_year.csv"), index=False, encoding='utf-8-sig')

    # ── 장세별 두 봇 기여도(분석 태깅 전용) ──
    regs = ['uptrend', 'downtrend', 'volatile_range', 'dead_range', 'unknown']
    rt = by_key(tT, 'regime', E_TREND_BASE); rsw = by_key(tS, 'regime', E_SW_BASE)
    rg_rows = [dict(regime=rg, trend_Rsum_pct=rt.get(rg, 0.0), sw_Rsum_pct=rsw.get(rg, 0.0),
                    n_trend=sum(1 for t in tT if t['regime'] == rg), n_sw=sum(1 for t in tS if t['regime'] == rg))
               for rg in regs]
    pd.DataFrame(rg_rows).to_csv(os.path.join(HERE, "by_regime.csv"), index=False, encoding='utf-8-sig')

    # ── 겹침 ──
    ov = overlap_hours(tT, tS)
    pd.DataFrame([ov]).to_csv(os.path.join(HERE, "overlap.csv"), index=False, encoding='utf-8-sig')

    # ── 단독 봇 성적(참고) ──
    mT = metrics([t['R'] for t in tT]); mS = metrics([t['R'] for t in tS])
    y2025 = next((r for r in yr_rows if r['year'] == 2025), None)

    verdict = (f"VERDICT Stg1 통합백테(현재파라미터=낙관상한치) | 자본배분 추세{int(CAP_SPLIT_TREND*100)}/횡보{int((1-CAP_SPLIT_TREND)*100)} 독립슬리브 | "
               f"거래 추세{len(tT)}/횡보{len(tS)} | "
               f"[기준노출 E추세{E_TREND_BASE}/E횡보{E_SW_BASE}] 합산수익 {base['ret_pct']}% MDD {base['mdd_pct']}% 청산{'Y' if base['liq'] else 'N'} | "
               f"단독 추세 PF{mT['PF']}/{mT['ret_pct']}% 횡보 PF{mS['PF']}/{mS['ret_pct']}% | "
               f"겹침 {ov['overlap_h']}h (추세대비 {ov['ov_pct_of_trend']}% / 횡보대비 {ov['ov_pct_of_sw']}%) | "
               f"권고노출(MDD<= {MDD_LIMIT} 최대) {('E추세'+str(rec['E_trend'])+'/E횡보'+str(rec['E_sw'])+' -> '+str(rec['ret_pct'])+'%/MDD'+str(rec['mdd_pct'])) if rec else '없음(전부 한계초과)'} | "
               f"★2025: 추세 {y2025['trend_Rsum_pct'] if y2025 else 'NA'}% + 횡보 {y2025['sw_Rsum_pct'] if y2025 else 'NA'}% = {y2025['sum_pct'] if y2025 else 'NA'}%(단순R합) | "
               f"펀딩 추세{'REAL' if fT else 'NONE'}/횡보{'REAL' if fS else 'NONE'}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[연도별] {yr_rows}"), dict(sec=f"[장세별] {rg_rows}"),
                  dict(sec=f"[프런티어] {fr_rows}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg1_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_sw={len(tS)}\ncap_split_trend={CAP_SPLIT_TREND}\n"
                f"base_ret={base['ret_pct']}\nbase_mdd={base['mdd_pct']}\nbase_liq={'YES' if base['liq'] else 'NO'}\n"
                f"trend_pf={mT['PF']}\ntrend_ret={mT['ret_pct']}\nsw_pf={mS['PF']}\nsw_ret={mS['ret_pct']}\n"
                f"overlap_h={ov['overlap_h']}\nov_pct_trend={ov['ov_pct_of_trend']}\nov_pct_sw={ov['ov_pct_of_sw']}\n"
                f"y2025_trend={y2025['trend_Rsum_pct'] if y2025 else 0}\ny2025_sw={y2025['sw_Rsum_pct'] if y2025 else 0}\n"
                f"y2025_sum={y2025['sum_pct'] if y2025 else 0}\n"
                f"rec_exposure={(str(rec['E_trend'])+'/'+str(rec['E_sw'])) if rec else 'NONE'}\n"
                f"rec_ret={rec['ret_pct'] if rec else 0}\nrec_mdd={rec['mdd_pct'] if rec else 0}\n"
                f"funding_trend={'REAL' if fT else 'NONE'}\nfunding_sw={'REAL' if fS else 'NONE'}\n"
                f"has_label_in_bot_input=False\nparams=CURRENT_SNOOPED(optimistic_ceiling)\n")
    print("[save] combined_equity/by_year/by_regime/exposure_frontier/overlap/summary.csv")


if __name__ == "__main__":
    main()
