# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch1_Slippage_stg5_MaeLiqLimitFix.py
# 코드길이: 약 280줄 | 내부버전: 07Prj_Ch1_stg5_MaeLiqLimitFix_v2 | 로직 전체 출력(축약/생략 없음)
# ---------------------------------------------------------------------------------------------
# [★stg4 → stg5 버그 수정 2건 — 반드시 인지]
#   버그1 (MAE 청산봉 누락): stg4 compute_mae가 MAE 구간을 [진입, 청산봉 시작]까지만 잡아,
#     청산이 일어난 봉(특히 trend_flip의 급락 봉)을 제외 → trend_flip 손실 15건 전부,
#     sl 손실 109건의 MAE가 최종 R보다 얕게 계산됨(물리적 불가, 최종손실이 도중최저보다 깊음).
#     수정: MAE 구간을 청산봉 끝(exit_t + TF_MIN분)까지 확장 + MAE=min(구간최저, 최종 가격손익률).
#       최종 가격손익률 = R + COST_RT + fund (R 역산, 청산시점 부호포함 손익).
#   버그2 (청산거리 FEE 이중적용): stg4 LIQ=1/L-MMR-FEE는 틀림. Binance 공식 청산가=Entry×[1-1/L+MMR],
#     즉 청산거리=1/L-MMR. 청산수수료는 청산 발동점이 아니라 청산 후 별도 차감(이미 -진입수량 전액에 내재).
#     수정: LIQ=1/L-MMR. 추가로 MMR을 명목별 적용(tier1 ≤$50k:0.40% / tier2 >$50k:0.50%).
# ---------------------------------------------------------------------------------------------
# [목적] 사장님 제시 5개 격리튕김 설정(7.5%×15 / 5%×20 / 4%×25 / 3.5%×30 / 3%×33)을
#   ★MAE(거래 도중 1분봉 최저점) 기준으로 36개월 검증. 기존 시뮬의 맹점(최종 R 기준 청산)을
#   바로잡아, "거래 도중 청산거리를 닿았다 회복한 거래"까지 정확히 잡는다.
# [핵심 발견 배경] 사장님 통찰: 손실한도를 낮추면 큰 손실(직행)은 자르지만, 손실났다 회복돼
#   수익으로 끝났을 거래(회복)의 수익 기회를 놓친다. 어느 쪽이 큰지는 MAE 없이 알 수 없다.
# [방식] A — 엔진 무수정. 청산된 거래의 손익을 청산값으로 대체하고 낮아진 잔고로 다음 거래
#   복리 진행(타이밍 불변). A 결과가 확실하면 방식 B(엔진 수정, 청산 후 새 진입 재탐색) 제안.
# ---------------------------------------------------------------------------------------------
# [데이터 출처 선언] 06Prj 챔피언 거래(greed55_smult0)를 엔진 무수정 재실행으로 동일 재현
#   + 원본 1분봉(Merged_Data_with_Regime_Features.csv)으로 거래별 MAE를 1분 해상도 계산.
# [사용명칭 정의] MAE=거래 도중 진입가 대비 최저 불리변동(롱=최저가, 숏=최고가) / ★청산거리 d=1/L-MMR (FEE 제외)
#   / 회복거래=청산됐으나 원래 R>0 / 직행거래=청산됐고 원래 R<=0 / EXP=진입수량×레버리지.
# ---------------------------------------------------------------------------------------------
# [수수료 규칙 — 사장님 지시 14bp 확정]
#   정상 거래(sl/trend_flip): R = 가격수익 - 0.0014(왕복14bp) - 실펀딩  (엔진 재현, 기존 유지)
#   격리튕김 청산 거래: 손익 = -진입수량(격리증거금 전액, 청산수수료1.25% 내재)
#                              - EXP×0.0007(진입측 절반 7bp)  - EXP×펀딩
#     ★청산측 7bp(슬리피지+시장가수수료)는 빼지 않음 — 거래소 강제청산이라 트레이더 시장가 주문 아님.
# ---------------------------------------------------------------------------------------------
# [사용 파일]
#   bots/SpTrd_Fib_V1_Champion.py (엔진 무수정 7f9192e3) : run_strategy/load_data/resample_tf/compute_signals
#   bots/SidewayDCA_Stg7_engine.py : load_funding/funding_sum
#   cooldown.py(apply_cooldown) / fear_greed_loader.py(map_to_bars) / regime_classifier.py(compute_indicators)
#   데이터(상위 D:\ML\verify): Merged_Data_with_Regime_Features.csv(1분봉) / Merged_Data.csv(OI)
#     / BTCUSDT_funding_history_8h.csv / Fear_Greed_Index_*.csv
# [출력 CSV] (실행 하위폴더)
#   stg5_maefix_summary.csv  : 5설정 × (격리튕김 ON/OFF 잔고·MDD·청산수·회복/직행 분해)
#   stg5_maefix_ledger.csv   : 거래별 원장 + entry_price + mae (MAE 포함 원장, 다음 작업자용)
#   stg5_maefix_coverage.csv : 실행 메타(거래수·1분봉수·펀딩·FNG커버)
# ---------------------------------------------------------------------------------------------
# [함수 In/Out]
#   load_engine(path,name)            In: 엔진경로·이름           Out: 모듈객체
#   find_file(cands)                  In: 후보파일명 리스트        Out: 존재경로 or None
#   ns_i64(dtindex)                   In: DatetimeIndex            Out: int64 ns 배열
#   load_label_smc(path,idx7)         In: 데이터경로·7h봉idx        Out: 봉별 장세라벨·컬럼명
#   build_raw_ext(...)                In: 엔진·데이터·신호 등        Out: raw 거래리스트(★entry·fund 포함)
#   apply_greed_guard(raw,th,sm)      In: raw·탐욕임계·숏배수        Out: 가드적용 거래·가드수
#   apply_4stack(raw)                 In: raw                      Out: 칩+쿨다운 적용 거래(kept)
#   compute_mae(kept,df1m,tf_min)     In: 거래·1분봉·봉길이(분)      Out: 거래에 mae 추가(청산봉포함)
#   sim_liqlimit(kept,entry_pct,lev)  In: 거래·진입%·레버리지        Out: ON/OFF 잔고·MDD·청산·분해 dict
#   main()                            In: -                        Out: CSV 3종
# [변수] START=10000 MMR_T1=0.004 MMR_T2=0.005 MMR_TIER=$50k FEE_LIQ=0.0125(청산손익내재) HALF_COST=0.0007 COST_RT=0.0014
#   GATE_ER=0.45 CHOP_HI=65 ER_LO=0.35 ADX_LO=25 COOL_K=4 COOL_M=8 BAR_MIN=420
#   GREED_BEST=55 SMULT_BEST=0.0  CONFIGS=[(7.5,15),(5,20),(4,25),(3.5,30),(3,33)]
# =============================================================================================
import os, sys, importlib.util
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cooldown as CD
import fear_greed_loader as FG

