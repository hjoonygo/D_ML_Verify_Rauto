# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg8_DualGrid.py
# 코드길이: 약 340줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg8_DualGrid | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 두 제안을 '인자 변경'과 '사후 사이징'으로만 재현해 그리드로 쓸어 비교한다.
#
#   ★제안1 (횡보봇 진입확대): run_bot_honest 가 par(nDCA)·atr_lo 를 인자로 받으므로 엔진 안 고치고
#     - A: nDCA 1 -> 2 (분할 추가매수 허용)
#     - D: atr_lo 그리드 [0.90(기본),0.85,0.80] (1차 ATR필터 완화; 낮출수록 진입 ↑)
#     - ★OI 2차필터(OI_Z_HI=1.0)는 검증된 알파라 고정 유지
#     - TF: 6h/8h(기본)/12h
#     측정: PF·수익률(ΣR%)·손익비·거래수·수익금(2.5배복리). 기준=PF 크게 안깎고 진입 최대.
#
#   ★제안2 (추세봇 POV 사이징): 추세봇 진입(눌림목)시점의 횡보봇 POV(dev=POC편차)를 별도 계산해 매칭.
#     dev<0(과매도)=롱과 방향일치 / dev>0(과매수)=롱과 반대. (숏이면 부호 반대로.)
#     - 방향일치 배수 m_agree ∈ {1,1.2,1.5,1.7,2}
#     - 방향반대 배수 m_oppo  ∈ {0.25,0.5,0.75,1}
#     ★진입 자체는 안 막음(수량만 조절) → 잭팟 보존. R_adj = R * 배수.
#     - TF: 6h/7h(기본)/8h
#     측정: 승률·손익비·PF·수익률·수익금(명목$5만 단리)·잭팟보존율(상위10% 수익거래 가중평균).
#
#   [Lookahead] dev/atr_ratio 모두 진입시점 과거기반(엔진과 동일). 사이징은 진입 후 결과에 곱하는 게 아니라
#     '진입시점 dev'로 정해지는 가중이므로 미래참조 없음. 라벨 미사용.
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg8_DualGrid\ . 데이터: 상위 D:\ML\Verify\ (4종).
# [OUTPUT] p1_sideways_grid.csv / p2_trend_pov_grid.csv / p2_best_detail.csv / summary.csv + .stg8_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
NOMINAL = champ.NOMINAL; NOTIONAL_CAP = sdca.NOTIONAL_CAP; START_CAP = champ.START_CAP


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def profit_compound(R, lev):
    cap = START_CAP
    for r in R:
        cap *= (1 + r * lev)
    return round(cap - START_CAP, 0)


def jackpot_keep(R, size, topfrac=0.10):
    # 상위 topfrac 수익거래(잭팟)에 적용된 평균 사이징(1.0이면 100% 보존)
    R = np.asarray(R); size = np.asarray(size)
    idx = np.argsort(R)[::-1][:max(1, int(len(R) * topfrac))]
    base = np.mean(np.clip(size, 0, None))
    return round(100 * float(np.mean(size[idx]) / (base if base > 0 else 1)), 1)


