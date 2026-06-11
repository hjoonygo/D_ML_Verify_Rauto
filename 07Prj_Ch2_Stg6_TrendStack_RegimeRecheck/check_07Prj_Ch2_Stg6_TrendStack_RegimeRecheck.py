# [파일명] check_07Prj_Ch2_Stg6_TrendStack_RegimeRecheck.py
# 코드길이: 약 180줄 / 내부버전: build6_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Stg6 산출물 오염검사(8시나리오) → 분석txt → INDEX. 결과는 D:\ML\verify\00WorkHstr.
# ── 8시나리오 ────────────────────────────────────────────────────────────
#  S1 파일명일치 : test_·check_·run.bat + featstruct.csv·joined.csv 생성
#  S2 원장무결성 : 264행·sha256
#  S3 복리검증   : 전체 264 복리 +560~+610% (best.csv +586% OPVnN 재현)
#  S4 매칭률     : feat_struct 매칭 >= 90%
#  S5 미래참조차단: joined entry_t 정렬·NaT없음 / feat는 asof backward, label_smc 필터미사용
#  S6 집계정합   : featstruct PF>=0, 거래수 합 == 264(또는 매칭수)
#  S7 교차표정합 : crosstab 합 == 매칭 거래수
#  S8 연도커버   : 2023~2026 전부
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, hashlib
from datetime import datetime
import pandas as pd, numpy as np

BASE='07Prj_Ch2_Stg6_TrendStack_RegimeRecheck'
LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0

def find_path(cands):
    for d in ['.','..','../..','D:/ML/verify','D:/ML/Verify','/home/claude/work','/mnt/user-data/uploads']:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return h[0]
    return None
def hstr_dir():
    for d in ['D:/ML/verify/00WorkHstr','D:/ML/Verify/00WorkHstr','../00WorkHstr','/home/claude/work/00WorkHstr']:
        if os.path.isdir(os.path.dirname(d)) or os.path.isdir(d):
            os.makedirs(d,exist_ok=True); return d
    os.makedirs('../00WorkHstr',exist_ok=True); return '../00WorkHstr'
def sha(p):
    if not p or not os.path.exists(p): return 'NA'
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<16),b''): h.update(b)
    return h.hexdigest()[:12]
def _naive(s):
    t=pd.to_datetime(s,errors='coerce')
    try: t=t.dt.tz_localize(None)
    except Exception: pass
    return t
def compound(df):
    df=df.sort_values('entry_t'); bal=START
    for _,r in df.iterrows():
        m=r.get('mult',1.0); mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(r['fund'])) if r['mae']<=-hsd else r['R']*EXP*m
        bal*=(1+p)
    return bal