# ── 상수 (06Prj 챔피언 동결값 + 07Prj 격리튕김) ──
START = 10000.0
MMR_T1 = 0.004       # ★유지증거금률 tier1 (명목 ≤$50k, Binance BTCUSDT USDⓈ-M)
MMR_T2 = 0.005       # ★유지증거금률 tier2 (명목 >$50k)
MMR_TIER_USDT = 50000.0   # tier1/tier2 명목 경계(USDT)
FEE_LIQ = 0.0125     # 강제청산 수수료 1.25% (★청산 손익 -진입수량에 내재. 청산거리엔 미반영)
HALF_COST = 0.0007   # 14bp 왕복의 절반(진입측 = 슬리피지+시장가수수료)
COST_RT = 0.0014     # 정상거래 왕복 비용 14bp
GATE_ER = 0.45
CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0
COOL_K = 4; COOL_M = 8
BAR_MIN = 420
GREED_BEST = 55      # 챔피언 탐욕 임계
SMULT_BEST = 0.0     # 챔피언 숏배수(완전차단)
YEARS = [2023, 2024, 2025, 2026]
CONFIGS = [(7.5, 15), (5.0, 20), (4.0, 25), (3.5, 30), (3.0, 33)]


def load_engine(p, nm):
    spec = importlib.util.spec_from_file_location(nm, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


def ns_i64(dtindex):
    return np.asarray(dtindex.values).astype('datetime64[ns]').astype('int64')


def load_label_smc(data_path, tf_index):
    try:
        head = pd.read_csv(data_path, nrows=1)
        smc_col = None
        for cand in ['label_smc_8', 'label_smc_5', 'label_smc_12']:
            if cand in head.columns:
                smc_col = cand; break
        if smc_col is None:
            return None, None
        df = pd.read_csv(data_path, usecols=['timestamp', smc_col], index_col='timestamp', parse_dates=True)
        if getattr(df.index, 'tz', None) is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()
        s = df[smc_col].reindex(df.index.union(tf_index)).ffill().reindex(tf_index)
        return s.values, smc_col
    except Exception:
        return None, None


def build_raw_ext(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7, fng_arr, smc_arr):
    # 06Prj build_raw와 동일 거래 생성 + ★raw dict에 entry(진입평단가)·fund(펀딩) 추가
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=GATE_ER,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); raw = []
    for t in ttr:
        fund = fpay(t['side'], t['entry_t'], t['exit_t'])
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        chop = ind['chop'][pos]; er = ind['er'][pos]; adx = ind['adx'][pos]
        is_chip = bool(np.isfinite(chop) and chop > CHOP_HI and np.isfinite(er) and er < ER_LO
                       and np.isfinite(adx) and adx < ADX_LO)
        fng = fng_arr[pos] if pos < len(fng_arr) else np.nan
        if smc_arr is not None and pos < len(smc_arr):
            rg = smc_arr[pos]
            regime = str(rg) if rg is not None and (isinstance(rg, str) or not (isinstance(rg, float) and np.isnan(rg))) else 'unknown'
        else:
            rnum = ind['regime'][pos] if 'regime' in ind else -1
            regime = RC.REGIME_NAMES.get(int(rnum), 'unknown') if rnum >= 0 else 'unknown'
        raw.append(dict(side=int(t['side']), entry_t=et, exit_t=pd.Timestamp(t['exit_t']), year=et.year,
                        ym=et.strftime('%Y-%m'), R=float(R), reason=t.get('reason', '?'),
                        bar=pos, is_chip=is_chip, fng=float(fng), regime=regime,
                        entry=float(t['entry']), fund=float(fund)))   # ★신규: 진입평단가·펀딩
    return raw


