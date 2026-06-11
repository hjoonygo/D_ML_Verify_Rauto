# -*- coding: utf-8 -*-
# [파일명] ml_test.py  (하드손절 원인 ML 분석)
# 코드길이: 약 320줄, 내부버전명: ML_hardstop_cause_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] "하드손절이 몇 가지 상황유형에서 나오는가 + 그 상황을 ML로 학습해 뽑기."
#   한 유형이라도 진입 전 거를 수 있으면 알파. 단 거를 때 피보 승자를 같이 죽이면 알파 아님
#   -> 모든 후보 필터에 대해 '하드손절 제거수 vs 승자 동반사망수' 맞교환표를 반드시 낸다.
#
# [방법] 검증된 S5 하네스(test.py)를 그대로 재사용해 백테스트를 재실행하되, 진입할 때마다
#   그 순간의 피처 벡터 + 결과 라벨(하드손절=1 / 살아남음=0)을 한 줄로 기록 -> ML.
#   알파엔진 Exec_Fibo_v3, OB모듈 ob_mtf, 하네스 test.py 모두 원본 그대로 import.
#
# [데이터] B(Merged_Data_with_Regime_Features.csv) 필수 + 같은/상위 폴더에 A(merged_data*.csv)
#   있으면 timestamp(1분·UTC) inner join 으로 OI/플로우 자동 결합. 매칭률 로그.
#
# [피처 3묶음] (1)게이트 맥락(진입전 아는값: RR·SL거리·TP거리) (2)B+A의 수치/인코딩 컬럼 자동탐색
#   (3)OHLC 직접계산(최근수익률·변동성·눌림목 위치·캔들). 가격절대값은 close대비 비율로.
#
# [모델] 지도: RandomForest(중요도) + 깊이3~4 DecisionTree(사람이 읽는 규칙)
#        비지도: KMeans(하드손절만 군집 -> '원인 N가지' 개수, K는 실루엣으로 2~6 자동선택)
#
# [결과 전량 파일] ML_importance.csv / ML_rules.txt / ML_clusters.csv /
#   ML_tradeoff.csv(★핵심) / ML_summary.txt / ML_entry_features.csv(원천)
#
# [함수 In/Out]
#   load_merged(pathB) -> (df, feat_cols, cat_map)   B필수 + A선택 결합
#   ohlc_features(df) -> dict 배열(ret/vol/pos/body)
#   collect_entries(df,...) -> DataFrame(피처 + hard/piano/net 라벨)  S5 재실행
#   ml_analyze(D, feat_cols) -> 파일들 저장
# ==============================================================================

import os, sys, glob
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test as T   # 검증된 하네스(상수·게이트·pivot·simulate_one·엔진)

S5 = dict(sid='S5_slob100_con', tp_mode='big', sl_mode='ob', clamp=0.0100, fill='con', timeout=False)
DROP_COLS = {'timestamp','open','high','low','close','close_time','ignore','quote_volume'}  # 원천/중복/plumbing


def _find(parent, names):
    for d in [parent, os.path.join(parent, '..')]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return os.path.abspath(p)
    return None


