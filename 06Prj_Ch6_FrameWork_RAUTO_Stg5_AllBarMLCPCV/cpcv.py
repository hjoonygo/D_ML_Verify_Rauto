# -*- coding: utf-8 -*-
# [파일명] cpcv.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg5_CPCV_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]  CPCV = 조합적 제거 교차검증 (López de Prado 2018, AFML).
#   왜 필요한가: 워크포워드는 '단일 역사경로' 하나로만 채점→운에 좌우(분산 큼). CPCV는 데이터를 N그룹으로
#     나눠 k그룹을 검증으로 쓰는 모든 조합 C(N,k)을 만들어 'OOS 성능 분포'를 낸다. 더 정직하고 견고.
#   ★purging(제거): 검증그룹과 시간이 겹치는(라벨이 미래를 본) 학습표본을 도려냄 → 누수 차단.
#   ★embargo(금수): 검증그룹 직후 일정 봉을 학습서 제외 → 시장메모리(자기상관) 누수 차단.
#   표준: N=6, k=2 → C(6,2)=15분할(S1~S15). 사장님 확정값.
#
#   [핵심 출처] López de Prado, Advances in Financial Machine Learning (2018).
#               "N그룹 중 k그룹을 검증으로, purge+embargo로 누수 차단, 성능분포로 견고 추론."
#
# [In] 표본수 n, 그룹수 N, 검증그룹수 k, 각 표본의 (진입시각·청산시각) ns, embargo봉수
# [Out] 분할 리스트 [(train_idx, test_idx), ...] (purge+embargo 적용됨)
# [사용함수] make_groups / combinatorial_splits / purge_embargo / cpcv_split(메인)
# ==============================================================================
import numpy as np
from itertools import combinations


def make_groups(n, N):
    # n개 표본을 시간순 N개 그룹으로(앞 N-1개는 floor(n/N), 마지막은 나머지). López de Prado 정의.
    base = n // N
    bounds = []
    start = 0
    for g in range(N):
        end = start + base if g < N - 1 else n
        bounds.append((start, end)); start = end
    return bounds   # [(lo,hi), ...] 각 그룹의 인덱스 범위


def purge_embargo_multi(train_idx, test_groups, groups, t_entry, t_exit, embargo_n):
    # 검증그룹들이 떨어져 있을 수 있으므로(예: 0과 5), 각 그룹별로 따로 purge+embargo.
    #   전체 min~max를 한 구간으로 잡으면 사이의 학습그룹까지 다 잘리는 버그 → 그룹별 처리.
    keep_mask = np.ones(len(t_entry), dtype=bool)
    keep_mask[train_idx] = False   # 일단 학습만 True로 뒤집어 관리
    keep_mask = ~keep_mask         # train_idx 위치만 True
    train_set = set(train_idx.tolist())
    removed = set()
    for g in test_groups:
        lo, hi = groups[g]
        te_start = t_entry[lo]; te_end = t_exit[hi - 1] if hi - 1 < len(t_exit) else t_exit[-1]
        for idx in train_idx:
            if idx in removed:
                continue
            # purge: 라벨시간 겹침
            if not (t_exit[idx] < te_start or t_entry[idx] > te_end):
                removed.add(idx); continue
            # embargo: 이 검증그룹 직후 embargo_n 인덱스
            if hi <= idx < hi + embargo_n:
                removed.add(idx)
    return np.array(sorted(train_set - removed), dtype=int)


def cpcv_split(n, t_entry, t_exit, N=6, k=2, embargo_n=None):
    # 메인: C(N,k) 분할 생성 + purge/embargo. 각 분할 = (train_idx, test_idx).
    #   t_entry/t_exit: 길이 n, 각 표본 라벨의 진입·청산 시각(int64 ns 또는 봉인덱스).
    if embargo_n is None:
        embargo_n = max(1, n // (N * 20))   # 표본의 약 5%/그룹 근사
    groups = make_groups(n, N)
    splits = []
    all_idx = np.arange(n)
    for test_groups in combinations(range(N), k):
        test_idx = []
        for g in test_groups:
            lo, hi = groups[g]; test_idx.extend(range(lo, hi))
        test_idx = np.array(sorted(test_idx), dtype=int)
        train_mask = np.ones(n, dtype=bool); train_mask[test_idx] = False
        train_idx = all_idx[train_mask]
        # purge+embargo: 검증그룹별로 따로 적용(떨어진 그룹 전체범위 오인 방지)
        train_idx = purge_embargo_multi(train_idx, test_groups, groups, t_entry, t_exit, embargo_n)
        if len(train_idx) >= 30 and len(test_idx) >= 10:
            splits.append((train_idx, test_idx, test_groups))
    return splits


def cpcv_eval(model_factory, X, y, w, t_entry, t_exit, N=6, k=2, embargo_n=None):
    # 각 분할서 학습→검증 AUC. OOS AUC 분포(평균·표준편차·최저) 반환. 견고성 = 분포가 0.5 위에 안정?
    from sklearn.metrics import roc_auc_score
    splits = cpcv_split(len(X), t_entry, t_exit, N, k, embargo_n)
    aucs = []
    for tr, te, tg in splits:
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        try:
            m = model_factory()
            m.fit(X[tr], y[tr], sample_weight=w[tr])
            p = m.predict_proba(X[te])[:, 1]
            aucs.append(roc_auc_score(y[te], p))
        except Exception:
            continue
    aucs = np.array(aucs)
    if len(aucs) == 0:
        return dict(n_paths=0, auc_mean=float('nan'), auc_std=float('nan'), auc_min=float('nan'), auc_p25=float('nan'))
    return dict(n_paths=len(aucs), auc_mean=round(float(aucs.mean()), 3),
                auc_std=round(float(aucs.std()), 3), auc_min=round(float(aucs.min()), 3),
                auc_p25=round(float(np.percentile(aucs, 25)), 3))