def apply_greed_guard(raw, greed_th, short_mult):
    out = []; n_guarded = 0
    for t in raw:
        if t['side'] == -1 and np.isfinite(t['fng']) and t['fng'] >= greed_th:
            if short_mult == 0.0:
                n_guarded += 1; continue
            t2 = dict(t); t2['R'] = t['R'] * short_mult; n_guarded += 1; out.append(t2)
        else:
            out.append(t)
    return out, n_guarded


def apply_4stack(raw):
    after_chip = [t for t in raw if not t['is_chip']]
    keep_idx, n_exc, n_trig = CD.apply_cooldown(after_chip, BAR_MIN, COOL_K, COOL_M)
    kept = [after_chip[i] for i in keep_idx]
    return kept


def compute_mae(kept, df1m, tf_min):
    # ★거래별 MAE(진입가 대비 최저 불리변동) 1분봉 계산. 벡터화(searchsorted).
    # ★stg5 수정: MAE 구간을 청산봉 끝(exit_t + tf_min분)까지 확장하여 청산봉(급락봉) 포함.
    #   추가로 MAE=min(구간최저, 최종 가격손익률)로 보정 → 최종손실이 반드시 MAE에 반영(물리 정합).
    #   최종 가격손익률 = R + COST_RT + fund (build_raw_ext의 R 정의 역산).
    ts = ns_i64(df1m.index)
    low = df1m['low'].values.astype('float64')
    high = df1m['high'].values.astype('float64')
    tf_ns = np.int64(int(tf_min) * 60 * 1_000_000_000)   # 분 → ns
    for t in kept:
        e = np.int64(pd.Timestamp(t['entry_t']).value)
        x = np.int64(pd.Timestamp(t['exit_t']).value) + tf_ns   # ★청산봉 끝까지
        i0 = int(np.searchsorted(ts, e, side='left'))
        i1 = int(np.searchsorted(ts, x, side='right'))
        ep = t['entry']
        final_px = float(t['R'] + COST_RT + t['fund'])   # 청산시점 가격손익률(부호포함)
        if i1 <= i0 or ep <= 0:
            t['mae'] = min(0.0, final_px); continue
        if t['side'] == 1:          # 롱: 최저가가 최악
            interval = float((low[i0:i1].min() - ep) / ep)
        else:                       # 숏: 최고가가 최악
            interval = float((ep - high[i0:i1].max()) / ep)
        t['mae'] = min(interval, final_px)   # ★둘 중 더 깊은(작은) 값
    return kept


