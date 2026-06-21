# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch4_SidewayDCA4RAUTO_Stg1.py
# 코드길이: 약 430줄 | 내부버전: ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg1 | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세선수(SpTrd_Fib)의 268거래 원장(sfstg8_trades.csv)에, 각 거래가 '진입한 시각'의
#   장세신호 3종(OI z, ADX, BB폭)을 데이터에서 찾아 붙인다(사후 매칭). 그런 다음
#   "손실 거래들이 OI급증/약한추세와 겹쳤나, 그 거래를 미리 안 쳤으면 손실을 피했나"를
#   8개 시나리오로 측정한다. ★봇을 새로 만드는 게 아니라, 끝난 거래에 신호를 매칭하는 '모의 측정'이다.
#   (방법론 TIL 1-2: 모의는 '방향'만 알려준다 → 효과 보이면 다음 사이클에서 실제 봇으로 재백테스트.)
#
# [★사용명칭 정의]  ※추정 방지 위해 명시
#   장세전환 스위치 = "지금 추세선수를 빼야 하나?"를 판정하는 신호. 이 코드가 후보를 측정.
#   OI z (oi_zscore_24h) = 24시간 OI가 평소대비 몇σ. 양수 크면 군중쏠림(전환 임박 의심) = 선행 후보.
#   ADX = 추세 강도(방향 무관). 낮으면 추세약함=횡보. 후행지표(추세 꺾인 뒤 알려줌).
#   BB폭 (bb_width_pct) = 볼린저밴드 폭 백분위. 변동성 압축/확장. 후행.
#   2층 = OI(선행)가 경보 → ADX(후행)가 확인 → 그때 차단. 거짓경보·지연을 서로 보완.
#   차단(block) = 그 추세거래를 '안 쳤다 치고' 손익에서 제외 = 횡보선수로 스위칭했다는 의미.
#
# [미래참조 차단 — Basic 3.4 준수]
#   - 거래 '진입 시각(entry_t)'의 OI/ADX/BB값만 매칭. 그 시점에 이미 아는 값(과거 24h·과거봉 기반).
#   - label_smc(정답라벨)는 채점·차단 어디에도 안 씀(미래참조라 금지).
#   - 청산 후 가격/지표는 보지 않는다. 차단 판정은 오직 진입시각 신호로만.
#   - 매칭은 '진입시각 이하의 가장 최근 데이터 행'(asof, backward) → 미래봉 안 봄.
#
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg1\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (동봉) sfstg8_trades.csv  ← 추세선수 268거래 (이 폴더 안)
#        (상위) Merged_Data.csv 또는 merged_data.csv  ← oi_zscore_24h (없으면 OI 시나리오 비활성+경고)
#        (상위) Merged_Data_with_Regime_Features.csv  ← adx, bb_width_pct, atr_ratio, ema20_slope
# [OUTPUT] (실행폴더) rs_summary.csv + rs_matched_trades.csv + rs_scenarios.csv  -> check.py 정리.
# [SPEED] 157만행 전체를 도는 대신, 268 진입시각만 searchsorted로 매칭(asof). 컬럼은 usecols로 3~4개만 읽음.
#         8시나리오는 매칭 끝난 268행 배열에서만 계산(가볍다). 수 초 내 완료.
#
# [사용 파일]
#   IN : (이 폴더) sfstg8_trades.csv
#        (상위)   Merged_Data.csv / merged_data.csv   (oi_zscore_24h)
#        (상위)   Merged_Data_with_Regime_Features.csv (adx/bb_width_pct/atr_ratio/ema20_slope)
#   OUT: (실행폴더) rs_summary.csv / rs_matched_trades.csv / rs_scenarios.csv
#        (실행폴더) .rs_metric  (check.py가 읽는 측정 증빙: 매칭율·OI유무 등)
#
# [함수 In->Out]
#   find_trades()                  (없음) -> 추세거래 csv 경로(이 폴더 우선)
#   find_oi()                      (없음) -> oi_zscore_24h 든 csv 경로 또는 None
#   find_regime()                  (없음) -> adx/bb 든 csv 경로 또는 None
#   load_trades(path)              csv경로 -> 거래 DataFrame(entry_t 파싱·정렬)
#   asof_match(t_ns, src_ns, col)  진입시각ns,소스시각ns,값 -> 각 진입시각 이하 최근값 배열(backward)
#   load_signal(path, col)         csv경로,컬럼 -> (시각ns 배열, 값 배열)  ※usecols로 가볍게
#   agg_block(R, blocked)          거래수익,차단마스크 -> 차단후 잔여거래 통계(PF/누적R/거래수/회피손익)
#   perm_test(R, blocked, n_iter)  수익,차단마스크,반복 -> 차단효과가 우연일 확률 p값
#   main()                         전체 실행 + 8시나리오 + CSV 3종
#
# [상태/주요변수]
#   tr            : 268거래 DataFrame (side,entry_t,exit_t,year,R_pct,reason,bars)
#   oi_z/adx/bbw  : 각 거래 진입시각에 매칭된 신호 배열 (길이 268, 못 맞추면 NaN)
#   blocked       : 시나리오별 차단 마스크 (True=그 거래 안 침=횡보선수로 스위칭)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── 설정(전부 명시: 추정 방지) ──
TRADES_NAME   = "sfstg8_trades.csv"          # 동봉(이 폴더)
OI_CANDS      = ["Merged_Data.csv", "merged_data.csv", "merged_data_sample.csv"]
REGIME_CANDS  = ["Merged_Data_with_Regime_Features.csv", "merged_data.csv"]

