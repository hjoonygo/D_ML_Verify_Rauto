# -*- coding: utf-8 -*-
# [make_fib_explain.py] 피보나치 스텝업 청산 고딩설명 그래프(한국어 라벨, 맑은 고딕).
#   상단: 개념 도식 — 롱 진입(반전기대)→눌림목마다 SL 계단식 상향→추세 끝까지.
#   하단: 같은 흐름서 3% 플랫 트레일은 정상 눌림목에 '털리고', 피보는 구조(눌림목)에 묶여 끝까지 탄다.
#   ※ 실제 데이터 검증수치는 콘솔에 별도 출력(이 그림은 '원리' 설명용).
import os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # ── 이상적 가격경로: 하락→반전 진입→상승(눌림목 3회=higher low)→천장→하락(청산) ──
    x = np.arange(40)
    pts = [(0,100),(4,94),(8,90),(12,103),(15,99),(20,114),(23,109),(28,126),(31,121),(35,138),(39,128)]
    px = np.interp(x, [p[0] for p in pts], [p[1] for p in pts])
    rng = np.random.RandomState(7); px = px + rng.randn(40)*0.4

    entry_i = 8; entry = px[entry_i]
    dips = [(15,99),(23,109),(31,121)]   # 눌림목(higher low) = 직전 고점 이후 되돌림 저점
    peaks_before = [103,114,126]         # 각 눌림목 직전 고점(lastPH 역할)
    fibr = [0.3,0.5,0.6]
    # 피보 스텝업 SL: 각 눌림목서 cand = lastPH - r*(lastPH - dip)
    sl_steps = []
    sl = entry*0.985
    for (di,dl),ph,r in zip(dips, peaks_before, fibr):
        cand = ph - r*(ph - dl); sl = max(sl, cand); sl_steps.append((di, sl))

    fig,(ax,ax2)=plt.subplots(2,1,figsize=(13,10),sharex=True,gridspec_kw={'height_ratios':[1,1]})

    # ── 상단: 피보 스텝업 원리 ──
    ax.plot(x,px,color="#222",lw=2,label="가격",zorder=3)
    ax.scatter([entry_i],[entry],marker="^",s=320,color="royalblue",zorder=6)
    ax.annotate("① 진입\n(하락→반전 기대 롱)",(entry_i,entry),xytext=(entry_i-3.5,entry-9),
                color="royalblue",fontsize=11,fontweight="bold",ha="center",
                arrowprops=dict(arrowstyle="->",color="royalblue"))
    # 초기 SL
    ax.hlines(entry*0.985, entry_i, dips[0][0], color="orange",lw=2,ls="--")
    ax.annotate("② 초기 SL\n(첫 눌림목 전까지)",(entry_i+0.3,entry*0.985-3),color="darkorange",fontsize=9.5)
    prev_x, prev_sl = entry_i, entry*0.985
    for k,((di,dl),(_,slv),r) in enumerate(zip(dips, sl_steps, fibr),1):
        ax.scatter([di],[dl],marker="o",s=160,color="crimson",zorder=6)
        ax.annotate(f"눌림목{k}\n(직전저점)",(di,dl),xytext=(di,dl-8),color="crimson",fontsize=10,
                    ha="center",fontweight="bold",arrowprops=dict(arrowstyle="->",color="crimson"))
        ax.hlines(prev_sl, prev_x, di, color="green",lw=2.6,zorder=4)
        ax.vlines(di, prev_sl, slv, color="green",lw=2.6,zorder=4)
        ax.annotate(f"③ SL 스텝업↑\n피보 {r}",(di,slv),xytext=(di+0.4,slv+1.5),color="green",fontsize=9.5,fontweight="bold")
        prev_x, prev_sl = di, slv
    ax.hlines(prev_sl, prev_x, 39, color="green",lw=2.6,label="피보 스텝업 SL",zorder=4)
    ax.scatter([39],[px[39]],marker="v",s=320,color="black",zorder=6)
    ax.annotate("④ 청산\n(추세 꺾일 때\n=끝까지 발라먹기)",(39,px[39]),xytext=(34,px[39]+3),color="black",fontsize=10.5,fontweight="bold")
    ax.set_title("피보나치 스텝업 청산의 원리 — 눌림목마다 SL을 계단식으로 올려 추세를 끝까지 탄다",fontsize=14,fontweight="bold")
    ax.set_ylabel("가격"); ax.legend(loc="upper left",fontsize=10); ax.grid(alpha=0.25)

    # ── 하단: 피보 vs 3% 플랫 트레일 (왜 비교가 안 되나) ──
    ax2.plot(x,px,color="#222",lw=2,label="가격",zorder=3)
    # 3% 플랫 트레일: 고점 대비 -3%
    hwm=entry; flat=[]
    for j in range(entry_i,40):
        hwm=max(hwm,px[j]); flat.append(hwm*0.97)
    fx=list(range(entry_i,40))
    ax2.plot(fx,flat,color="purple",lw=2,ls="--",label="3% 플랫 트레일 SL",zorder=4)
    # 3% 트레일이 처음 깨지는 지점(눌림목에서 가격<flat)
    shake=None
    for idx,j in enumerate(fx):
        if px[j] < flat[idx]: shake=j; break
    if shake is not None:
        ax2.scatter([shake],[px[shake]],marker="X",s=300,color="red",zorder=7)
        ax2.annotate("3% 트레일은\n정상 눌림목에 '털림'\n(추세 초반 손절)",(shake,px[shake]),xytext=(shake-1,px[shake]+8),
                     color="red",fontsize=10.5,fontweight="bold",ha="center",arrowprops=dict(arrowstyle="->",color="red"))
    # 피보 SL(계단) 재표시
    pxs=[entry_i]; pys=[entry*0.985]
    for (di,_),(_,slv) in zip(dips,sl_steps): pxs+=[di,di]; pys+=[pys[-1],slv]
    pxs.append(39); pys.append(pys[-1])
    ax2.plot(pxs,pys,color="green",lw=2.6,label="피보 스텝업 SL",zorder=5)
    ax2.scatter([39],[px[39]],marker="v",s=260,color="black",zorder=6)
    ax2.annotate("피보는 눌림목 구조에 묶여\n안 털리고 끝까지 탄다",(39,px[39]),xytext=(30,px[39]-12),
                 color="green",fontsize=10.5,fontweight="bold")
    ax2.set_title("비교: 3% 플랫 트레일(보라)은 정상 눌림목에 조기 손절 / 피보 스텝업(초록)은 추세 끝까지",fontsize=12.5,fontweight="bold")
    ax2.set_ylabel("가격"); ax2.set_xlabel("시간 →"); ax2.legend(loc="upper left",fontsize=10); ax2.grid(alpha=0.25)

    plt.tight_layout(); out=os.path.join(HERE,"fib_stepup_explain.png"); plt.savefig(out,dpi=120)
    print(f"[그래프 저장] {out}")


if __name__ == "__main__":
    main()
