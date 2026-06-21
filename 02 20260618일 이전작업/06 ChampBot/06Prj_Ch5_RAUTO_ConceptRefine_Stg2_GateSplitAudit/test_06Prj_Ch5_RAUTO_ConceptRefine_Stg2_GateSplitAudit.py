# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg2_GateSplitAudit.py
# 코드길이: 약 330줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg2_GateSplitAudit | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세봇(SpTrd_Fib_V1_Champion)을 '원본 그대로' 불러 돌리고, 두 가지를 바깥에서 진단한다.
#   ★전략 로직은 한 줄도 새로 안 짠다. bots/ 원본 엔진을 import 해서 그 함수·신호배열을 그대로 쓴다.
#
#   [로직1 — 게이트 감사] 2025년에 추세봇이 왜 +1.7%밖에 못 벌었나: '신호는 떴는데 게이트가 막았나,
#     아니면 신호 자체가 안 떴나'를 가린다. 엔진의 진입 트리거 조건(원본 라인 476-477)과 무덤필터
#     게이트(라인 483-499, gate_mode='er' gate_er=0.45, 무덤구간 0<=oi_z<1)를 그대로 복제해,
#     모든 봉을 분류한다: 진입성공 / 게이트차단(무덤) / 신호없음. 특히 2025-12 숏신호를 콕 집어 본다.
#     ★검증: 내가 'pos0에서 게이트통과로 분류한 봉'이 엔진의 실제 진입봉과 정확히 일치하는지 대조.
#            일치하면 내 트리거+게이트+포지션 복제가 엔진과 똑같다는 증명(추정 0).
#
#   [로직2 — 분할A 거품검증] 분할A의 +55.7%p가 진짜인가, 미래체결을 당겨쓴 착시인가.
#     엔진의 분할평단(원본 compute_split_entry 라인 381-405)을 그대로 복제해 거래별 평단을 재계산.
#     ★검증: 재계산 평단이 엔진이 실제 쓴 평단(trade['entry'])과 일치하는지 대조(일치=복제 정확).
#     그 뒤 '정직판'을 만든다: 되돌림 체결이 '청산 이후'에야 닿았다면 그 체결은 실제로 없었던 것이므로
#     그 몫을 보수적으로 신호봉 종가(base)로 되돌려 평단을 다시 계산 → R 재계산 → 누적·PF 비교.
#     엔진판 cumR − 정직판 cumR = '거품'.
#
# [★사용명칭 정의]  ※추정 방지
#   진입트리거(raw): 엔진이 신규진입을 검토하는 조건. 롱=Trend==1 & 새 피봇저점 & 직전피봇고점 존재.
#                    숏=Trend==-1 & 새 피봇고점 & 직전피봇저점 존재.  (원본 476-477 그대로)
#   무덤필터 게이트: 진입봉 oi_zscore가 [0,1) 이고 ER>=0.45 이면 진입 보류. (원본 483-499, gate_mode='er')
#   pos0봉: 그 봉 시작 시 무포지션. 엔진 거래구간 (진입,청산]을 in_pos로 칠해 그 밖이면 pos0.
#   거품: 분할A에서 미래체결을 평단에 당겨쓴 효과(엔진판 − 정직판 누적수익차).
#
# [미래참조] 엔진은 무수정. 게이트 감사는 엔진의 신호배열만 사용. 분할 거품검증은 '청산 이후 체결 제외'로
#   오히려 미래참조를 더 엄격히 제거한다(엔진보다 보수적).
# [PATH] 실행: D:\ML\verify\06Prj_Ch5_RAUTO_ConceptRefine_Stg2_GateSplitAudit\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv / Merged_Data.csv(oi_zscore_24h) / 펀딩 8h csv
# [OUTPUT] (실행폴더) audit_summary.csv + audit_gate_year.csv + audit_gate_2025m.csv
#          + audit_dec2025.csv + audit_splitA.csv + .audit_metric(check용)
# [지정 노출(승인본·이번 진단엔 미사용, 향후 페이퍼 설정값)] 추세 E=1.5, 횡보 E=10(10배정책). config로 기록만.
#
# [함수 In->Out]
#   load_engine(path,name)         경로,이름 -> 모듈객체
#   find_file(cands)               후보 -> 경로 or None
#   to_ns(t)/nfund(a_t,b_t)        시각 -> ns / 8h 펀딩횟수
#   realize_R(side,avg,exit,a_t,b_t,ft,fr) -> 현실화 R(비용0.14%+실펀딩 부호반영)
#   split_fills(d,i,close,high,low,rPH,rPL,n) -> [(가격, 체결봉j or None), ...]  (원본 분할A 복제)
#   avg_of(fills)/avg_honest(fills,exit_i)     -> 엔진평단 / 정직평단
#   main()                         전체 실행 + CSV 저장
# ==============================================================================

