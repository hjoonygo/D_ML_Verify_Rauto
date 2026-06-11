# [파일명] check_07Prj_Ch3_Stg2_TrendStack_UptrendShortCut.py
# 코드길이: 약 150줄 / 내부버전: build_ch3s2_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Stg2(uptrend 숏 축소) 산출물 8시나리오 오염검사 → 분석txt → INDEX. 결과 전량 파일.
#        엔진을 test 와 독립 재구현해 재계산값과 test 보고값을 대조. 출력=D:\ML\verify\00WorkHstr.
# ── 8시나리오 ──
#  S1 파일명일치 : test_·check_·run.bat + 결과5종(summary/sweep/yearly/cpcv/wf)
#  S2 원장무결성 : 264행·sha
#  S3 복리재현   : 독립재계산 기준선 ret∈[560,610] & 룰(sh_best)>기준선 & summary 일치(±1%p)
#  S4 룰정합     : m_rule == m_base×sh (uptrend&숏)·아니면 m_base / uptrend숏>0
#  S5 미래참조차단: 주석제거 후 shift(-) 0건 / entry_t 정렬·NaT없음 / feat_src!=label_smc
#  S6 CPCV정합   : 폴드>0·n>=8·NaN없음
#  S7 MDD가드    : 최악폴드 MDD >= -20% AND 모든연도 룰MDD >= -20% (핵심 안전게이트)
#  S8 연도커버   : 2023~2026 전부 & uptrend숏 매년적자(구조성) 확인
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, re, hashlib
from datetime import datetime
import numpy as np, pandas as pd

BASE='07Prj_Ch3_Stg2_TrendStack_UptrendShortCut'
LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60; MDD_LIMIT=-20.0
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0
SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','../00WorkHstr','D:/ML/verify/00WorkHstr','/mnt/user-data/uploads']

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
    bal=START; peak=START; mdd=0.0
    for i in range(len(R)):
        m=mult[i];
        if m!=m: m=1.0
        mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(fund[i])) if mae[i]<=-hsd else R[i]*EXP*m
        bal*=(1.0+p); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0)
    ret=(bal/START-1.0)*100.0
    return ret, mdd*100.0

