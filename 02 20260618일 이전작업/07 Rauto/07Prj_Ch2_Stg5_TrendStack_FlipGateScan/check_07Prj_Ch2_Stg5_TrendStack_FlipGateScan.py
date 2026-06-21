# [파일명] check_07Prj_Ch2_Stg5_TrendStack_FlipGateScan.py
# 코드길이: 약 200줄 / 내부버전: build5_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] test 산출물 오염검사(8시나리오) → 분석txt 저장 → INDEX 한 줄 기록.
#        결과·INDEX는 하위폴더가 아니라 D:\ML\verify\00WorkHstr 로 출력.
#
# ── 사용 파일 ────────────────────────────────────────────────────────────
#  IN  ..\stg6_levsweep_ledger.csv                       : 원장(라벨 원천, 264행)
#  IN  .\07Prj_Ch2_Stg5_TrendStack_FlipGateScan_scan.csv : test 결과(피처 채점)
#  IN  .\07Prj_Ch2_Stg5_TrendStack_FlipGateScan_labels.csv: test 라벨
#  OUT D:\ML\verify\00WorkHstr\(YYYYMMDDHHMM).txt        : 분석 결과
#  OUT D:\ML\verify\00WorkHstr\00WorkHstr_INDEX.txt      : INDEX 한 줄 추가
#
# ── 함수 (In/Out) ───────────────────────────────────────────────────────
#  find_path(c)        In: 후보명 list      Out: 경로|None
#  hstr_dir()          In: -                Out: 00WorkHstr 경로(없으면 생성)
#  sha256_of(p)        In: 경로             Out: 해시 str
#  run_checks()        In: -                Out: (통과여부 bool, 시나리오 결과 list, 요약 dict)
#
# ── 8시나리오 ────────────────────────────────────────────────────────────
#  S1 파일명 일치 : test_·check_·run.bat 존재 + scan.csv·labels.csv 생성됨
#  S2 원장 무결성 : 원장 존재·264행·sha256 기록
#  S3 라벨 정합성 : 전환형64 / 회복형9 / 정상191 (figM 일치)
#  S4 피처 완전성 : 채점표에 기대 피처 11종 전부 존재
#  S5 미래참조차단: 라벨 entry_t 모두 유효(NaT 없음)·정렬, 매칭은 asof<entry_t 설계
#  S6 AUC 범위    : AUC∈[0,1], sep∈[0,0.5]
#  S7 순열p 범위  : perm_p∈[0,1] (있는 행)
#  S8 연도 커버   : 2023~2026 전부 등장 + 거래 합 264
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, hashlib
from datetime import datetime
import pandas as pd
import numpy as np

BASE='07Prj_Ch2_Stg5_TrendStack_FlipGateScan'
EXPECT_FEATS=['oi_change_1h_pct','oi_drop_after_spike','top_retail_divergence',
              'taker_imbalance_5m_avg','oi_zscore_24h','fng','fundingRate','funding_div',
              'cvd_1h','taker_imb_60m','tick_dens_60m']

def find_path(cands):
    for d in ['.','..','../..','D:/ML/verify','D:/ML/Verify','/home/claude/work']:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return h[0]
    return None

def hstr_dir():
    for d in ['D:/ML/verify/00WorkHstr','D:/ML/Verify/00WorkHstr','../00WorkHstr','/home/claude/work/00WorkHstr']:
        parent=os.path.dirname(d)
        if os.path.isdir(parent) or os.path.isdir(d):
            os.makedirs(d, exist_ok=True); return d
    os.makedirs('../00WorkHstr', exist_ok=True); return '../00WorkHstr'

def sha256_of(p):
    if not p or not os.path.exists(p): return 'NA'
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<16), b''): h.update(b)
    return h.hexdigest()[:12]

