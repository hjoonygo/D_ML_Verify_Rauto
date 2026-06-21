# -*- coding: utf-8 -*-
# [파일명] run_grid_D_v2.py
# 코드길이: 약 230줄, 내부버전명: GridD_v2_fast, 로직 축약/생략 없이 전체 출력
#
# [v1 -> v2 변경]
#   (1) 엔진을 Backtest_Engine_GridD_v2(독립거래 시뮬)로 교체 -> 진입 누락 없음.
#   (2) Merged_Data 슬라이스를 메모리에 1회만 로드해 8 config가 공유 -> 재로딩 제거.
#   (3) 기준 config(50:50/혁신1 ON)를 원본 TradeLog와 '거래별 1:1 자가대조' -> 재현 진단.
#
# [목적] 검증된 2.86모델의 진입 125건을 독립시뮬, 분할비율 4종 × 혁신1 2종 = 8회.
#        진입을 고정·독립으로 둬 '비율'만의 순효과 분리. 최고는 PF 아닌 DSR·PBO로.
#
# [함수 In/Out]
#   find_data_file()                 : -> Merged_Data.csv 경로
#   load_entries(path)               : -> (entry_list[(t,side,regime)], orig_net{t:net})
#   load_slice_df(src,t0,t1)         : -> tz벗긴 1분봉 DataFrame(메모리)
#   group_by_entry(trade_logs)       : -> 진입당 순익 DataFrame(key,net,진입시간)
#   run_one(exec,params,df,entries)  : 1회 독립시뮬 -> (r,g,logs,agg)
#   deflated_sharpe(...) / pbo_cscv(...) : DSR / PBO proxy
# ==============================================================================

import os, sys, math, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

try:
    from scipy.stats import norm, skew as _skew, kurtosis as _kurt
    def _ppf(p): return float(norm.ppf(p))
    def _cdf(x): return float(norm.cdf(x))
    def _sk(a): return float(_skew(a, bias=False)) if len(a) > 2 else 0.0
    def _ku(a): return float(_kurt(a, fisher=False, bias=False)) if len(a) > 3 else 3.0