def sim_liqlimit(kept, entry_pct, lev):
    # ★MAE 기준 격리튕김 시뮬. 격리튕김 ON(도중청산) vs OFF(청산없음) 둘 다 복리 계산.
    # ★stg5 수정: 청산거리 LIQ=1/L-MMR (청산수수료 FEE 미반영, Binance 공식).
    #   MMR은 거래 진입 시점 명목(cap×EXP)의 tier로 결정(tier1 ≤$50k:0.40% / tier2:0.50%).
    entry = entry_pct / 100.0
    EXP = entry * lev
    s = sorted(kept, key=lambda t: pd.Timestamp(t['exit_t']).value)

    def liq_dist_at(cap):
        notional = cap * EXP                       # 명목(USDT)
        mmr = MMR_T1 if notional <= MMR_TIER_USDT else MMR_T2
        return -(1.0 / lev - mmr)                  # 청산거리(음수)

    def run(liq_on):
        cap = START; peak = START; mdd = 0.0
        n_liq = 0; rec_n = 0; rec_loss = 0.0; dir_n = 0; dir_gain = 0.0
        for t in s:
            orig = t['R'] * EXP                       # 정상(격리튕김 OFF) 손익
            LIQ = liq_dist_at(cap)                    # ★거래별 청산거리(명목 tier 반영)
            if liq_on and t.get('mae', 0.0) <= LIQ:   # 도중 청산 발동
                # 격리전액(-entry, 청산수수료 내재) - 진입측7bp - 펀딩. 청산측7bp 제외.
                pnl = -entry - EXP * (HALF_COST + t['fund'])
                n_liq += 1
                if t['R'] > 0:
                    rec_n += 1; rec_loss += (orig - pnl)      # 회복거래: 놓친 수익(+)
                else:
                    dir_n += 1; dir_gain += (pnl - orig)      # 직행거래: 방어 효과(+이면 이득)
            else:
                pnl = orig
            cap *= (1.0 + pnl)
            peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
        return cap, mdd * 100.0, n_liq, rec_n, rec_loss * 100.0, dir_n, dir_gain * 100.0

    on = run(True); off = run(False)
    liq_lo = liq_dist_at(START); liq_hi = liq_dist_at(START * 6)   # 참고용 청산거리 범위
    return dict(setting=f"{entry_pct}%x{lev}", entry_pct=entry_pct, lev=lev,
                EXP=round(EXP, 3), LIQ_dist=round(liq_lo * 100, 2),
                LIQ_dist_t2=round(liq_hi * 100, 2), single_loss=-entry_pct,
                cap_off=round(off[0], 0), mdd_off=round(off[1], 2),
                cap_on=round(on[0], 0), mdd_on=round(on[1], 2),
                net_effect=round(on[0] - off[0], 0),     # ON - OFF (양수면 격리튕김 이득)
                n_liq=on[2],
                recover_n=on[3], recover_loss_pct=round(on[4], 2),   # 회복거래 놓친 수익(%p합)
                direct_n=on[5], direct_gain_pct=round(on[6], 2))     # 직행거래 방어(%p합)


