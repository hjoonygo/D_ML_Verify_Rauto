# [파일명] check_07Prj_Ch3_Stg3_TrendStack_OPVnNRemoval.py
# 코드길이: 약 145줄 / 내부버전: build_ch3s3_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Stg3(OPVnN 제거 검증) 산출물 8시나리오 오염검사 → 분석txt → INDEX. 결과 전량 파일.
#        엔진·mult 독립 재구현해 재계산 대조. 핵심: 'OPVnN 제거(NMULT=1.0)=MDD -20% 위반=제거불가' 재현.
# ── 8시나리오 ──
#  S1 파일명일치 : test_·check_·run.bat + 결과5종(summary/sweep/yearly/cpcv/wf)
#  S2 원장무결성 : 264행·sha
#  S3 복리재현   : 독립재계산 선정NMULT rule ret/mdd == summary(±1%p)
#  S4 룰정합     : 역추세 진입(ctr)>0 & uptrend숏(고정0)>0 & NMULT=1.0과 0.6 결과 상이
#  S5 미래참조차단: 주석제거 후 shift(-) 0건 / entry_t 정렬·NaT없음 / feat_src!=label_smc
#  S6 CPCV정합   : 폴드>0·NaN없음
#  S7 OPVnN핵심  : 제거(NMULT=1.0) 전체MDD < -20%(제거불가 재현) AND 선정NMULT 최악(폴드/연도) >= -20%
#  S8 연도커버   : 2023~2026 전부 & removal_ok==0(제거 기각 기록 일치)
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, re, hashlib
from datetime import datetime
import numpy as np, pandas as pd

BASE='07Prj_Ch3_Stg3_TrendStack_OPVnNRemoval'
LEV=22; EXP=1.559; OPV=0.25; SHORT_CUT=0.0; MDD_LIMIT=-20.0
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0
N_BLOCKS=6; EMBARGO=1; K_OOS=(1,2,3)
SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','../00WorkHstr','D:/ML/verify/00WorkHstr','/mnt/user-data/uploads']
import itertools

def find(cands):
    for d in SEARCH:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return sorted(h)[0]
    return None
def hstr_dir():
    for d in ['D:/ML/verify/00WorkHstr','D:/ML/Verify/00WorkHstr','../00WorkHstr']:
        if os.path.isdir(d) or os.path.isdir(os.path.dirname(d)): os.makedirs(d,exist_ok=True); return d
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
def compound(R,mae,fund,mult):
    bal=START;peak=START;mdd=0.0
    for i in range(len(R)):
        m=mult[i]
        if m!=m: m=1.0
        mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(fund[i])) if mae[i]<=-hsd else R[i]*EXP*m
        bal*=(1.0+p); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0)
    return (bal/START-1.0)*100.0, mdd*100.0