import os, sys, math, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
BOTS = os.path.join(HERE, "bots")

COST_RT = 0.0014        # 왕복 0.14% (Basic 표준)
GATE_ER = 0.45          # 엔진 FINAL과 동일
DZ_LO, DZ_HI = 0.0, 1.0 # 무덤구간 (엔진과 동일)
START = 10000.0
# 승인된 운영 노출(이번 진단엔 미사용 — 향후 페이퍼 설정값으로만 기록)
TREND_E = 1.5
SDCA_E = 10.0


def load_engine(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_file(cands):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def to_ns(t):
    return int(pd.Timestamp(t).value)


def nfund(a_t, b_t):
    a = to_ns(a_t) / 3.6e12; b = to_ns(b_t) / 3.6e12
    return int(math.floor(b / 8.0) - math.floor(a / 8.0))


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")

DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUNDING = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv",
                     "sample_BTCUSDT_funding_history_8h.csv"])


def realize_R(side, avg, exit_px, a_t, b_t, ft, fr):
    # 평단 avg에서 exit까지 1배 손익 - 비용0.14% - 실펀딩(부호반영). 분할 후 평단 기준.
    gross = side * (exit_px - avg) / avg
    if ft is not None:
        fs = sdca.funding_sum(ft, fr, to_ns(a_t), to_ns(b_t))
        fcost = side * fs if fs is not None else 0.0
    else:
        fcost = 0.0
    return gross - COST_RT - fcost


# ── 원본 compute_split_entry(분할A, split_n=3) 복제 + 각 체결의 '체결봉 j' 기록 ──
LEVELS = [0.382, 0.5]    # 원본: [0.382,0.5,0.618][:split_n-1], split_n=3 -> 2개


def split_fills(d, i, close, high, low, rPH, rPL, n):
    base = close[i]
    out = [(base, i)]              # 1차=신호봉 종가(항상 체결, 체결봉=i)
    lph = rPH[i]; lpl = rPL[i]
    if np.isnan(lph) or np.isnan(lpl):
        return out                 # 원본: 한쪽 피봇 nan이면 base만(전량)
    swing = lph - lpl
    for lv in LEVELS:
        if d == 1:
            target = base - lv * swing * 0.1
            hit = None
            for j in range(i + 1, min(i + 21, n)):
                if low[j] <= target:
                    hit = j; break
        else:
            target = base + lv * swing * 0.1
            hit = None
            for j in range(i + 1, min(i + 21, n)):
                if high[j] >= target:
                    hit = j; break
        if hit is not None:
            out.append((target, hit))
        else:
            out.append((base, None))   # 20봉내 미도달 -> base(원본과 동일)
    return out


def avg_of(fills):
    return float(np.mean([p for p, _ in fills]))


def avg_honest(fills, exit_i):
    # 청산봉(exit_i) 이후에야 닿은 체결은 실제 없었던 것 -> base(=첫 체결가)로 되돌림
    base = fills[0][0]; vals = [base]
    for p, j in fills[1:]:
        if j is not None and j <= exit_i:
            vals.append(p)
        else:
            vals.append(base)
    return float(np.mean(vals))


def pf(R):
    R = np.asarray(R, float)
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return round(float(gp / gl), 3) if gl > 0 else 999.0


