# -*- coding: utf-8 -*-
# [make_risk_matrix.py] Rauto 구조개혁 — 결정 전 위험 시나리오 매트릭스 (세션 260625_01_Rauto_Sys_Reform).
#   선행연구(백테/라이브 실패모드) + Rauto 과거 참사(A~E 전부 실재) 대조. 색=아키텍처 영향.
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
OUT = r"D:\ML\RfRauto\07_Rauto_System\260625_01_Rauto_Sys_Reform"
os.makedirs(OUT, exist_ok=True)

# (id, 발생가능성, 충격, 색, 한줄설명)  색: red=과거실재·최우선 / orange=리팩터신규 / gray=별도실측보정
S = [
    ("S1", 2.9, 5.0, "red",    "S1 중앙 리샘플러 룩어헤드 — 1버그가 전 봇 동시오염(집중형)"),
    ("S2", 4.2, 5.0, "red",    "S2 RautoCEX 체결환상 재발 — '도달=체결' 가정 (과거 +11397%->+39%)"),
    ("S3", 4.7, 4.3, "orange", "S3 리팩터 회귀 — 해시잠금 엔진 추출하다 앵커(+1852%/+827%) 깨짐"),
    ("S4", 3.4, 3.0, "orange", "S4 두 백테경로 불일치 — 벡터(연구) vs 이벤트(라이브) 결과 갈림"),
    ("S5", 2.5, 4.2, "red",    "S5 비용 2레이어 재병합 — 선정4bp+실행 섞임 = '갑/을' 부활"),
    ("S6", 3.7, 4.6, "red",    "S6 챔피언 선발 = 과적합/생존편향 — full표본 성적으로 뽑으면"),
    ("S7", 5.0, 3.0, "gray",   "S7 슬립모델 미보정 — 1m 한계 (실측 안하면 +253<->+1483 추정)"),
    ("S8", 2.2, 4.0, "orange", "S8 이벤트 동시간 순서버그 — 같은봉 진입+스톱·다봇 자본경쟁"),
]
CMAP = {"red": "#e53935", "orange": "#fb8c00", "gray": "#757575"}
CLAB = {"red": "과거 실재·최우선 완화 (Rauto가 이미 데임)", "orange": "리팩터가 새로 만드는 위험", "gray": "별도 실측보정 필요"}

fig, ax = plt.subplots(figsize=(15, 10))
ax.add_patch(plt.Rectangle((3.5, 3.5), 2.0, 2.0, color="#ffcdd2", alpha=0.45, zorder=0))
ax.add_patch(plt.Rectangle((0.5, 0.5), 1.5, 1.5, color="#c8e6c9", alpha=0.4, zorder=0))
ax.text(4.5, 5.32, "위험 집중지대 High-risk", fontsize=11, color="#b71c1c", ha="center", fontweight="bold")

for sid, lk, sv, ck, _ in S:
    ax.scatter(lk, sv, s=560, color=CMAP[ck], edgecolor="black", lw=1.5, zorder=3, alpha=0.93)
    ax.text(lk, sv, sid, fontsize=11.5, color="white", ha="center", va="center", fontweight="bold", zorder=4)

# 색 범례(우상)
for i, ck in enumerate(["red", "orange", "gray"]):
    ax.scatter(3.62, 5.18 - i*0.22, s=150, color=CMAP[ck], edgecolor="black", lw=1.0, zorder=4)
    ax.text(3.74, 5.18 - i*0.22, CLAB[ck], fontsize=9.2, va="center", zorder=4)

# 시나리오 키(좌하 빈 안전지대)
ax.text(0.62, 2.62, "시나리오 (위험 가능성 × 충격):", fontsize=9.6, fontweight="bold", color="#333")
for i, (sid, lk, sv, ck, desc) in enumerate(S):
    ax.text(0.62, 2.40 - i*0.205, desc, fontsize=8.7, color=CMAP[ck], va="center")

ax.set_xlim(0.5, 5.5); ax.set_ylim(0.5, 5.5)
ax.set_xlabel("발생 가능성  Likelihood  (1 낮음 → 5 높음)", fontsize=12, fontweight="bold")
ax.set_ylabel("충격(피해)  Impact  (1 낮음 → 5 치명)", fontsize=12, fontweight="bold")
ax.set_title("Rauto 구조개혁 — 결정 전 위험 시나리오 매트릭스 (선행연구 + 과거참사 대조)\n"
             "Risk scenarios before committing — prior research x Rauto's own past failures", fontsize=13, fontweight="bold")
ax.set_xticks(range(1, 6)); ax.set_yticks(range(1, 6)); ax.grid(alpha=0.3, zorder=0)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "260625_01_Rauto_Sys_Reform_RiskMatrix.png"), dpi=140, bbox_inches="tight")
plt.close(fig)
print("[저장]", os.path.join(OUT, "260625_01_Rauto_Sys_Reform_RiskMatrix.png"))