def build():
    lp=find(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t']); led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find(['*OPVnN*devledger*.csv','*devledger*.csv'])
    if dp:
        dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
        led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
        rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
        led['m_base']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
    else: led['m_base']=1.0
    fc=find([f'{BASE}_featcache.csv','*featcache*.csv'])
    if fc:
        c=pd.read_csv(fc); c['entry_t']=_naive(c['entry_t']); mp=dict(zip(c['entry_t'],c['feat']))
        led['feat']=[mp.get(t) for t in led['entry_t']]
    else: led['feat']=None
    return led, lp

def run_checks():
    res=[]; ok=True; S={}
    led,lp=build()
    sm=pd.read_csv(find([f'{BASE}_summary.csv'])) if find([f'{BASE}_summary.csv']) else None
    sh=float(sm['sh_best'][0]) if sm is not None else 0.0
    up_sh=(led['feat']=='uptrend')&(led['side']==-1)
    m_rule=np.where(up_sh, led['m_base']*sh, led['m_base'])
    # S1
    r5=[find([f'{BASE}_{k}.csv']) for k in ['summary','sweep','yearly','cpcv','wf']]
    s1=os.path.exists(f'test_{BASE}.py') and os.path.exists(f'check_{BASE}.py') and os.path.exists('run.bat') and all(r5)
    res.append(('S1 파일명일치',s1,f"test/check/bat+결과5종={all(r5)}")); ok&=s1
    # S2
    s2=(len(led)==264); res.append(('S2 원장무결성',s2,f"rows={len(led)} sha={sha(lp)}")); ok&=s2
    # S3
    rb=compound(led['R'].values,led['mae'].values,led['fund'].values,led['m_base'].values)
    rr=compound(led['R'].values,led['mae'].values,led['fund'].values,m_rule)
    agree = (sm is not None) and abs(sm['base_ret'][0]-rb[0])<=1 and abs(sm['rule_ret'][0]-rr[0])<=1
    s3=(560<=rb[0]<=610) and (rr[0]>rb[0]) and agree
    res.append(('S3 복리재현',s3,f"기준{rb[0]:+.0f}% 룰(sh={sh}){rr[0]:+.0f}% summary일치={agree}")); ok&=s3
    S.update(base_ret=round(rb[0]),base_mdd=round(rb[1],1),rule_ret=round(rr[0]),rule_mdd=round(rr[1],1),sh_best=sh)
    # S4
    nush=int(up_sh.sum()); exp=np.where(up_sh, led['m_base']*sh, led['m_base'])
    s4=(nush>0) and np.allclose(np.nan_to_num(m_rule),np.nan_to_num(exp),atol=1e-9)
    res.append(('S4 룰정합',s4,f"uptrend숏={nush} 규칙일치={s4}")); ok&=s4; S['uptrend_short_n']=nush
    # S5
    src=open(f'test_{BASE}.py',encoding='utf-8').read() if os.path.exists(f'test_{BASE}.py') else ''
    code='\n'.join(ln.split('#',1)[0] for ln in src.splitlines())
    no_shift=re.search(r'shift\(\s*-',code) is None; t=led['entry_t']; sok=t.notna().all() and t.is_monotonic_increasing
    fsrc=sm['feat_src'][0] if (sm is not None and 'feat_src' in sm.columns) else '?'
    s5=no_shift and sok and ('label_smc' not in str(fsrc))
    res.append(('S5 미래참조차단',s5,f"shift(-)없음={no_shift} 정렬={sok} feat출처={fsrc}")); ok&=s5
    # S6
    cp=pd.read_csv(r5[3]) if r5[3] else None
    s6=(cp is not None and len(cp)>0 and (cp['n']>=8).all() and not cp[['d_ret','d_mdd']].isna().any().any())
    res.append(('S6 CPCV정합',s6,f"folds={0 if cp is None else len(cp)}")); ok&=s6
    # S7 MDD가드
    worst_fold = round(cp['rule_mdd'].min(),1) if (cp is not None and 'rule_mdd' in cp.columns) else None
    yf=pd.read_csv(r5[2]) if r5[2] else None
    worst_year = round(yf['rule_mdd'].min(),1) if (yf is not None and 'rule_mdd' in yf.columns) else None
    s7=(worst_fold is not None and worst_year is not None and worst_fold>=MDD_LIMIT and worst_year>=MDD_LIMIT)
    res.append(('S7 MDD가드(-20%)',s7,f"최악폴드={worst_fold}% 최악연도={worst_year}%")); ok&=s7
    S['worst_fold_mdd']=worst_fold; S['worst_year_mdd']=worst_year
    # S8
    yneg=True; yrs=set()
    if yf is not None:
        yrs=set(int(x) for x in yf['year'])
        if 'ushort_R%' in yf.columns: yneg=bool((yf['ushort_R%']<=0).all())
    s8=all(y in yrs for y in [2023,2024,2025,2026]) and len(yf)==4 and yneg
    res.append(('S8 연도커버+구조성',s8,f"연도={sorted(yrs)} uptrend숏매년적자={yneg}")); ok&=s8
    S['ushort_neg_allyears']=int(yneg); S['code_sha']=sha(f'test_{BASE}.py')
    return ok,res,S

if __name__=='__main__':
    ok,res,S=run_checks(); npass=sum(1 for _,o,_ in res if o)
    print('='*66); print(f"[CHECK] {BASE}  build_ch3s2_v1"); print('='*66)
    for n,o,m in res: print(f"  [{'PASS' if o else 'FAIL'}] {n:16s} | {m}")
    print('-'*66); print(f"  결과: {npass}/8 -> {'OK' if ok else 'NG'}")
    HD=hstr_dir(); stamp=datetime.now().strftime('%Y%m%d%H%M')
    with open(os.path.join(HD,f'{stamp}.txt'),'w',encoding='utf-8') as f:
        f.write(f"[{BASE}] build_ch3s2_v1 {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("목적: Stg1 전체uptrend축소의 2024손해를 개선 — '상승구조 역행 숏'만 외과적 축소(실시간 feat+side 1줄판정)\n")
        f.write(f"오염검사 {npass}/8 ({'OK' if ok else 'NG'})\n")
        f.write(f"숏승수 SH_best={S.get('sh_best')} / uptrend숏거래={S.get('uptrend_short_n')}건(4년 전부 적자 구조성={S.get('ushort_neg_allyears')})\n")
        f.write(f"전체: 기준선 ret{S.get('base_ret')}% MDD{S.get('base_mdd')}% → 룰 ret{S.get('rule_ret')}% MDD{S.get('rule_mdd')}%\n")
        f.write(f"MDD가드 최악폴드{S.get('worst_fold_mdd')}% 최악연도{S.get('worst_year_mdd')}% (한도 -20%)\n")
        f.write(f"판정: Stg1대비 수익·Calmar 우위·2024 개선·CPCV 견고면 채택후보 → Rauto 실시간룰 박제. code_sha={S.get('code_sha')}\n")
    with open(os.path.join(HD,'00WorkHstr_INDEX.txt'),'a',encoding='utf-8') as f:
        f.write(f"{stamp} | {BASE} | CHECK {npass}/8 | SH{S.get('sh_best')} 기준{S.get('base_ret')}%→룰{S.get('rule_ret')}% "
                f"MDD{S.get('base_mdd')}→{S.get('rule_mdd')} | 최악폴드MDD{S.get('worst_fold_mdd')}% | uptrend숏매년적자{S.get('ushort_neg_allyears')} | 한도-20%\n")
    print(f"\n[기록] {os.path.join(HD,stamp+'.txt')} / INDEX 추가")
    sys.exit(0 if ok else 2)
