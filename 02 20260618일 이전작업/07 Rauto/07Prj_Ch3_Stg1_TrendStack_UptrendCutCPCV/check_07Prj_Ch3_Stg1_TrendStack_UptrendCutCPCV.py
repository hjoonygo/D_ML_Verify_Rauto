# [파일명] check_07Prj_Ch3_Stg1_TrendStack_UptrendCutCPCV.py
# 코드길이: 약 150줄 / 내부버전: build_ch3s1_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] test 산출물 8시나리오 오염검사 → 분석txt → INDEX.  결과는 전량 파일(복붙요청 없음).
#        엔진을 test 와 '독립' 재구현해 재계산값과 test 보고값을 대조(조작·버그 동시 적발).
#        출력 위치: 분석txt·INDEX 는 하위폴더가 아니라 D:\ML\verify\00WorkHstr 로.
# ── 8시나리오 ────────────────────────────────────────────────────────────
#  S1 파일명일치 : test_·check_·run.bat + 결과 4종(summary/cpcv/yearly/wf) 존재
#  S2 원장무결성 : ledger 264행·sha256
#  S3 복리재현   : 독립재계산 기준선 ret∈[560,610](OPVnN +586 검증) & 룰 ret>기준선 & summary와 일치(±1%p)
#  S4 룰정합     : m_rule == m_base×0.3(uptrend)·아니면 m_base / uptrend>0
#  S5 미래참조차단: test 소스 shift(-) 0건 / entry_t 정렬·NaT없음 / feat_src!=label_smc
#  S6 CPCV정합   : cpcv 폴드>0·n>=8·NaN없음·MDD개선% 보고
#  S7 2024게이트 : yearly 에 2024 존재 & gate_2024 기록 & cal_keep 보고
#  S8 연도커버   : 2023~2026 전부 & yearly 4행
# ── 함수 (In/Out) ──  find/_naive/sha = 경로·시각·해시 / engine = 독립 복리엔진 / run_checks = (ok,res,summ)
# ── 상수 = test 와 동일 (LEV22 EXP1.559 OPV0.25 NMULT0.6 UP_MULT0.3 ...) ──
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, re, hashlib
from datetime import datetime
import numpy as np, pandas as pd

BASE='07Prj_Ch3_Stg1_TrendStack_UptrendCutCPCV'
LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60; UP_MULT=0.30
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0
SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','../00WorkHstr','D:/ML/verify/00WorkHstr','/mnt/user-data/uploads']

def find(cands):
    for d in SEARCH:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return h[0]
    return None
def hstr_dir():
    for d in ['D:/ML/verify/00WorkHstr','D:/ML/Verify/00WorkHstr','../00WorkHstr']:
        if os.path.isdir(d) or os.path.isdir(os.path.dirname(d)):
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
def compound(R,mae,fund,mult):                 # 독립 재구현(엔진 검증용)
    bal=START; peak=START; mdd=0.0
    for i in range(len(R)):
        m=mult[i];
        if m!=m: m=1.0
        mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(fund[i])) if mae[i]<=-hsd else R[i]*EXP*m
        bal*=(1.0+p); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0)
    ret=(bal/START-1.0)*100.0
    return ret, mdd*100.0, (ret/abs(mdd*100.0) if mdd<0 else float('nan'))