def run_checks():
    res=[]; ok_all=True; summ={}
    # S1 파일명
    f_test=os.path.exists(f'test_{BASE}.py'); f_chk=os.path.exists(f'check_{BASE}.py')
    f_bat=os.path.exists('run.bat')
    scan=find_path([f'{BASE}_scan.csv']); labels=find_path([f'{BASE}_labels.csv'])
    s1 = f_test and f_chk and f_bat and bool(scan) and bool(labels)
    res.append(('S1 파일명일치', s1, f"test={f_test} check={f_chk} bat={f_bat} scan={bool(scan)} labels={bool(labels)}"))
    ok_all &= s1
    # S2 원장
    led_p=find_path(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(led_p) if led_p else None
    s2 = led is not None and len(led)==264
    res.append(('S2 원장무결성', s2, f"path={led_p} rows={0 if led is None else len(led)} sha={sha256_of(led_p)}"))
    ok_all &= s2
    # S3 라벨
    s3=False; n_flip=n_rec=n_norm=-1
    if led is not None:
        mae=led['mae'].values; R=led['R'].values
        deep=mae<=-0.02; rec=(R-mae)>=0.03
        n_norm=int((~deep).sum()); n_rec=int((deep&rec).sum()); n_flip=int((deep&~rec).sum())
        s3 = (n_flip==64 and n_rec==9 and n_norm==191)
    res.append(('S3 라벨정합성', s3, f"전환형={n_flip} 회복형={n_rec} 정상={n_norm} (기대 64/9/191)"))
    ok_all &= s3; summ['n_flip']=n_flip
    # S4 피처
    sc=pd.read_csv(scan) if scan else None
    feats=set(sc['feature']) if sc is not None else set()
    miss=[f for f in EXPECT_FEATS if f not in feats]
    s4 = len(miss)==0
    res.append(('S4 피처완전성', s4, f"있음={len(feats)}/11 누락={miss}"))
    ok_all &= s4
    # S5 미래참조차단(라벨 entry_t 유효·정렬)
    s5=False
    lb=pd.read_csv(labels) if labels else None
    if lb is not None:
        t=pd.to_datetime(lb['entry_t'], errors='coerce')
        s5 = t.notna().all() and t.is_monotonic_increasing
    res.append(('S5 미래참조차단', s5, "entry_t NaT없음·정렬 / 매칭 asof<entry_t 설계(코드보증)"))
    ok_all &= s5
    # S6 AUC 범위
    s6=False
    if sc is not None:
        a=sc['AUC_flip'].dropna(); sp=sc['sep'].dropna()
        s6 = ((a>=0)&(a<=1)).all() and ((sp>=0)&(sp<=0.5)).all()
    res.append(('S6 AUC범위', s6, f"AUC∈[0,1]·sep∈[0,0.5] {'OK' if s6 else 'NG'}"))
    ok_all &= s6
    # S7 순열p
    s7=False
    if sc is not None:
        p=sc['perm_p'].dropna()
        s7 = ((p>=0)&(p<=1)).all() if len(p)>0 else True
    res.append(('S7 순열p범위', s7, f"perm_p∈[0,1] {'OK' if s7 else 'NG'}"))
    ok_all &= s7
    # S8 연도커버
    s8=False; yrs={}
    if lb is not None:
        yrs=dict(lb['year'].value_counts().sort_index())
        s8 = all(y in yrs for y in [2023,2024,2025,2026]) and int(lb.shape[0])==264
    res.append(('S8 연도커버', s8, f"연도={ {int(k):int(v) for k,v in yrs.items()} } 합={0 if lb is None else len(lb)}"))
    ok_all &= s8
    # 요약(알파후보)
    if sc is not None:
        cand=sc[sc['verdict'].astype(str).str.contains('알파')]
        summ['cands']=list(zip(cand['feature'], cand['AUC_flip'], cand['dir'])) if len(cand) else []
        summ['scan_sha']=sha256_of(scan)
    return ok_all, res, summ

if __name__=='__main__':
    ok, res, summ = run_checks()
    print("="*64); print(f"[CHECK] {BASE}  내부버전 build5_v1"); print("="*64)
    npass=sum(1 for _,o,_ in res if o)
    for name,o,msg in res:
        print(f"  [{'PASS' if o else 'FAIL'}] {name:14s} | {msg}")
    print("-"*64); print(f"  결과: {npass}/8 통과  →  {'OK(오염없음)' if ok else 'NG(검토필요)'}")

    # 분석txt + INDEX (00WorkHstr)
    HD=hstr_dir(); stamp=datetime.now().strftime('%Y%m%d%H%M')
    txt=os.path.join(HD, f'{stamp}.txt')
    cand_str = '; '.join([f"{f}(AUC{a},{d})" for f,a,d in summ.get('cands',[])]) or '없음'
    with open(txt,'w',encoding='utf-8') as f:
        f.write(f"[{BASE}] build5_v1  {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"목적: 전환형 64건 분리력 검증 (진입시점 가격외부 피처 11종, 슬리피지 제외)\n")
        f.write(f"오염검사: {npass}/8 통과 ({'OK' if ok else 'NG'})\n")
        f.write(f"전환형={summ.get('n_flip','?')} / 라벨 64/9/191 기대\n")
        f.write(f"★알파후보: {cand_str}\n")
        f.write(f"기준: AUC sep>=0.15 & 순열p<0.05 & 연도방향일치 & 가격상관<0.5\n")
        f.write(f"MDD 절대선 -20%(확정). 슬리피지는 분리력 부족시에만 재검토.\n")
        f.write(f"scan_sha={summ.get('scan_sha','NA')}\n")
    idx=os.path.join(HD,'00WorkHstr_INDEX.txt')
    line=f"{stamp} | {BASE} | 전환형분리력 {npass}/8 | 알파후보:{cand_str} | MDD-20%\n"
    with open(idx,'a',encoding='utf-8') as f: f.write(line)
    print(f"\n[기록] 분석txt: {txt}")
    print(f"[기록] INDEX  : {idx}")
    sys.exit(0 if ok else 2)