except Exception:
    def _ppf(p):
        a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.3577518672690,-30.66479806614716,2.506628277459239]
        b=[-54.47609879822406,161.5858368580409,-155.6989798598866,66.80131188771972,-13.28068155288572]
        c=[-0.007784894002430293,-0.3223964580411365,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783]
        d=[0.007784695709041462,0.3224671290700398,2.445134137142996,3.754408661907416]
        pl,ph=0.02425,1-0.02425
        if p<pl: q=math.sqrt(-2*math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        if p>ph: q=math.sqrt(-2*math.log(1-p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        q=p-0.5; r=q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    def _cdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
    def _sk(a):
        a=np.asarray(a); 
        if len(a)<3: return 0.0
        s=a.std(ddof=1); return 0.0 if s==0 else float(np.mean(((a-a.mean())/s)**3))
    def _ku(a):
        a=np.asarray(a)
        if len(a)<4: return 3.0
        s=a.std(ddof=1); return 3.0 if s==0 else float(np.mean(((a-a.mean())/s)**4))

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
EULER = 0.5772156649015329
NOMINAL_PER_ENTRY = 50000.0
SPLIT_RATIOS = [0.35, 0.40, 0.45, 0.50]
INNOV1 = [True, False]
# [교정] 원본 거래기록에서 직접 추출한 실제 파라미터:
#   fib_sl_roe=3.0(하드손절 31건 전부 -3.00%), fib_ext_pct=0.65(피보락인 13건 전부 0.65), leverage=5.
#   fib_trigger_roe는 기록에 안 찍혀 코드기본 15.0로 둠 -> Pauto_Best_Params.json 있으면 거기 값으로 덮음.
BASE = {'leverage': 5, 'fib_trigger_roe': 15.0, 'fib_sl_roe': 3.0, 'fib_ext_pct': 0.65,
        'fee_rate': 0.0004, 'funding_rate_daily': 0.0001}


def calibrate_trigger(exec_cls, base, df, entries, orig, candidates=(15.0, 16.0, 17.0, 17.5, 18.0, 19.0, 20.0)):
    """잃어버린 fib_trigger_roe 1개를, 원본 거래(orig)와 거래별 차이가 최소가 되도록 복원.
       기준 config(50:50/혁신1 ON)로 후보 트리거를 돌려 |new-orig| 총합 최소를 고른다.
       (전략 최적화가 아니라 '원본을 만든 입력값 복원' = 시스템 식별)"""
    best = None
    print("[보정] fib_trigger_roe 복원 — 원본 거래와 매칭 최적값 탐색:")
    for trg in candidates:
        p = dict(base); p['split_ratio'] = 0.5; p['innovation1'] = True; p['fib_trigger_roe'] = trg
        _, g, _, agg = run_one(exec_cls, p, df, entries)
        gt = g.set_index(pd.to_datetime(g['key']))['net'] if len(g) else pd.Series(dtype=float)
        tot = 0.0; cnt = 0
        for t, net in gt.items():
            if t in orig:
                tot += abs(net - orig[t]); cnt += 1
        score = tot / max(cnt, 1)
        print(f"   trigger={trg:>5}: PF={agg['pf']:.3f} 순익={agg['net_sum']:,.0f}$ | 거래별 평균오차={score:,.1f}$")
        if best is None or score < best[1]:
            best = (trg, score)
    print(f"   -> 복원된 fib_trigger_roe = {best[0]} (평균오차 최소 {best[1]:,.1f}$)")
    return best[0]


def find_data_file():
    for d in [WORK_DIR, os.path.dirname(WORK_DIR), r"D:\ML\Verify"]:
        for n in ["Merged_Data.csv", "Merged_data.csv", "merged_data.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p): return p
    raise FileNotFoundError("Merged_Data.csv 를 상위 D:\\ML\\Verify 에 두세요.")


def load_entries(path):
    df = pd.read_csv(path)
    df['진입시간'] = pd.to_datetime(df['진입시간'])
    entry_list, orig = [], {}
    for _, r in df.iterrows():
        t = r['진입시간']
        entry_list.append((t, str(r['side']).upper(), str(r.get('regime', 'N/A'))))
        if 'orig_net' in df.columns:
            orig[t] = float(r['orig_net'])
    return entry_list, orig


def load_slice_df(src, t0, t1):
    df = pd.read_csv(src, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)  # Merged_Data(UTC) vs 진입시간(tz없음) 통일
    sub = df.loc[(df.index >= t0) & (df.index <= t1)].copy()
    return sub


def group_by_entry(trade_logs):
    if not trade_logs:
        return pd.DataFrame(columns=['key', 'net', '진입시간'])
    d = pd.DataFrame(trade_logs)
    d['key'] = d['진입시간'].astype(str)
    g = d.groupby('key')['순수익금($)'].sum().reset_index().rename(columns={'순수익금($)': 'net'})
    g['진입시간'] = pd.to_datetime(g['key'])
    return g.sort_values('진입시간').reset_index(drop=True)


def run_one(exec_cls, params, df, entries):
    from Backtest_Engine_GridD_v2 import Backtest_Engine_GridD_v2
    eng = Backtest_Engine_GridD_v2(exec_cls(), params, df)
    eng.run_entries(entries)
    logs = eng.get_trades()
    g = group_by_entry(logs)
    net = g['net'].values if len(g) else np.array([])
    wins = net[net > 0].sum() if len(net) else 0.0
    loss = net[net < 0].sum() if len(net) else 0.0
    pf = (wins / abs(loss)) if loss != 0 else float('inf')
    r = net / NOMINAL_PER_ENTRY if len(net) else np.array([])
    sr = float(r.mean() / r.std(ddof=1)) if len(r) > 1 and r.std(ddof=1) > 0 else 0.0
    agg = {'entries': len(g), 'net_sum': float(net.sum()) if len(net) else 0.0, 'pf': pf,
           'win_rate': float((net > 0).mean() * 100) if len(net) else 0.0,
           'sharpe': sr, 'skew': _sk(r), 'kurt': _ku(r)}
    return r, g, logs, agg


def deflated_sharpe(sr, sr_list, T, skew, kurt):
    if T < 3: return float('nan')
    N = len(sr_list); var_sr = float(np.var(sr_list, ddof=1)) if N > 1 else 0.0
    if var_sr <= 0:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(var_sr) * ((1 - EULER) * _ppf(1 - 1.0/N) + EULER * _ppf(1 - 1.0/(N*math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew*sr + ((kurt-1)/4.0)*(sr**2)))
    return float(_cdf((sr - sr0) * math.sqrt(T - 1) / denom))


def pbo_cscv(R, n_blocks=8):
    R = np.asarray(R); n_entries, n_cfg = R.shape
    if n_entries < n_blocks or n_cfg < 2: return float('nan')
    blocks = [b for b in np.array_split(np.arange(n_entries), n_blocks) if len(b) > 0]
    nb = len(blocks); half = nb // 2; below = 0; total = 0
    for combo in itertools.combinations(range(nb), half):
        tr = np.concatenate([blocks[b] for b in combo])
        te = np.concatenate([blocks[b] for b in range(nb) if b not in combo])
        best = int(np.argmax(R[tr].mean(axis=0)))
        oos = R[te].mean(axis=0)
        omega = (oos < oos[best]).sum() / (n_cfg - 1)
        below += 1 if omega < 0.5 else 0; total += 1
    return float(below / total) if total else float('nan')


def main():
    print("=" * 68)
    print("[단계 D — 분할익절 비율 그리드 (독립시뮬 고속판) | GridD_v2_fast]")
    print("=" * 68)
    data = find_data_file(); print(f"[데이터] {data}")
    if os.path.exists(os.path.join(WORK_DIR, "Pauto_Best_Params.json")):
        print("[주의] Pauto_Best_Params.json 발견 — 그러나 이 파일은 2.864 거래기록과 불일치"
              "(레버8/손절6.0/락인0.5 vs 실제 5/3.0/0.65, 저장도 거래 1시간 뒤)라 사용하지 않음.")
    base = dict(BASE)   # 거래기록에서 추출한 실제값: lev5 / sl3.0 / ext0.65
    entries, orig = load_entries(os.path.join(WORK_DIR, "entries_fixed.csv"))
    ts = sorted([e[0] for e in entries])
    t0 = ts[0] - pd.Timedelta(days=2); t1 = ts[-1] + pd.Timedelta(days=90)
    print(f"[슬라이스 로드] {t0.date()} ~ {t1.date()} ...")
    df = load_slice_df(data, t0, t1)
    print(f"[슬라이스] {len(df):,}행 | 고정진입 {len(entries)}건 (메모리 1회 로드, 8 config 공유)")

    from Exec_Dynamic_TS_GridD_v1 import Exec_Dynamic_TS_GridD_v1
    # 잃어버린 trigger 1개를 원본 거래와 매칭 최적값으로 복원
    if orig:
        base['fib_trigger_roe'] = calibrate_trigger(Exec_Dynamic_TS_GridD_v1, base, df, entries, orig)
    print(f"[확정 파라미터] leverage={base['leverage']} fib_sl_roe={base['fib_sl_roe']} "
          f"fib_ext_pct={base['fib_ext_pct']} fib_trigger_roe={base['fib_trigger_roe']}")

    rows = []; sr_list = []; detail = {}; R_cols = []; key_order = None; base_logs = None
    print("\n[실행] 8 config (독립시뮬) ...")
    for inv in INNOV1:
        for sr_ratio in SPLIT_RATIOS:
            p = dict(base); p['split_ratio'] = sr_ratio; p['innovation1'] = inv
            tag = f"{int(sr_ratio*100)}_{100-int(sr_ratio*100)}_inv{'ON' if inv else 'OFF'}"
            r, g, logs, agg = run_one(Exec_Dynamic_TS_GridD_v1, p, df, entries)
            pd.DataFrame(logs).to_csv(os.path.join(WORK_DIR, f"GridD_trades_{tag}.csv"), index=False, encoding='utf-8-sig')
            sr_list.append(agg['sharpe']); detail[tag] = (g, agg)
            rows.append({'config': tag, 'split': f"{int(sr_ratio*100)}:{100-int(sr_ratio*100)}", '혁신1': 'ON' if inv else 'OFF', **agg})
            if key_order is None and len(g): key_order = list(g['key'])
            if len(g): R_cols.append(g.set_index('key').reindex(key_order)['net'].fillna(0).values)
            if tag == "50_50_invON": base_logs = logs
            print(f"  {tag:>16s}: 진입{agg['entries']:3d}  PF={agg['pf']:.3f}  승률={agg['win_rate']:.1f}%  순익={agg['net_sum']:,.0f}$  Sharpe={agg['sharpe']:.3f}")

    for row in rows:
        g, agg = detail[row['config']]
        row['DSR'] = deflated_sharpe(agg['sharpe'], sr_list, agg['entries'], agg['skew'], agg['kurt'])
    pbo = pbo_cscv(np.array(R_cols).T) if len(R_cols) == len(rows) and key_order else float('nan')

    summary = pd.DataFrame(rows)[['config','split','혁신1','entries','pf','win_rate','net_sum','sharpe','DSR']]
    summary = summary.rename(columns={'pf':'PF','win_rate':'승률%','net_sum':'순익$','sharpe':'Sharpe'})
    summary.to_csv(os.path.join(WORK_DIR, "GridD_summary.csv"), index=False, encoding='utf-8-sig')

    # ---- 재현 자가검증 (기준 config) + 거래별 1:1 대조 ----
    print("\n" + "=" * 68)
    print("[재현 자가검증] config 50:50 / 혁신1 ON (= 원본 수익난모델 설정)")
    base = summary[summary['config'] == "50_50_invON"]
    if len(base):
        b = base.iloc[0]
        print(f"  진입 {int(b['entries'])}건 (목표 125)   PF={b['PF']:.3f} (목표≈2.864)   순익={b['순익$']:,.0f}$ (목표≈+15,712$)")
    if base_logs and orig:
        gb = group_by_entry(base_logs); gb['t'] = pd.to_datetime(gb['key'])
        match = 0; close = 0; tot = 0
        for _, rr in gb.iterrows():
            ot = rr['t']
            if ot in orig:
                tot += 1
                diff = abs(rr['net'] - orig[ot])
                if diff < 1.0: match += 1
                elif diff < abs(orig[ot]) * 0.05 + 5: close += 1
        print(f"  [거래별 대조] 원본과 매칭된 진입 {tot}/125 | 순익 거의일치 {match} | 5%내근사 {close} | 차이큼 {tot-match-close}")
        print(f"  -> 매칭 125 & 거의일치 다수면 '충실 재현'. 매칭<125면 그 진입은 데이터/시점 점검.")
    print("=" * 68)
    print("\n[그리드 요약표]")
    print(summary.to_string(index=False))
    print(f"\n[PBO proxy] {pbo:.3f}  (낮을수록 좋음. 8config 경량검사 — 본 PBO/CPCV는 단계 C)")
    print("[저장] GridD_summary.csv + GridD_trades_*.csv")
    print("\n[해석] 최고 비율은 PF만 보지 말고 'DSR 높고 PBO 낮은' 것. 혁신1 ON/OFF로 눌림목재설정 효과 확인.")


if __name__ == "__main__":
    main()