def main():
    print("[07Prj_Ch1 stg5] MAE 격리튕김 5설정 재검증 (버그2건 수정: MAE청산봉포함 + 청산거리1/L-MMR)")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    FNG = find_file(["Fear_Greed_Index_Clean.csv", "Fear_Greed_Index_2018to20260602.csv",
                     "Fear_Greed_Index_4Years.csv", "Fear_Greed_Index.csv"])
    if DATA is None or FNG is None:
        pd.DataFrame([{'x': f'missing DATA={DATA} FNG={FNG}'}]).to_csv(
            os.path.join(HERE, "stg5_maefix_summary.csv"), index=False, encoding='utf-8-sig')
        print(f"[ERR] 데이터없음 DATA={DATA} FNG={FNG}"); return

    df1m = champ.load_data(DATA)
    df7 = champ.resample_tf(df1m, champ.TF_MIN)
    sig = champ.compute_signals(df7)
    idx7 = df7.index
    oi7 = champ.load_oi_8h(OIPATH, idx7)
    bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    fund_real = ft is not None
    fng_arr, fng_cov = FG.map_to_bars(FNG, idx7)
    smc_arr, smc_col = load_label_smc(DATA, idx7)
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    if 'regime' not in ind:
        try:
            reg, _ds, _tv, _i = RC.classify(o, h, l, c, RC.DEFAULT_PARAMS, ind=ind)
            ind['regime'] = reg
        except Exception:
            ind['regime'] = np.full(len(c), -1)

    raw0 = build_raw_ext(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7, fng_arr, smc_arr)
    guarded, ng = apply_greed_guard(raw0, GREED_BEST, SMULT_BEST)   # greed55_smult0 챔피언
    kept = apply_4stack(guarded)
    kept = compute_mae(kept, df1m, champ.TF_MIN)
    print(f"[준비] raw {len(raw0)} → 가드후 {len(guarded)} → 챔피언거래 {len(kept)}건 / "
          f"펀딩{'REAL' if fund_real else 'NONE'} / FNG커버{fng_cov*100:.1f}% / 1분봉 {len(df1m)}행")

    # ── 5설정 시뮬 ──
    rows = [sim_liqlimit(kept, ep, lv) for (ep, lv) in CONFIGS]
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "stg5_maefix_summary.csv"), index=False, encoding='utf-8-sig')

    # ── MAE 포함 원장 (다음 작업자용) ──
    led = pd.DataFrame([dict(entry_t=str(t['entry_t']), exit_t=str(t['exit_t']), ym=t['ym'],
                             year=t['year'], side=t['side'], R=round(t['R'], 6), reason=t['reason'],
                             regime=t['regime'], fng=round(t['fng'], 1) if np.isfinite(t['fng']) else None,
                             entry_price=round(t['entry'], 2), fund=round(t['fund'], 6),
                             mae=round(t.get('mae', 0.0), 6)) for t in kept])
    led.to_csv(os.path.join(HERE, "stg5_maefix_ledger.csv"), index=False, encoding='utf-8-sig')

    # ── 실행 메타 ──
    pd.DataFrame([dict(n_trades=len(kept), n_1min_bars=len(df1m), n_7h_bars=len(idx7),
                       funding='REAL' if fund_real else 'NONE', fng_coverage_pct=round(fng_cov*100, 2),
                       regime_source=smc_col or 'regime_classifier',
                       cost_rt=COST_RT, fee_liq=FEE_LIQ, half_cost=HALF_COST)]).to_csv(
        os.path.join(HERE, "stg5_maefix_coverage.csv"), index=False, encoding='utf-8-sig')

    print("[완료] stg5_maefix_summary.csv / stg5_maefix_ledger.csv / stg5_maefix_coverage.csv 저장")
    for r in rows:
        print(f"  {r['setting']:>10} | OFF ${r['cap_off']:>8,.0f}({r['mdd_off']}%) | "
              f"ON ${r['cap_on']:>8,.0f}({r['mdd_on']}%) | 순효과 ${r['net_effect']:>+8,.0f} | "
              f"청산{r['n_liq']}(회복{r['recover_n']}/직행{r['direct_n']})")


if __name__ == "__main__":
    main()