def main():
    print("[Stg8] 듀얼 그리드: 제안1 횡보확대 + 제안2 추세POV사이징")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            pass

    def fund_pay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0

    # ───────────────────────── 제안1: 횡보봇 진입확대 그리드 ─────────────────────────
    print("[제안1] 횡보봇 nDCA×atr_lo×TF 그리드 ...")
    p1 = []
    base_par = dict(sdca.BEST_PAR)
    s1_full = sdca.load_1m(DATA)
    for tf in [360, 480, 720]:                 # 6h / 8h(기본) / 12h
        try:
            s8 = sdca.resample_tf(s1_full, tf); ss = sdca.precompute(s8)
            s_ss, s_se = sdca.build_1m_map(s1_full, s8)
            mO = s1_full['open'].values; mH = s1_full['high'].values; mL = s1_full['low'].values
            mT = s1_full.index.values.astype('datetime64[ns]').astype('int64')
        except Exception as e:
            p1.append(dict(tf_min=tf, err=str(e)[:40])); continue
        for ndca in [1, 2]:                    # A: 분할 추가매수
            for atr_lo in [0.90, 0.85, 0.80]:  # D: ATR필터 완화 (OI필터는 고정유지)
                par = dict(base_par); par['nDCA'] = ndca
                try:
                    tr, *_ = sdca.run_bot_honest(s8, ss, par, mO, mH, mL, mT, s_ss, s_se, ft, fr,
                                                 sdca.DEFAULT_SLMULT, filter_mode='precise', atr_lo=atr_lo, atr_hi=sdca.ATR_HI,
                                                 filter_scens=sdca.FILTER_SCENS, oi_filter=True, oi_z_hi=1.0,
                                                 oi_filter_scens=sdca.OI_FILTER_SCENS)
                    R = np.array([t['R'] for t in tr])
                    m = metrics(R); m['profit_usd'] = profit_compound(R, NOTIONAL_CAP)
                    tag = "기본" if (tf == 480 and ndca == 1 and atr_lo == 0.90) else ""
                    p1.append(dict(tf=f"{tf//60}h", nDCA=ndca, atr_lo=atr_lo, base=tag, **m))
                except Exception as e:
                    p1.append(dict(tf=f"{tf//60}h", nDCA=ndca, atr_lo=atr_lo, err=str(e)[:40]))
    p1df = pd.DataFrame(p1); p1df.to_csv(os.path.join(HERE, "p1_sideways_grid.csv"), index=False, encoding='utf-8-sig')
    base1 = p1df[(p1df.get('base') == '기본')]
    base1_pf = float(base1.PF.iloc[0]) if len(base1) else 2.653
    base1_n = int(base1.n.iloc[0]) if len(base1) else 86

    # ───────────────────────── 제안2: 추세봇 POV 사이징 그리드 ─────────────────────────
    print("[제안2] 추세봇 POV(dev) 사이징 × TF 그리드 ...")
    p2 = []; best = None; best_key = None
    df1m_c = champ.load_data(DATA)
    s1_pov = sdca.load_1m(DATA)
    for tf in [360, 420, 480]:                 # 6h / 7h(기본) / 8h
        df_tf = champ.resample_tf(df1m_c, tf); sig = champ.compute_signals(df_tf)
        idx = df_tf.index; oi = champ.load_oi_8h(OIPATH, idx); bb = champ.load_bb_8h(DATA, idx)
        # 그 TF에서 추세봇 거래
        save_tf = champ.TF_MIN
        ttr = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                                 dz_oi=oi, gate_bb=bb, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
        # 같은 TF로 횡보봇 POV(POC편차 dev) 배열 만들기
        s8 = sdca.resample_tf(s1_pov, tf); ssig = sdca.precompute(s8)
        poc = ssig['poc']; atr = ssig['atr']; close8 = s8['close'].values; sidx = s8.index
        dev_arr = np.full(len(sidx), np.nan)
        for k in range(len(sidx)):
            if not np.isnan(poc[k]) and not np.isnan(atr[k]) and atr[k] > 0:
                dev_arr[k] = (close8[k] - poc[k]) / atr[k]
        # 추세봇 각 거래의 진입시점 dev 매칭(진입봉 직전 닫힌 8h봉 = 과거기반)
        base_R = []; devs = []; sides = []
        for t in ttr:
            R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
            pos = sidx.searchsorted(pd.Timestamp(t['entry_t'])) - 1
            dv = dev_arr[pos] if 0 <= pos < len(dev_arr) else np.nan
            base_R.append(R); devs.append(dv); sides.append(t['side'])
        base_R = np.array(base_R); devs = np.array(devs); sides = np.array(sides)
        # POV 동의 여부: 롱(side+1)은 dev<0(과매도)=동의 / 숏(side-1)은 dev>0(과매수)=동의
        agree = ((sides > 0) & (devs < 0)) | ((sides < 0) & (devs > 0))
        oppo = ((sides > 0) & (devs > 0)) | ((sides < 0) & (devs < 0))
        # base 성과(사이징 전)
        if tf == 420:
            bm = metrics(base_R); bm['profit_usd'] = round(float(base_R.sum() * NOMINAL), 0)
            p2_base = bm
        for ma in [1.0, 1.2, 1.5, 1.7, 2.0]:        # 방향일치 배수
            for mo in [0.25, 0.5, 0.75, 1.0]:       # 방향반대 배수
                size = np.ones(len(base_R))
                size[agree] = ma; size[oppo] = mo    # dev=NaN인 건 1 유지
                R_adj = base_R * size
                m = metrics(R_adj)
                m['profit_usd'] = round(float(R_adj.sum() * NOMINAL), 0)
                m['jack_keep'] = jackpot_keep(base_R, size)
                tag = "기본" if (tf == 420 and ma == 1.0 and mo == 1.0) else ""
                row = dict(tf=f"{tf//60}h", m_agree=ma, m_oppo=mo, base=tag,
                           n_agree=int(agree.sum()), n_oppo=int(oppo.sum()), **m)
                p2.append(row)
                score = m['ret_pct'] * (1 if m['jack_keep'] >= 85 else 0.5)  # 잭팟 깎으면 페널티
                if best is None or score > best[0]:
                    best = (score, row); best_key = (tf, ma, mo)
        champ.TF_MIN = save_tf
    p2df = pd.DataFrame(p2); p2df.to_csv(os.path.join(HERE, "p2_trend_pov_grid.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame([best[1]]).to_csv(os.path.join(HERE, "p2_best_detail.csv"), index=False, encoding='utf-8-sig')

    # ───────────────────────── 요약 ─────────────────────────
    # 제안1 best: PF가 기본의 90% 이상 유지하면서 거래수 최대
    ok1 = p1df[(p1df.get('PF', 0) >= base1_pf * 0.9) & (p1df.get('n', 0) > base1_n)] if 'PF' in p1df else pd.DataFrame()
    if len(ok1):
        b1 = ok1.sort_values('n', ascending=False).iloc[0]
        p1_best = f"{b1['tf']} nDCA{b1['nDCA']} atr_lo{b1['atr_lo']}: 거래{int(b1['n'])}(기본{base1_n}) PF{b1['PF']}(기본{base1_pf}) 수익률{b1['ret_pct']}%"
        p1_verdict = "진입확대 유효(PF유지하며 거래↑)"
    else:
        p1_best = f"PF{base1_pf*0.9:.2f} 이상 유지하며 거래 늘리는 조합 없음"
        p1_verdict = "진입확대 무효(늘리면 PF훼손)"
    bp = best[1]
    p2_verdict = ("POV사이징 유효" if (bp['ret_pct'] > p2_base['ret_pct'] and bp['jack_keep'] >= 85)
                  else "POV사이징 무효(수익↑못하거나 잭팟훼손)")
    verdict = (f"VERDICT Stg8 | [제안1] 기본 거래{base1_n}/PF{base1_pf} -> best: {p1_best} => {p1_verdict} | "
               f"[제안2] 기본(7h) 승률{p2_base['win_pct']}%/손익비{p2_base['payoff']}/수익률{p2_base['ret_pct']}%/${p2_base['profit_usd']} -> "
               f"best {best_key[0]//60}h 일치×{best_key[1]} 반대×{best_key[2]}: 승률{bp['win_pct']}%/손익비{bp['payoff']}/수익률{bp['ret_pct']}%/${bp['profit_usd']}/잭팟보존{bp['jack_keep']}% => {p2_verdict}")
    print("[verdict] " + verdict)

    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[제안1 기본] 거래{base1_n} PF{base1_pf}"),
                  dict(sec=f"[제안2 기본 7h] 승률{p2_base['win_pct']}% 손익비{p2_base['payoff']} 수익률{p2_base['ret_pct']}% ${p2_base['profit_usd']}")
                  ]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg8_metric"), "w", encoding="utf-8") as f:
        f.write(f"p1_base_n={base1_n}\np1_base_pf={base1_pf}\np1_verdict={p1_verdict}\np1_best={p1_best}\n"
                f"p2_base_win={p2_base['win_pct']}\np2_base_payoff={p2_base['payoff']}\np2_base_ret={p2_base['ret_pct']}\n"
                f"p2_base_profit={p2_base['profit_usd']}\np2_best_tf={best_key[0]//60}\np2_best_agree={best_key[1]}\n"
                f"p2_best_oppo={best_key[2]}\np2_best_win={bp['win_pct']}\np2_best_payoff={bp['payoff']}\np2_best_ret={bp['ret_pct']}\n"
                f"p2_best_profit={bp['profit_usd']}\np2_best_jack={bp['jack_keep']}\np2_verdict={p2_verdict}\n"
                f"p1_rows={len(p1df)}\np2_rows={len(p2df)}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\n")
    print("[save] p1_sideways_grid / p2_trend_pov_grid / p2_best_detail / summary.csv")


if __name__ == "__main__":
    main()