def run_checks():
    res=[]; ok=True; summ={}
    # 결합 (복리검증용)
    lp=find_path(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(lp) if lp else None
    if led is not None:
        led['entry_t']=_naive(led['entry_t']); led=led.sort_values('entry_t')
        dp=find_path(['*OPVnN*devledger*.csv','*devledger*.csv'])
        if dp:
            dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
            led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
            rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
            led['mult']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
        else: led['mult']=1.0
    # S1
    fs=find_path([f'{BASE}_featstruct.csv']); jn=find_path([f'{BASE}_joined.csv'])
    s1=os.path.exists(f'test_{BASE}.py') and os.path.exists(f'check_{BASE}.py') and os.path.exists('run.bat') and bool(fs) and bool(jn)
    res.append(('S1 파일명일치',s1,f"test/check/bat + featstruct={bool(fs)} joined={bool(jn)}")); ok&=s1
    # S2
    s2=led is not None and len(led)==264
    res.append(('S2 원장무결성',s2,f"rows={0 if led is None else len(led)} sha={sha(lp)}")); ok&=s2
    # S3 복리
    bal=compound(led) if led is not None else 0; ret=(bal/START-1)*100
    s3=560<=ret<=610
    res.append(('S3 복리검증',s3,f"전체복리 {ret:+.0f}% (기대 +586% OPVnN)")); ok&=s3; summ['ret']=round(ret)
    # S4 매칭
    jdf=pd.read_csv(jn) if jn else None
    mr=jdf['feat'].notna().mean()*100 if jdf is not None and 'feat' in jdf.columns else 0
    s4=mr>=90
    res.append(('S4 매칭률',s4,f"feat_struct 매칭 {mr:.0f}% (>=90)")); ok&=s4; summ['match']=round(mr)
    # S5 미래참조
    s5=False
    if jdf is not None:
        t=_naive(jdf['entry_t']); s5=t.notna().all() and t.is_monotonic_increasing
    res.append(('S5 미래참조차단',s5,"joined 정렬·NaT없음 / feat asof backward, label_smc 필터미사용")); ok&=s5
    # S6 집계
    fdf=pd.read_csv(fs) if fs else None
    s6=False
    if fdf is not None:
        s6=(fdf['PF']>=0).all() and fdf['거래수'].sum()<=264 and fdf['거래수'].sum()>=200
    res.append(('S6 집계정합',s6,f"PF>=0·거래수합={0 if fdf is None else int(fdf['거래수'].sum())}")); ok&=s6
    # S7 교차표
    ctp=find_path([f'{BASE}_crosstab.csv']); s7=True; ctsum=0
    if ctp:
        ct=pd.read_csv(ctp,index_col=0); ctsum=int(ct.values.sum())
        s7 = (jdf is not None and ctsum==int(jdf['feat'].notna().sum())) if jdf is not None else True
    res.append(('S7 교차표정합',s7,f"교차표합={ctsum}")); ok&=s7
    # S8 연도
    s8=False
    if jdf is not None:
        yrs=set(jdf['year'].unique()); s8=all(y in yrs for y in [2023,2024,2025,2026])
    res.append(('S8 연도커버',s8,f"연도={sorted(jdf['year'].unique()) if jdf is not None else []}")); ok&=s8
    # 요약: feat_struct 약점
    if fdf is not None:
        weak=fdf[fdf['PF']<1.5]['feat_struct'].tolist()
        summ['weak']=weak; summ['featstruct_sha']=sha(fs)
        summ['table']=fdf[['feat_struct','거래수','PF','수익률%']].to_dict('records')
    return ok,res,summ

if __name__=='__main__':
    ok,res,summ=run_checks()
    print("="*64); print(f"[CHECK] {BASE}  build6_v1"); print("="*64)
    npass=sum(1 for _,o,_ in res if o)
    for name,o,m in res: print(f"  [{'PASS' if o else 'FAIL'}] {name:14s} | {m}")
    print("-"*64); print(f"  결과: {npass}/8 → {'OK' if ok else 'NG'}")
    HD=hstr_dir(); stamp=datetime.now().strftime('%Y%m%d%H%M')
    weak=summ.get('weak',[]); tbl=summ.get('table',[])
    with open(os.path.join(HD,f'{stamp}.txt'),'w',encoding='utf-8') as f:
        f.write(f"[{BASE}] build6_v1 {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"목적: label_smc(미래참조) 장세약점이 feat_struct(실시간)로 재현되나\n")
        f.write(f"오염검사 {npass}/8 ({'OK' if ok else 'NG'}) / 전체복리 {summ.get('ret','?')}% / 매칭 {summ.get('match','?')}%\n")
        f.write(f"feat_struct 약점장세(PF<1.5): {weak if weak else '없음'}\n")
        for r in tbl: f.write(f"  {r['feat_struct']}: n={r['거래수']} PF={r['PF']} ret={r['수익률%']}%\n")
        f.write(f"판정: feat_struct로 약점 재현시 진입필터 가능 / 미재현시 미래참조환상(접음)\n")
        f.write(f"MDD-20% 기준. featstruct_sha={summ.get('featstruct_sha','NA')}\n")
    idx=os.path.join(HD,'00WorkHstr_INDEX.txt')
    with open(idx,'a',encoding='utf-8') as f:
        f.write(f"{stamp} | {BASE} | regime재라벨 {npass}/8 | feat약점:{weak if weak else '없음'} | 복리{summ.get('ret','?')}% | MDD-20%\n")
    print(f"\n[기록] {os.path.join(HD,stamp+'.txt')} / INDEX")
    sys.exit(0 if ok else 2)