def main():
    print("[Stg2] 게이트 감사 + 분할A 거품검증 (추세봇 원본 무수정)")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or OIPATH is None:
        pd.DataFrame([{'x': '★검증불가: 데이터/OI 파일 없음(상위 D:\\ML\\verify)'}]).to_csv(
            os.path.join(HERE, "audit_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort] 데이터 없음"); return
    print(f"[data]{DATA}\n[oi]{OIPATH}\n[funding]{FUNDING}")

    ft = fr = None; fnote = "FALLBACK(펀딩없음->비용만)"
    if FUNDING is not None:
        try:
            ft, fr = sdca.load_funding(FUNDING)
            fnote = f"REAL({os.path.basename(FUNDING)},{sdca.load_funding.n_loaded}건)"
        except Exception as e:
            fnote = f"FALLBACK({e})"

    # ── 엔진 원본 실행(Stg1과 동일 FINAL) ──
    df1m = champ.load_data(DATA)
    df_tf = champ.resample_tf(df1m, champ.TF_MIN)
    sig = champ.compute_signals(df_tf)
    oi_arr = champ.load_oi_8h(OIPATH, df_tf.index)
    bb_arr = champ.load_bb_8h(DATA, df_tf.index)
    FINAL = dict(gate_mode='er', gate_er=0.45, dz_oi=oi_arr, gate_bb=bb_arr,
                 fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    trades = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, **FINAL)
    print(f"[engine] 거래 {len(trades)}건 (Stg1과 동일해야 함)")

    idx = df_tf.index; n = len(idx)
    close = df_tf['close'].values; high = df_tf['high'].values; low = df_tf['low'].values
    er = sig['er']; Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    i_of = {t: k for k, t in enumerate(idx)}

    # 러닝 피봇값(엔진과 동일 갱신)
    rPH = np.full(n, np.nan); rPL = np.full(n, np.nan)
    lph = np.nan; lpl = np.nan
    for i in range(n):
        if i in ph_conf: lph = ph_conf[i][1]
        if i in pl_conf: lpl = pl_conf[i][1]
        rPH[i] = lph; rPL[i] = lpl

    # raw 트리거(원본 476-477 그대로)
    le_raw = np.array([(Trend[i] == 1) and (i in pl_conf) and (not np.isnan(rPH[i])) for i in range(n)])
    se_raw = np.array([(Trend[i] == -1) and (i in ph_conf) and (not np.isnan(rPL[i])) for i in range(n)])

    # 무덤필터 게이트(원본 483-499, gate_mode='er')
    z = oi_arr
    grave = (~np.isnan(z)) & (z >= DZ_LO) & (z < DZ_HI)
    is_trend = er >= GATE_ER
    blocked = grave & is_trend

    # 엔진 거래구간으로 pos0 판정
    in_pos = np.zeros(n, bool)
    entry_set = set()
    for tr in trades:
        a = i_of[tr['entry_t']]; b = i_of[tr['exit_t']]
        entry_set.add(a)
        in_pos[a + 1:b + 1] = True
    at_pos0 = ~in_pos

    # ── 로직1 검증: pos0 & 트리거 & 게이트통과 == 엔진 진입봉? ──
    trig = le_raw | se_raw
    calc_entry = set(i for i in range(n) if trig[i] and at_pos0[i] and (not blocked[i]))
    # 엔진은 청산된 거래만 목록에 담음 → 데이터 말미에 진입했으나 못 닫은 '미청산 꼬리'는 빠짐.
    # 그 1건(마지막 청산봉 이후의 진입)만 허용. 중간에 어긋나면 진짜 버그 → FAIL.
    last_exit = max((i_of[t['exit_t']] for t in trades), default=-1)
    extra = calc_entry - entry_set        # 내가 진입이라 본 봉 중 엔진목록에 없는 것
    missing = entry_set - calc_entry       # 엔진은 진입했는데 내가 못 본 것(있으면 버그)
    mid_extra = [e for e in extra if e <= last_exit]   # 말미꼬리가 아닌 중간 초과 = 진짜 버그
    tail_ok = (len(extra) <= 1) and (len(mid_extra) == 0)
    repl_ok = (len(missing) == 0) and tail_ok
    if len(extra) == 0 and len(missing) == 0:
        repl_msg = "일치(트리거+게이트+포지션 복제=엔진)"
    elif repl_ok:
        repl_msg = f"일치(말미 미청산진입 {len(extra)}건 제외, 트리거+게이트+포지션=엔진)"
    else:
        repl_msg = f"불일치 누락{len(missing)} 중간초과{len(mid_extra)}"
    print(f"[검증1] 진입재현 {repl_msg}")

    # ── 로직1 집계: 연도별 + 2025 월별 ──
    yr = idx.year.values; mo = idx.month.values
    def tally(mask_bars):
        rows = {}
        for i in np.where(mask_bars)[0]:
            if not trig[i]:
                continue
            key = (yr[i], mo[i])
            r = rows.setdefault(key, dict(long_sig=0, short_sig=0, blocked=0, entered=0, inpos=0))
            if le_raw[i]: r['long_sig'] += 1
            if se_raw[i]: r['short_sig'] += 1
            if not at_pos0[i]:
                r['inpos'] += 1
            elif blocked[i]:
                r['blocked'] += 1
            elif i in entry_set:
                r['entered'] += 1
        return rows
    allrows = tally(np.ones(n, bool))
    # 연도별
    yagg = {}
    for (Y, M), r in allrows.items():
        a = yagg.setdefault(Y, dict(long_sig=0, short_sig=0, blocked=0, entered=0, inpos=0))
        for k in a: a[k] += r[k]
    gy = pd.DataFrame([dict(year=Y, **yagg[Y]) for Y in sorted(yagg)])
    gy.to_csv(os.path.join(HERE, "audit_gate_year.csv"), index=False, encoding='utf-8-sig')
    # 2025 월별 — 항상 1~12월 고정 12행(없는 달은 0). 실데이터 견고성/빈CSV 방지.
    z0 = dict(long_sig=0, short_sig=0, blocked=0, entered=0, inpos=0)
    g25 = pd.DataFrame([dict(month=M, **allrows.get((2025, M), z0)) for M in range(1, 13)])
    g25.to_csv(os.path.join(HERE, "audit_gate_2025m.csv"), index=False, encoding='utf-8-sig')

    # ── 2025-12 숏신호 콕집기 + 그 달 거래 ──
    dec = [i for i in range(n) if yr[i] == 2025 and mo[i] == 12]
    dec_rows = []
    for i in dec:
        if se_raw[i] or le_raw[i]:
            dec_rows.append(dict(time=idx[i].strftime('%Y-%m-%d %H:%M'),
                                 sig='숏' if se_raw[i] else '롱',
                                 er=round(float(er[i]), 3), oi_z=round(float(z[i]), 3) if not np.isnan(z[i]) else None,
                                 무덤차단='Y' if (at_pos0[i] and blocked[i]) else 'N',
                                 보유중='Y' if not at_pos0[i] else 'N',
                                 진입='Y' if i in entry_set else 'N'))
    dec_trades = [dict(entry_t=tr['entry_t'].strftime('%Y-%m-%d %H:%M'), side=tr['side'],
                       R_pct=round(tr['R'] * 100, 3), reason=tr['reason'], bars=tr['bars'])
                  for tr in trades if tr['exit_t'].year == 2025 and tr['exit_t'].month == 12]
    pd.DataFrame(dec_rows if dec_rows else [{'note': '2025-12 진입트리거 0건(신호자체 미발생)'}]) \
        .to_csv(os.path.join(HERE, "audit_dec2025.csv"), index=False, encoding='utf-8-sig')

    # ── 로직2: 분할A 거품검증 ──
    rows = []; match = 0; bad = 0
    Reng = []; Rhon = []
    for tr in trades:
        i = i_of[tr['entry_t']]; ei = i_of[tr['exit_t']]; d = tr['side']
        fills = split_fills(d, i, close, high, low, rPH, rPL, n)
        a_eng = avg_of(fills)
        a_hon = avg_honest(fills, ei)
        if abs(a_eng - tr['entry']) <= max(1e-6, abs(tr['entry']) * 1e-6):
            match += 1
        else:
            bad += 1
        re_ = realize_R(d, a_eng, tr['exit'], tr['entry_t'], tr['exit_t'], ft, fr)
        rh_ = realize_R(d, a_hon, tr['exit'], tr['entry_t'], tr['exit_t'], ft, fr)
        Reng.append(re_); Rhon.append(rh_)
        lost = sum(1 for (p, j) in fills[1:] if j is not None and j > ei)
        rows.append(dict(entry_t=tr['entry_t'].strftime('%Y-%m-%d %H:%M'), side=d, year=tr['year'],
                         avg_engine=round(a_eng, 2), avg_engine_field=round(tr['entry'], 2),
                         avg_honest=round(a_hon, 2), exit=round(tr['exit'], 2),
                         R_eng_pct=round(re_ * 100, 4), R_hon_pct=round(rh_ * 100, 4),
                         fills_lost_after_exit=lost, bars=tr['bars']))
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "audit_splitA.csv"), index=False, encoding='utf-8-sig')
    cum_eng = round(sum(Reng) * 100, 1); cum_hon = round(sum(Rhon) * 100, 1)
    pf_eng = pf(Reng); pf_hon = pf(Rhon)
    bubble = round(cum_eng - cum_hon, 1)
    n_bubble = sum(1 for r in rows if r['fills_lost_after_exit'] > 0)
    match_rate = round(100 * match / max(1, len(trades)), 1)
    print(f"[검증2] 분할평단 재현일치 {match}/{len(trades)}건({match_rate}%)")
    print(f"[거품] 엔진판 cumR {cum_eng}% (PF{pf_eng}) vs 정직판 {cum_hon}% (PF{pf_hon}) -> 거품 {bubble}%p, "
          f"미래체결당김 거래 {n_bubble}건")

    # ── VERDICT + summary ──
    dec_block = sum(1 for r in dec_rows if r.get('무덤차단') == 'Y')
    dec_short = sum(1 for r in dec_rows if r.get('sig') == '숏')
    verdict = (f"VERDICT Stg2 | 펀딩={fnote} | 진입재현={repl_msg} | 분할평단재현={match_rate}% | "
               f"분할A거품: 엔진 {cum_eng}% -> 정직 {cum_hon}% (거품 {bubble}%p, 당김거래 {n_bubble}건) | "
               f"2025-12: 진입트리거 {len(dec_rows)}건(숏 {dec_short}), 무덤차단 {dec_block}건, 그달거래 {len(dec_trades)}건 | "
               f"지정노출(향후): 추세E={TREND_E} 횡보E={SDCA_E}")
    print("[verdict] " + verdict)

    out = [dict(sec=verdict)]
    out.append(dict(sec='─ 게이트 감사: 연도별 (long_sig/short_sig/blocked/entered/inpos) ─'))
    for _, r in gy.iterrows():
        out.append(dict(sec=f"  {int(r['year'])}: 롱신호{r['long_sig']} 숏신호{r['short_sig']} "
                            f"무덤차단{r['blocked']} 진입{r['entered']} 보유중트리거{r['inpos']}"))
    out.append(dict(sec='─ 2025 월별 ─'))
    for _, r in g25.iterrows():
        out.append(dict(sec=f"  {int(r['month'])}월: 롱{r['long_sig']} 숏{r['short_sig']} "
                            f"무덤차단{r['blocked']} 진입{r['entered']} 보유중{r['inpos']}"))
    pd.DataFrame(out).to_csv(os.path.join(HERE, "audit_summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".audit_metric"), "w", encoding="utf-8") as f:
        f.write(f"repl_ok={repl_ok}\nmatch_rate={match_rate}\ncum_eng={cum_eng}\ncum_hon={cum_hon}\n"
                f"bubble={bubble}\nn_bubble={n_bubble}\nfunding={fnote}\n"
                f"dec2025_trig={len(dec_rows)}\ndec2025_short={dec_short}\ndec2025_block={dec_block}\n"
                f"trend_E={TREND_E}\nsdca_E={SDCA_E}\nn_trades={len(trades)}\n")
    print("[save] audit_summary/gate_year/gate_2025m/dec2025/splitA.csv")


if __name__ == "__main__":
    main()