def load_merged(pathB):
    df = pd.read_csv(pathB, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    if T.REGIME_COL not in df.columns:
        raise KeyError(f"{T.REGIME_COL} 없음 — 백테스트용 B파일이 맞는지 확인")
    # A(원시 OI/플로우) 결합 시도
    pa = _find(PARENT, ['merged_data.csv', 'merged_data_sample.csv',
                        'Merged_Data.csv', 'merged_data_full.csv'])
    if pa and os.path.abspath(pa) != os.path.abspath(pathB):
        a = pd.read_csv(pa, index_col='timestamp', parse_dates=True)
        if getattr(a.index, 'tz', None) is not None:
            a.index = a.index.tz_localize(None)
        a = a.sort_index()
        addcols = [c for c in a.columns if c not in df.columns]  # 중복 OHLCV는 B 우선
        before = len(df)
        df = df.join(a[addcols], how='left')
        match = df[addcols[0]].notna().mean() * 100 if addcols else 0
        print(f"[결합] A={os.path.basename(pa)} 추가컬럼 {len(addcols)}개, 매칭률 {match:.0f}% (행 {before})")
    else:
        print("[결합] A(원시 OI/플로우) 미발견 — B 피처만 사용")
    # 피처 컬럼 선별 + 문자 라벨 인코딩
    cat_map = {}
    feat_cols = []
    for c in df.columns:
        if c in DROP_COLS or c == T.REGIME_COL:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            feat_cols.append(c)
        else:
            codes, uniq = pd.factorize(df[c].astype(str))
            df[c + '__code'] = codes
            cat_map[c + '__code'] = {i: v for i, v in enumerate(uniq)}
            feat_cols.append(c + '__code')
    return df, feat_cols, cat_map


def ohlc_features(df):
    c = df['close'].values.astype(float); h = df['high'].values; l = df['low'].values
    o = df['open'].values; n = len(c)
    def ret(k):
        r = np.full(n, np.nan); r[k:] = c[k:] / c[:-k] - 1; return r
    def vol(k):
        lr = np.zeros(n); lr[1:] = np.log(c[1:] / c[:-1])
        s = pd.Series(lr).rolling(k).std().values; return s
    def posrange(k):
        hh = pd.Series(h).rolling(k).max().values; ll = pd.Series(l).rolling(k).min().values
        return (c - ll) / (hh - ll + 1e-9)   # 0=구간 바닥, 1=구간 천장(숏 고점진입=위험)
    body = (c - o) / (h - l + 1e-9)
    return {'f_ret5': ret(5), 'f_ret15': ret(15), 'f_ret60': ret(60),
            'f_vol30': vol(30), 'f_vol60': vol(60),
            'f_posrange60': posrange(60), 'f_posrange240': posrange(240),
            'f_candlebody': body,
            'f_ema50_gap': (c / df['ema_50'].values - 1) if 'ema_50' in df.columns else np.zeros(n),
            'f_ema100_gap': (c / df['ema_100'].values - 1) if 'ema_100' in df.columns else np.zeros(n)}


def collect_entries(df):
    """S5 백테스트 재실행하며 진입마다 피처+결과 1행 기록(test.py run_cfg와 동일 골격)."""
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index; idxv = idx.values
    down_idx = np.where(df[T.REGIME_COL].astype(str).values == 'downtrend')[0]
    pv = T.prep_pivots(df)
    of = ohlc_features(df)
    sl_arr = pv['SL_big']; tp_arr = pv['TP_big']
    eng = T.Exec_Fibo_v3()
    cap = T.START_CAP; rows = []; n = len(c); cur = 0
    diag = {'sl_dist': [], 'tp_dist': [], 'rr': [], 'pass': 0, 'checked': 0, 'wait_success': 0, 'wait_timeout': 0}
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        t0 = int(down_idx[dptr])
        if t0 >= n - 1: break
        if cap <= T.MIN_CAP: break
        e_idx, gate = T.wait_entry(c, idxv, t0, sl_arr, tp_arr, diag)
        if e_idx is not None:
            tp_target = gate['tp_price']
            trows, pnl, why = T.simulate_one(eng, df, o, h, l, c, idx, e_idx, gate, cap, S5, tp_target)
            cap += pnl
            is_hard = int(any('하드손절' in str(r['청산사유']) for r in trows))
            is_piano = int(any(('락인' in str(r['청산사유'])) or ('Fibonacci' in str(r['청산사유'])) for r in trows))
            rec = {'entry_time': idx[e_idx], 'hard': is_hard, 'piano': is_piano, 'net': round(pnl, 2),
                   'g_rr': gate['rr'], 'g_sl_dist': gate['sl_dist'], 'g_tp_dist': gate['tp_dist']}
            for k, arr in of.items():
                rec[k] = float(arr[e_idx]) if e_idx < len(arr) else np.nan
            r0 = df.iloc[e_idx]
            for col in df.columns:
                if col.endswith('__code') or (pd.api.types.is_numeric_dtype(df[col]) and col not in DROP_COLS):
                    rec[col] = float(r0[col]) if pd.notna(r0[col]) else np.nan
            rows.append(rec)
            last_x = pd.to_datetime(trows[-1]['청산시간']); x_idx = idx.searchsorted(last_x)
            cur = max(int(x_idx) + 1, e_idx + 1)
        else:
            cur = t0 + T.WAIT_MIN + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return pd.DataFrame(rows)


def ml_analyze(D, cat_map):
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.tree import DecisionTreeClassifier, export_text
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import silhouette_score
    except ImportError:
        msg = ("[sklearn 없음] 'pip install scikit-learn' 후 다시 실행하세요.\n"
               "진입 피처는 ML_entry_features.csv 에 이미 저장됨(재실행 시 ML만 추가).")
        open(os.path.join(HERE, "ML_summary.txt"), 'w', encoding='utf-8').write(msg)
        print(msg); return

    meta = {'entry_time', 'hard', 'piano', 'net'}
    feat = [c for c in D.columns if c not in meta]
    X = D[feat].replace([np.inf, -np.inf], np.nan)
    keep = X.columns[X.notna().mean() > 0.5]      # 절반이상 결측 컬럼 제외(워밍업 등)
    feat = list(keep); X = X[feat].fillna(X[feat].median())
    y = D['hard'].values
    out = []
    out.append(f"[하드손절 원인 ML 분석]  진입 {len(D)}건 | 하드 {int(y.sum())}({y.mean()*100:.0f}%) | "
               f"피보승자 {int(D['piano'].sum())} | 사용피처 {len(feat)}개")

    if y.sum() < 5 or (y == 0).sum() < 5:
        out.append("표본 부족(한 클래스 5건 미만) — 규칙/군집 생략. 더 긴 데이터 필요.")
        open(os.path.join(HERE, "ML_summary.txt"), 'w', encoding='utf-8').write("\n".join(out))
        return

    # 1) 중요도(RandomForest)
    rf = RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=5,
                                class_weight='balanced', random_state=0).fit(X, y)
    imp = pd.DataFrame({'feature': feat, 'importance': rf.feature_importances_}).sort_values('importance', ascending=False)
    imp.to_csv(os.path.join(HERE, "ML_importance.csv"), index=False, encoding='utf-8-sig')
    out.append("\n[중요피처 TOP10]")
    for _, r in imp.head(10).iterrows():
        out.append(f"  {r['feature']:24s} {r['importance']:.3f}")

    # 2) 규칙(얕은 트리)
    dt = DecisionTreeClassifier(max_depth=4, min_samples_leaf=8, class_weight='balanced', random_state=0).fit(X, y)
    rules = export_text(dt, feature_names=feat, max_depth=4)
    open(os.path.join(HERE, "ML_rules.txt"), 'w', encoding='utf-8').write(rules)
    out.append("\n[의사결정나무 규칙] -> ML_rules.txt 참조")

    # 3) 군집(하드손절만 -> 원인 몇 가지)
    Xh = X[y == 1]
    Xs = StandardScaler().fit_transform(Xh)
    bestK, bestS = 2, -1
    for k in range(2, min(7, len(Xh) // 5 + 2)):
        try:
            lab = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(Xs)
            s = silhouette_score(Xs, lab)
            if s > bestS: bestK, bestS = k, s
        except Exception:
            pass
    km = KMeans(n_clusters=bestK, n_init=10, random_state=0).fit(Xs)
    Dh = D[y == 1].copy(); Dh['cluster'] = km.labels_
    prof = Dh.groupby('cluster').agg(건수=('hard', 'size'), 평균손실=('net', 'mean')).reset_index()
    # 각 군집의 대표(중요 상위 6피처 평균)
    top6 = list(imp['feature'].head(6))
    for f in top6:
        prof[f] = Dh.groupby('cluster')[f].mean().values
    prof.to_csv(os.path.join(HERE, "ML_clusters.csv"), index=False, encoding='utf-8-sig')
    out.append(f"\n[원인 군집] 하드손절은 약 {bestK}가지 유형 (실루엣 {bestS:.2f})")
    for _, r in prof.iterrows():
        out.append(f"  유형{int(r['cluster'])}: {int(r['건수'])}건, 평균손실 {r['평균손실']:.0f}$")

    # 4) ★맞교환표: 후보필터 = 중요 상위 피처의 단일임계값(하드 분리 최대화) + 트리 잎 규칙
    out.append("\n[필터 맞교환표] -> ML_tradeoff.csv (하드제거 vs 승자동반사망)")
    rec = []
    base_hard = int(D['hard'].sum()); base_pia = int(D['piano'].sum()); base_net = D['net'].sum()
    for f in top6:
        v = X[f].values
        best = None
        for q in np.linspace(0.1, 0.9, 17):
            thr = np.quantile(v, q)
            for side in ['>=', '<']:
                mask = (v >= thr) if side == '>=' else (v < thr)   # mask=거를 진입
                if mask.sum() == 0 or mask.sum() == len(v): continue
                hr = int(D['hard'].values[mask].sum())             # 제거되는 하드
                pr = int(D['piano'].values[mask].sum())            # 동반사망 승자
                if hr == 0: continue
                score = hr - 3 * pr                                 # 승자 1=하드3 가치 가정
                if best is None or score > best[0]:
                    best = (score, f, side, round(float(thr), 5), hr, pr,
                            round(float(D['net'].values[~mask].sum() - base_net), 0))
        if best:
            rec.append(dict(피처=best[1], 조건=f"{best[2]}{best[3]}", 제거하드=best[4],
                            동반사망승자=best[5], 잔존하드=base_hard - best[4],
                            순익변화=best[6]))
    pd.DataFrame(rec).sort_values('제거하드', ascending=False).to_csv(
        os.path.join(HERE, "ML_tradeoff.csv"), index=False, encoding='utf-8-sig')
    out.append(f"  (기준: 전체 하드 {base_hard} / 승자 {base_pia})")
    for r in sorted(rec, key=lambda x: -x['제거하드'])[:6]:
        out.append(f"  {r['피처']} {r['조건']}: 하드 -{r['제거하드']} / 승자 -{r['동반사망승자']} / 순익 {r['순익변화']:+.0f}$")

    open(os.path.join(HERE, "ML_summary.txt"), 'w', encoding='utf-8').write("\n".join(out))
    print("\n".join(out))


def main():
    pb = _find(PARENT, ['Merged_Data_with_Regime_Features.csv'])
    if pb is None:
        raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")
    print(f"[B] {pb}")
    df, feat_cols, cat_map = load_merged(pb)
    print(f"[로드] {len(df):,}행, 후보피처 {len(feat_cols)}개. S5 재실행+피처로깅...")
    D = collect_entries(df)
    D.to_csv(os.path.join(HERE, "ML_entry_features.csv"), index=False, encoding='utf-8-sig')
    print(f"[진입수집] {len(D)}건 (하드 {int(D['hard'].sum())} / 피보 {int(D['piano'].sum())})")
    ml_analyze(D, cat_map)
    print("\n[저장] ML_importance/rules/clusters/tradeoff/summary + entry_features — 전량 파일")


if __name__ == "__main__":
    main()