def build_ledger():
    lp=find(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t']); led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find(['*OPVnN*devledger*.csv','*devledger*.csv'])
    if dp:
        dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
        led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
        rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
        led['m_base']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
    else: led['m_base']=1.0
    fc=find([f'{BASE}_featcache.csv'])           # test 가 만든 feat 캐시로 feat 부착
    if fc:
        c=pd.read_csv(fc); c['entry_t']=_naive(c['entry_t']); mp=dict(zip(c['entry_t'],c['feat']))
        led['feat']=[mp.get(t) for t in led['entry_t']]
    else: led['feat']=None
    led['m_rule']=np.where(led['feat']=='uptrend', led['m_base']*UP_MULT, led['m_base'])
    return led, lp

def run_checks():
    res=[]; ok=True; summ={}
    led,lp=build_ledger()
    # S1
    r4=[find([f'{BASE}_{k}.csv']) for k in ['summary','cpcv','yearly','wf']]
    s1=os.path.exists(f'test_{BASE}.py') and os.path.exists(f'check_{BASE}.py') and os.path.exists('run.bat') and all(r4)
    res.append(('S1 파일명일치',s1,f"test/check/bat + 결과4종={all(r4)}")); ok&=s1
    # S2
    s2=(led is not None and len(led)==264)
    res.append(('S2 원장무결성',s2,f"rows={0 if led is None else len(led)} sha={sha(lp)}")); ok&=s2
    # S3 독립 재계산 vs 보고
    rb=compound(led['R'].values,led['mae'].values,led['fund'].values,led['m_base'].values)
    rr=compound(led['R'].values,led['mae'].values,led['fund'].values,led['m_rule'].values)
    sm=pd.read_csv(r4[0]) if r4[0] else None
    agree=True
    if sm is not None:
        agree=abs(sm['base_ret'][0]-rb[0])<=1.0 and abs(sm['rule_ret'][0]-rr[0])<=1.0
    s3=(560<=rb[0]<=610) and (rr[0]>rb[0]) and agree
    res.append(('S3 복리재현',s3,f"기준{rb[0]:+.0f}% 룰{rr[0]:+.0f}% (summary일치={agree})")); ok&=s3
    summ.update(base_ret=round(rb[0]),rule_ret=round(rr[0]),base_mdd=round(rb[1],1),rule_mdd=round(rr[1],1),
                base_cal=round(rb[2],2),rule_cal=round(rr[2],2))
    # S4 룰정합
    up=(led['feat']=='uptrend'); exp_rule=np.where(up,led['m_base']*UP_MULT,led['m_base'])
    s4=bool(up.sum()>0) and np.allclose(np.nan_to_num(led['m_rule'].values),np.nan_to_num(exp_rule),atol=1e-9)
    res.append(('S4 룰정합',s4,f"uptrend={int(up.sum())} mult규칙일치={s4}")); ok&=s4; summ['uptrend_n']=int(up.sum())
    # S5 미래참조차단
    src=open(f'test_{BASE}.py',encoding='utf-8').read() if os.path.exists(f'test_{BASE}.py') else ''
    code_only='\n'.join(ln.split('#',1)[0] for ln in src.splitlines())   # 주석 제거 후 실코드만 스캔
    no_shift = (re.search(r'shift\(\s*-', code_only) is None)
    t=led['entry_t']; sorted_ok=t.notna().all() and t.is_monotonic_increasing
    feat_src = sm['feat_src'][0] if (sm is not None and 'feat_src' in sm.columns) else '?'
    s5 = no_shift and sorted_ok and ('label_smc' not in str(feat_src))
    res.append(('S5 미래참조차단',s5,f"shift(-)없음={no_shift} 정렬={sorted_ok} feat출처={feat_src}")); ok&=s5
    # S6 CPCV정합
    cp=pd.read_csv(r4[1]) if r4[1] else None
    s6=False; mddbetter='?'
    if cp is not None and len(cp)>0:
        s6=(cp['n']>=8).all() and not cp[['d_ret','d_mdd','d_cal']].isna().any().any()
        mddbetter=round((cp['d_mdd']>0).mean()*100)
    res.append(('S6 CPCV정합',s6,f"folds={0 if cp is None else len(cp)} MDD개선={mddbetter}%")); ok&=s6
    summ['cpcv_folds']=0 if cp is None else len(cp); summ['cpcv_mdd_better']=mddbetter
    # S7 2024게이트
    yf=pd.read_csv(r4[2]) if r4[2] else None
    gate='?'; ck='?'
    if yf is not None and 2024 in set(yf['year']):
        row=yf[yf['year']==2024].iloc[0]; ck=round(float(row['cal_keep']),2)
        gate = 'PASS' if (sm is not None and int(sm['gate_2024'][0])==1) else 'FAIL'
    s7=(gate in ('PASS','FAIL')) and (ck!='?')
    res.append(('S7 2024게이트',s7,f"gate={gate} cal_keep={ck}")); ok&=s7; summ['gate2024']=gate; summ['cal_keep_2024']=ck
    # S8 연도커버
    s8=False
    if yf is not None:
        yrs=set(int(x) for x in yf['year']); s8=all(y in yrs for y in [2023,2024,2025,2026]) and len(yf)==4
    res.append(('S8 연도커버',s8,f"연도={sorted(set(int(x) for x in yf['year'])) if yf is not None else []}")); ok&=s8
    summ['code_sha']={'test':sha(f'test_{BASE}.py'),'check':sha(f'check_{BASE}.py')}
    return ok,res,summ

if __name__=='__main__':
    ok,res,summ=run_checks()
    npass=sum(1 for _,o,_ in res if o)
    print('='*66); print(f"[CHECK] {BASE}  build_ch3s1_v1"); print('='*66)
    for name,o,m in res: print(f"  [{'PASS' if o else 'FAIL'}] {name:14s} | {m}")
    print('-'*66); print(f"  결과: {npass}/8 -> {'OK' if ok else 'NG'}")
    HD=hstr_dir(); stamp=datetime.now().strftime('%Y%m%d%H%M')
    with open(os.path.join(HD,f'{stamp}.txt'),'w',encoding='utf-8') as f:
        f.write(f"[{BASE}] build_ch3s1_v1 {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("목적: 추세봇 uptrend(feat_struct 실시간) 진입 0.3배 '단일룰'의 4년 폴드 견고성(블록CPCV+WF+2024게이트)\n")
        f.write(f"오염검사 {npass}/8 ({'OK' if ok else 'NG'})\n")
        f.write(f"전체: 기준선 ret{summ.get('base_ret')}% MDD{summ.get('base_mdd')}% Calmar{summ.get('base_cal')}\n")
        f.write(f"      0.3룰  ret{summ.get('rule_ret')}% MDD{summ.get('rule_mdd')}% Calmar{summ.get('rule_cal')}\n")
        f.write(f"uptrend거래={summ.get('uptrend_n')} / CPCV폴드={summ.get('cpcv_folds')} MDD개선={summ.get('cpcv_mdd_better')}%\n")
        f.write(f"2024게이트(Calmar유지>=0.85)={summ.get('gate2024')} (cal_keep={summ.get('cal_keep_2024')})\n")
        f.write(f"판정: 룰은 MDD/Calmar 견고개선·2024생존이면 1순위 통과 → 2순위(OPV·n·N 그리드+PBO)로\n")
        f.write(f"MDD-20% 기준. code_sha={summ.get('code_sha')}\n")
    idx=os.path.join(HD,'00WorkHstr_INDEX.txt')
    with open(idx,'a',encoding='utf-8') as f:
        f.write(f"{stamp} | {BASE} | CPCV {npass}/8 | 기준{summ.get('base_ret')}% 룰{summ.get('rule_ret')}% "
                f"MDD{summ.get('base_mdd')}->{summ.get('rule_mdd')} | 2024게이트{summ.get('gate2024')} "
                f"| CPCV MDD개선{summ.get('cpcv_mdd_better')}% | MDD-20%\n")
    print(f"\n[기록] {os.path.join(HD,stamp+'.txt')} / INDEX 추가")
    sys.exit(0 if ok else 2)