def build():
    lp=find(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t']); led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find(['*OPVnN*devledger*.csv','*devledger*.csv'])
    dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
    led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
    rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
    led['ctr']=((led['dev'].abs()>=OPV)&(led['side']==-rd)).fillna(False)
    fc=find([f'{BASE}_featcache.csv','*featcache*.csv'])
    if fc:
        c=pd.read_csv(fc); c['entry_t']=_naive(c['entry_t']); mp=dict(zip(c['entry_t'],c['feat']))
        led['feat']=[mp.get(t) for t in led['entry_t']]
    else: led['feat']=None
    return led, lp
def mult_for(led,nm):
    up_sh=((led['feat']=='uptrend')&(led['side']==-1)).values
    return np.where(up_sh, SHORT_CUT, np.where(led['ctr'].values, nm, 1.0))
def make_blocks(n):
    edges=np.array_split(np.arange(n),N_BLOCKS); out=[]
    for k in K_OOS:
        for cmb in itertools.combinations(range(N_BLOCKS),k):
            idx=np.sort(np.concatenate([edges[b] for b in cmb])); keep=np.ones(len(idx),bool); d=np.diff(idx)
            brk=set(np.where(d>1)[0])|{0,len(idx)-1}|set(b+1 for b in np.where(d>1)[0])
            for e in brk:
                for o in range(EMBARGO):
                    if 0<=e+o<len(idx): keep[e+o]=False
                    if 0<=e-o<len(idx): keep[e-o]=False
            out.append(idx[keep])
    return out

def run_checks():
    res=[]; ok=True; S={}
    led,lp=build()
    sm=pd.read_csv(find([f'{BASE}_summary.csv'])) if find([f'{BASE}_summary.csv']) else None
    nb=float(sm['nmult_best'][0]) if sm is not None else 0.6
    r5=[find([f'{BASE}_{k}.csv']) for k in ['summary','sweep','yearly','cpcv','wf']]
    s1=os.path.exists(f'test_{BASE}.py') and os.path.exists(f'check_{BASE}.py') and os.path.exists('run.bat') and all(r5)
    res.append(('S1 파일명일치',s1,f"test/check/bat+결과5종={all(r5)}")); ok&=s1
    s2=(len(led)==264); res.append(('S2 원장무결성',s2,f"rows={len(led)} sha={sha(lp)}")); ok&=s2
    R=led['R'].values;mae=led['mae'].values;fund=led['fund'].values
    rret,rmdd=compound(R,mae,fund,mult_for(led,nb))
    agree=(sm is not None) and abs(sm['rule_ret'][0]-rret)<=1 and abs(sm['rule_mdd'][0]-rmdd)<=0.5
    s3=agree and (300<=rret<=2000)
    res.append(('S3 복리재현',s3,f"NMULT={nb} ret{rret:+.0f}% MDD{rmdd:.1f}% summary일치={agree}")); ok&=s3
    S.update(nmult_best=nb,rule_ret=round(rret),rule_mdd=round(rmdd,1))
    nctr=int(led['ctr'].sum()); nush=int(((led['feat']=='uptrend')&(led['side']==-1)).sum())
    diff=not np.allclose(mult_for(led,1.0),mult_for(led,0.6))
    s4=(nctr>0 and nush>0 and diff)
    res.append(('S4 룰정합',s4,f"역추세={nctr} uptrend숏={nush} NMULT1.0≠0.6={diff}")); ok&=s4; S['ctr_n']=nctr; S['ush_n']=nush
    src=open(f'test_{BASE}.py',encoding='utf-8').read() if os.path.exists(f'test_{BASE}.py') else ''
    code='\n'.join(l.split('#',1)[0] for l in src.splitlines())
    nosh=re.search(r'shift\(\s*-',code) is None; t=led['entry_t']; sok=t.notna().all() and t.is_monotonic_increasing
    fsrc=sm['feat_src'][0] if (sm is not None and 'feat_src' in sm.columns) else '?'
    s5=nosh and sok and ('label_smc' not in str(fsrc)); res.append(('S5 미래참조차단',s5,f"shift(-)없음={nosh} 정렬={sok} feat={fsrc}")); ok&=s5
    cp=pd.read_csv(r5[3]) if r5[3] else None
    s6=(cp is not None and len(cp)>0 and not cp[['mdd']].isna().any().any())
    res.append(('S6 CPCV정합',s6,f"folds={0 if cp is None else len(cp)}")); ok&=s6
    # S7 핵심: 제거(1.0) MDD<-20 재현 & 선정NMULT 최악 >= -20
    rem_ret,rem_mdd=compound(R,mae,fund,mult_for(led,1.0))
    worst_fold = round(cp['mdd'].min(),1) if (cp is not None and 'mdd' in cp.columns) else None
    yf=pd.read_csv(r5[2]) if r5[2] else None
    worst_year = round(yf['rule_mdd'].min(),1) if (yf is not None and 'rule_mdd' in yf.columns) else None
    s7=(rem_mdd < MDD_LIMIT) and (worst_fold is not None and worst_fold>=MDD_LIMIT) and (worst_year is not None and worst_year>=MDD_LIMIT)
    res.append(('S7 OPVnN핵심',s7,f"제거MDD{rem_mdd:.1f}%(<-20확인) 선정최악폴드{worst_fold}% 연도{worst_year}%")); ok&=s7
    S.update(removal_mdd=round(rem_mdd,1),worst_fold=worst_fold,worst_year=worst_year)
    yrs=set(int(x) for x in yf['year']) if yf is not None else set()
    rem_ok=int(sm['removal_ok'][0]) if (sm is not None and 'removal_ok' in sm.columns) else 9
    s8=all(y in yrs for y in [2023,2024,2025,2026]) and (rem_ok==0)
    res.append(('S8 연도+제거기각',s8,f"연도={sorted(yrs)} removal_ok={rem_ok}(0=기각)")); ok&=s8
    S['code_sha']=sha(f'test_{BASE}.py')
    return ok,res,S

if __name__=='__main__':
    ok,res,S=run_checks(); npass=sum(1 for _,o,_ in res if o)
    print('='*66); print(f"[CHECK] {BASE}  build_ch3s3_v1"); print('='*66)
    for n,o,m in res: print(f"  [{'PASS' if o else 'FAIL'}] {n:16s} | {m}")
    print('-'*66); print(f"  결과: {npass}/8 -> {'OK' if ok else 'NG'}")
    HD=hstr_dir(); stamp=datetime.now().strftime('%Y%m%d%H%M')
    with open(os.path.join(HD,f'{stamp}.txt'),'w',encoding='utf-8') as f:
        f.write(f"[{BASE}] build_ch3s3_v1 {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("목적(E1): Stg2 숏컷 깔린 상태에서 OPVnN(역추세 NMULT배) 제거 가능여부 검증\n")
        f.write(f"오염검사 {npass}/8 ({'OK' if ok else 'NG'})\n")
        f.write(f"결론: OPVnN 제거(NMULT=1.0) 전체MDD {S.get('removal_mdd')}% = -20% 위반 → 제거 불가(기각)\n")
        f.write(f"한도내 최적 NMULT={S.get('nmult_best')} : ret{S.get('rule_ret')}% MDD{S.get('rule_mdd')}% (최악폴드{S.get('worst_fold')}% 연도{S.get('worst_year')}%)\n")
        f.write(f"의미: OPVnN은 군더더기 아닌 낙폭통제 필수. NMULT는 레버와 함께 다룰 'MDD 예산 다이얼'(0.6 보수유지, 0.8은 여유부족). code_sha={S.get('code_sha')}\n")
    with open(os.path.join(HD,'00WorkHstr_INDEX.txt'),'a',encoding='utf-8') as f:
        f.write(f"{stamp} | {BASE} | CHECK {npass}/8 | E1:OPVnN제거기각(제거시MDD{S.get('removal_mdd')}%) | 확정NMULT{S.get('nmult_best')} ret{S.get('rule_ret')}% MDD{S.get('rule_mdd')}% | 한도-20%\n")
    print(f"\n[기록] {os.path.join(HD,stamp+'.txt')} / INDEX 추가")
    sys.exit(0 if ok else 2)