# 시나리오4 OI 임계 그리드: stg7의 0.5단위를 유지하되 ★범위를 1.0 위로 확장(-1~3, 8점).
#   stg7 실수(1.0이 그리드 끝이라 봉우리/끝 구분 불가)를 차단. + 연속 누적곡선 별도 출력.
OI_Z_GRID     = [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
# 시나리오2 ADX 임계(이하면 추세약함=차단). SpTrd는 adx_hi 게이트를 썼으므로 그 근방 스윕.
ADX_GRID      = [18.0, 20.0, 22.0, 25.0]
# 2층(시나리오3) 기본 결합: OI z>=OI_Z_2L 이고 ADX<=ADX_2L 이면 차단(둘 다 만족 시).
OI_Z_2L       = 1.0
ADX_2L        = 22.0
# persistence(시나리오6): 표시는 개념. 거래원장 단위라 '연속 N거래 신호지속'으로 근사.
PERSIST_GRID  = [1, 2, 3]
PERM_ITER     = 5000                          # 순열검정 반복(시나리오8)
NOTIONAL      = 2.5                            # 복리 노출배수(Basic 환경). 누적R 환산 참고용.

np.random.seed(20260531)                      # 순열검정 재현성 고정


def find_trades():
    p = os.path.join(HERE, TRADES_NAME)
    if os.path.exists(p):
        return p
    for d in [PARENT, r"D:\ML\verify", r"D:\ML\Verify"]:
        q = os.path.join(d, TRADES_NAME)
        if os.path.exists(q):
            return q
    raise FileNotFoundError(f"{TRADES_NAME} 없음(이 폴더 또는 상위 D:\\ML\\verify)")


def _find_with_col(cands, col):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                try:
                    h = pd.read_csv(p, nrows=1)
                    if col in h.columns:
                        return p
                except Exception:
                    pass
    return None


def find_oi():
    return _find_with_col(OI_CANDS, "oi_zscore_24h")


def find_regime():
    return _find_with_col(REGIME_CANDS, "adx")


def load_trades(path):
    t = pd.read_csv(path, encoding="utf-8-sig")
    t["entry_t"] = pd.to_datetime(t["entry_t"], format="ISO8601", errors="coerce")
    if getattr(t["entry_t"].dt, "tz", None) is not None:
        t["entry_t"] = t["entry_t"].dt.tz_localize(None)
    t = t.dropna(subset=["entry_t"]).sort_values("entry_t").reset_index(drop=True)
    return t


def load_signal(path, col):
    # timestamp + col 두 컬럼만 읽어 가볍게. 시각 오름차순 정렬해 반환.
    df = pd.read_csv(path, usecols=["timestamp", col])
    ts = pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    ok = ts.notna() & pd.to_numeric(df[col], errors="coerce").notna()
    ts = ts[ok].values.astype("datetime64[ns]").astype("int64")
    val = pd.to_numeric(df[col], errors="coerce")[ok].values.astype("float64")
    order = np.argsort(ts)
    return ts[order], val[order]


def asof_match(t_ns, src_ns, src_val):
    # 각 진입시각 t에 대해, src에서 t 이하(과거)의 가장 최근 값을 가져온다(backward asof).
    #   ★미래참조 차단의 핵심: t보다 미래의 행은 절대 보지 않는다.
    idx = np.searchsorted(src_ns, t_ns, side="right") - 1   # t 이하 마지막 인덱스
    out = np.full(len(t_ns), np.nan)
    valid = idx >= 0
    out[valid] = src_val[idx[valid]]
    return out


def agg_block(R, blocked):
    # blocked=True인 거래는 '안 침'(횡보선수로 스위칭). 잔여 거래(추세선수가 실제 친 것)의 통계.
    kept = R[~blocked]
    avoided = R[blocked]                          # 차단된 거래들의 손익(이걸 피한 것)
    if len(kept) == 0:
        return dict(trades=0, win_pct=0.0, cumR_pct=0.0, PF=0.0,
                    blocked_n=int(blocked.sum()), avoided_cumR=round(float(avoided.sum()), 2),
                    avoided_loss=round(float(avoided[avoided < 0].sum()), 2),
                    avoided_win=round(float(avoided[avoided > 0].sum()), 2))
    wins = kept[kept > 0]; losses = kept[kept < 0]
    gp = wins.sum(); gl = -losses.sum()
    pf = (gp / gl) if gl > 0 else 999.0
    return dict(
        trades=int(len(kept)),
        win_pct=round(100.0 * len(wins) / len(kept), 1),
        cumR_pct=round(float(kept.sum()), 2),
        PF=round(float(pf), 3),
        blocked_n=int(blocked.sum()),
        avoided_cumR=round(float(avoided.sum()), 2),          # 차단으로 피한 순손익(음수면 손실 회피=좋음)
        avoided_loss=round(float(avoided[avoided < 0].sum()), 2),  # 피한 손실(클수록 좋음)
        avoided_win=round(float(avoided[avoided > 0].sum()), 2),   # 잘못 막은 이익(0에 가까울수록 좋음)
    )


def perm_test(R, blocked, n_iter):
    # 귀무가설: 차단이 무작위였다면 '피한 평균손익'이 이만큼 좋게 나올 확률은?
    #   실제 차단의 avoided 평균 vs 같은 개수를 무작위로 막았을 때의 분포 비교.
    nb = int(blocked.sum())
    if nb == 0 or nb >= len(R):
        return 1.0
    actual = R[blocked].mean()        # 실제 차단된 거래들의 평균수익(음수 클수록 손실 잘 막음)
    n = len(R); cnt = 0
    for _ in range(n_iter):
        idx = np.random.choice(n, nb, replace=False)
        if R[idx].mean() <= actual:   # 무작위가 실제만큼(또는 더) 손실을 막은 경우
            cnt += 1
    return round((cnt + 1) / (n_iter + 1), 4)   # +1 보정(p값 0 방지)


def main():
    print("[ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg1] 추세거래×장세신호 매칭 — OI 2층 스위치 8시나리오 측정")
    open(os.path.join(HERE, ".run_start"), "w").close()

    # ── 1) 추세거래 로드 ──
    tpath = find_trades()
    tr = load_trades(tpath)
    R = tr["R_pct"].values.astype("float64")
    n_tr = len(tr)
    t_ns = tr["entry_t"].values.astype("datetime64[ns]").astype("int64")
    print(f"[trades] {tpath} | {n_tr}거래 | {tr['entry_t'].min().date()}~{tr['entry_t'].max().date()}")
    base_cumR = round(float(R.sum()), 2)
    base_loss = round(float(R[R < 0].sum()), 2)
    is_flip = (tr["reason"].values == "trend_flip")
    flip_cumR = round(float(R[is_flip].sum()), 2)
    print(f"[base] 무차단 누적R={base_cumR}% | 총손실={base_loss}% | trend_flip {int(is_flip.sum())}건 {flip_cumR}%")

    # ── 2) 장세신호 매칭(진입시각 이하 최근값, 미래참조 없음) ──
    oipath = find_oi(); regpath = find_regime()
    has_oi = oipath is not None
    has_reg = regpath is not None
    oi_z = np.full(n_tr, np.nan); adx = np.full(n_tr, np.nan); bbw = np.full(n_tr, np.nan)
    oi_note = "★oi_zscore 없음 → OI 시나리오 비활성"
    reg_note = "★regime(adx) 없음 → ADX/BB 시나리오 비활성"
    if has_oi:
        s_ns, s_v = load_signal(oipath, "oi_zscore_24h")
        oi_z = asof_match(t_ns, s_ns, s_v)
        oi_note = f"oi_zscore 매칭 {int(np.isfinite(oi_z).sum())}/{n_tr}건 (src={os.path.basename(oipath)})"
    if has_reg:
        a_ns, a_v = load_signal(regpath, "adx")
        adx = asof_match(t_ns, a_ns, a_v)
        try:
            b_ns, b_v = load_signal(regpath, "bb_width_pct")
            bbw = asof_match(t_ns, b_ns, b_v)
        except Exception:
            pass
        reg_note = f"adx 매칭 {int(np.isfinite(adx).sum())}/{n_tr}건 (src={os.path.basename(regpath)})"
    print(f"[match] {oi_note} | {reg_note}")

    rows = []

    def add_row(cell, st, extra=""):
        rows.append({"cell": cell, "blocked_n": st["blocked_n"], "kept_trades": st["trades"],
                     "kept_PF": st["PF"], "kept_cumR": st["cumR_pct"], "kept_win": st["win_pct"],
                     "avoided_cumR": st["avoided_cumR"], "avoided_loss": st["avoided_loss"],
                     "avoided_win": st["avoided_win"], "note": extra})

    # 기준선(무차단) = 추세선수 그대로
    st0 = agg_block(R, np.zeros(n_tr, bool))
    add_row("BASE_무차단(추세선수 원본)", st0, f"trend_flip {int(is_flip.sum())}건 {flip_cumR}%")

    # ── 시나리오1: OI 단독 차단 (z>=임계면 그 거래 안 침) ──
    if has_oi:
        bl = np.isfinite(oi_z) & (oi_z >= OI_Z_2L)
        st = agg_block(R, bl); p = perm_test(R, bl, PERM_ITER)
        add_row(f"S1_OI단독(z>={OI_Z_2L})", st, f"우연확률 p={p}")
    else:
        rows.append({"cell": "S1_OI단독 ★불가(oi_zscore없음)", "blocked_n": "", "kept_trades": "",
                     "kept_PF": "", "kept_cumR": "", "kept_win": "", "avoided_cumR": "",
                     "avoided_loss": "", "avoided_win": "", "note": "Merged_Data.csv 확인"})

    # ── 시나리오2: ADX 단독 차단 (adx<=임계면 추세약함=차단) ──
    if has_reg:
        for ax in ADX_GRID:
            bl = np.isfinite(adx) & (adx <= ax)
            st = agg_block(R, bl)
            add_row(f"S2_ADX단독(adx<={ax})", st)
    else:
        rows.append({"cell": "S2_ADX단독 ★불가(adx없음)", "blocked_n": "", "kept_trades": "",
                     "kept_PF": "", "kept_cumR": "", "kept_win": "", "avoided_cumR": "",
                     "avoided_loss": "", "avoided_win": "", "note": "Regime_Features.csv 확인"})

    # ── 시나리오3: 2층 (OI 경보 AND ADX 확인) — ★핵심 ──
    if has_oi and has_reg:
        bl = (np.isfinite(oi_z) & (oi_z >= OI_Z_2L)) & (np.isfinite(adx) & (adx <= ADX_2L))
        st = agg_block(R, bl); p = perm_test(R, bl, PERM_ITER)
        add_row(f"S3_2층(OIz>={OI_Z_2L} AND adx<={ADX_2L})", st, f"우연확률 p={p}")
    else:
        rows.append({"cell": "S3_2층 ★불가(OI또는ADX없음)", "blocked_n": "", "kept_trades": "",
                     "kept_PF": "", "kept_cumR": "", "kept_win": "", "avoided_cumR": "",
                     "avoided_loss": "", "avoided_win": "", "note": "두 파일 다 필요"})

    # ── 시나리오4: OI 임계 스윕 (범위 -1~3, 8점) + 표본수 경고 ──
    if has_oi:
        for z in OI_Z_GRID:
            bl = np.isfinite(oi_z) & (oi_z >= z)
            st = agg_block(R, bl)
            warn = "표본부족(차단<5건)" if st["blocked_n"] < 5 else ""
            add_row(f"S4_OI임계_{z}", st, warn)

    # ── 시나리오5: 선행성 시차 — OI경보 시점 vs ADX약화 시점, 어느 게 먼저? ──
    #   거래 단위 근사: 각 거래에서 'OI가 이미 급증(z>=1)인데 ADX는 아직 강(adx>22)'인 비율.
    #   이 비율이 높으면 OI가 ADX보다 먼저 경보 = 선행성 증거.
    if has_oi and has_reg:
        oi_hot = np.isfinite(oi_z) & (oi_z >= OI_Z_2L)
        adx_strong = np.isfinite(adx) & (adx > ADX_2L)
        lead = oi_hot & adx_strong                 # OI는 경보, ADX는 아직 추세강함 = OI 선행
        n_valid = int((np.isfinite(oi_z) & np.isfinite(adx)).sum())
        lead_pct = round(100.0 * int(lead.sum()) / n_valid, 1) if n_valid else 0.0
        # 그 'OI선행' 거래들이 실제로 손실이었나(=조기경보가 맞았나)
        lead_R = round(float(R[lead].sum()), 2) if lead.any() else 0.0
        rows.append({"cell": "S5_선행성(OI경보&ADX아직강)", "blocked_n": int(lead.sum()),
                     "kept_trades": n_valid, "kept_PF": "", "kept_cumR": "", "kept_win": "",
                     "avoided_cumR": lead_R, "avoided_loss": "", "avoided_win": "",
                     "note": f"OI선행비율 {lead_pct}% (이 거래들 누적R {lead_R}%, 음수면 조기경보 적중)"})

    # ── 시나리오6: persistence — 연속 N거래 신호지속 시에만 차단(휩소 방지 근사) ──
    if has_oi:
        oi_hot = (np.isfinite(oi_z) & (oi_z >= OI_Z_2L)).astype(int)
        for N in PERSIST_GRID:
            # 직전 N거래가 연속으로 oi_hot일 때만 차단(노이즈 1회성 경보 무시)
            bl = np.zeros(n_tr, bool)
            run = 0
            for i in range(n_tr):
                run = run + 1 if oi_hot[i] == 1 else 0
                if run >= N:
                    bl[i] = True
            st = agg_block(R, bl)
            add_row(f"S6_persist_{N}거래연속", st)

    # ── 시나리오7: 수익보존 — 차단이 좋은 추세거래를 죽이진 않나(2층 기준) ──
    if has_oi and has_reg:
        bl = (np.isfinite(oi_z) & (oi_z >= OI_Z_2L)) & (np.isfinite(adx) & (adx <= ADX_2L))
        avoided_win = round(float(R[bl][R[bl] > 0].sum()), 2) if bl.any() else 0.0
        avoided_loss = round(float(R[bl][R[bl] < 0].sum()), 2) if bl.any() else 0.0
        # 좋은거래 보존 점수: 피한 손실이 잘못막은 이익보다 클수록 좋음(음수 손실 vs 양수 이익)
        net = round(avoided_loss + avoided_win, 2) if bl.any() else 0.0   # 음수면 순손실회피=이득
        rows.append({"cell": "S7_수익보존(2층 차단의 질)", "blocked_n": int(bl.sum()),
                     "kept_trades": int((~bl).sum()), "kept_PF": "", "kept_cumR": "", "kept_win": "",
                     "avoided_cumR": net, "avoided_loss": avoided_loss, "avoided_win": avoided_win,
                     "note": "avoided_loss(피한손실)가 avoided_win(잘못막은이익)보다 커야 가치있음"})

    # ── 시나리오8: 순열검정 — 2층 차단효과가 우연일 확률 ──
    if has_oi and has_reg:
        bl = (np.isfinite(oi_z) & (oi_z >= OI_Z_2L)) & (np.isfinite(adx) & (adx <= ADX_2L))
        p = perm_test(R, bl, PERM_ITER)
        verdict_p = "유의(p<0.05)" if p < 0.05 else ("약함(0.05~0.1)" if p < 0.1 else "우연가능(p>=0.1)")
        rows.append({"cell": "S8_순열검정(2층)", "blocked_n": int(bl.sum()),
                     "kept_trades": "", "kept_PF": "", "kept_cumR": "", "kept_win": "",
                     "avoided_cumR": "", "avoided_loss": "", "avoided_win": "",
                     "note": f"p={p} {verdict_p} (반복{PERM_ITER}회)"})

    # ── 연속 누적곡선(시나리오4 보강): z 정렬 후 'z 이상' 누적손익을 매끄럽게 ──
    curve_note = ""
    if has_oi:
        valid = np.isfinite(oi_z)
        zv = oi_z[valid]; rv = R[valid]
        order = np.argsort(-zv)                 # z 높은 것부터
        zs = zv[order]; rs = rv[order]
        cum = np.cumsum(rs)                      # z>=zs[k] 인 거래들의 누적손익
        # 곡선이 꺾이는(누적이 음→양 전환) z 지점 찾기 = 차단가치 한계
        knee = None
        for k in range(1, len(cum)):
            if cum[k - 1] < 0 <= cum[k]:
                knee = round(float(zs[k]), 2); break
        curve_note = f"누적곡선 꺾임 z≈{knee}" if knee is not None else "누적곡선 단조(꺾임없음)"

    # ── VERDICT ──
    s3 = next((r for r in rows if str(r["cell"]).startswith("S3_2층(")), None)
    s8 = next((r for r in rows if str(r["cell"]).startswith("S8_")), None)
    if s3 and isinstance(s3.get("avoided_loss"), (int, float)):
        v_core = (f"2층 차단 {s3['blocked_n']}건 → 피한손실 {s3['avoided_loss']}% "
                  f"잘못막은이익 {s3['avoided_win']}% | 잔여 PF {s3['kept_PF']} cumR {s3['kept_cumR']}%")
    else:
        v_core = "2층 측정불가(OI 또는 ADX 데이터 없음 — 상위 D:\\ML\\verify 확인)"
    v_p = s8["note"] if s8 else ""
    verdict = (f"VERDICT RegimeSwitch | BASE cumR {base_cumR}% (trend_flip {flip_cumR}%) | "
               f"{v_core} | {v_p} | OI {('O' if has_oi else 'X')} ADX {('O' if has_reg else 'X')} | "
               f"S4 {curve_note}")
    print("[verdict] " + verdict)

    # ── 저장(전량 파일) ──
    out = [{"cell": verdict, "blocked_n": "", "kept_trades": "", "kept_PF": "", "kept_cumR": "",
            "kept_win": "", "avoided_cumR": "", "avoided_loss": "", "avoided_win": "", "note": ""}] + rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "rs_summary.csv"), index=False, encoding="utf-8-sig")

    # 거래별 매칭값 원장
    md = pd.DataFrame({
        "entry_t": tr["entry_t"].dt.strftime("%Y-%m-%d %H:%M"),
        "side": tr["side"].values, "year": tr["year"].values, "R_pct": R,
        "reason": tr["reason"].values, "oi_z": np.round(oi_z, 3),
        "adx": np.round(adx, 2), "bb_width_pct": np.round(bbw, 4),
    })
    md.to_csv(os.path.join(HERE, "rs_matched_trades.csv"), index=False, encoding="utf-8-sig")

    # 시나리오 분해(연도×reason별 차단효과, 2층 기준)
    sc_rows = []
    if has_oi and has_reg:
        bl = (np.isfinite(oi_z) & (oi_z >= OI_Z_2L)) & (np.isfinite(adx) & (adx <= ADX_2L))
        for y in sorted(tr["year"].unique()):
            for rs_name in ["sl", "trend_flip"]:
                m = (tr["year"].values == y) & (tr["reason"].values == rs_name)
                if m.sum() == 0:
                    continue
                sc_rows.append({"cell": f"SCEN_{int(y)}_{rs_name}", "n": int(m.sum()),
                                "cumR": round(float(R[m].sum()), 2),
                                "blocked": int((m & bl).sum()),
                                "blocked_cumR": round(float(R[m & bl].sum()), 2)})
    if not sc_rows:
        sc_rows = [{"cell": "SCEN_불가(데이터없음)", "n": "", "cumR": "", "blocked": "", "blocked_cumR": ""}]
    pd.DataFrame(sc_rows).to_csv(os.path.join(HERE, "rs_scenarios.csv"), index=False, encoding="utf-8-sig")

    # check.py가 읽을 측정 증빙
    with open(os.path.join(HERE, ".rs_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trades={n_tr}\n")
        f.write(f"oi_matched={int(np.isfinite(oi_z).sum())}\n")
        f.write(f"adx_matched={int(np.isfinite(adx).sum())}\n")
        f.write(f"has_oi={int(has_oi)}\n")
        f.write(f"has_reg={int(has_reg)}\n")
        f.write(f"base_cumR={base_cumR}\n")
        f.write(f"flip_cumR={flip_cumR}\n")

    print(f"[save] rs_summary.csv + rs_matched_trades.csv + rs_scenarios.csv")


if __name__ == "__main__":
    main()
