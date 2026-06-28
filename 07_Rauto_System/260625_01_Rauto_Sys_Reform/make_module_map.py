# -*- coding: utf-8 -*-
# [make_module_map.py] Rauto 구조개혁 모듈맵 고딩보고 그래프 (세션 260625_01_Rauto_Sys_Reform, 캡틴 최종승인용).
#   캡틴 결정 반영: ③중앙1m→봇별TF·룩어헤드차단 최우선 / ④RautoCEX부터 떼어내 앵커일치 후 점진.
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager as fm
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
OUT = r"D:\ML\RfRauto\07_Rauto_System\260625_01_Rauto_Sys_Reform"
os.makedirs(OUT, exist_ok=True)

fig, ax = plt.subplots(figsize=(13.5, 17))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")


def box(x, y, w, h, color, ec="#333", lw=1.6, alpha=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.4",
                                fc=color, ec=ec, lw=lw, alpha=alpha, zorder=2))


def txt(x, y, s, size=11, w="normal", c="#111", ha="left", va="top"):
    ax.text(x, y, s, fontsize=size, fontweight=w, color=c, ha=ha, va=va, zorder=3)


def arrow(x1, y1, x2, y2, c="#1565c0", lw=2.4, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=22,
                                 color=c, lw=lw, zorder=1, shrinkA=2, shrinkB=2))


ax.text(50, 98.3, "Rauto 구조개혁 모듈맵  ·  Rauto System Module Map", fontsize=17, fontweight="bold", ha="center")
ax.text(50, 96.2, "세션 260625_01_Rauto_Sys_Reform  ·  기능을 나눠 '갑/을 비용 재확인'을 끝낸다", fontsize=11, ha="center", color="#555")

# ── [0] 관제센터 ──
box(6, 84.5, 88, 9.5, "#e3f2fd")
txt(8, 93.4, "[0] 관제센터  Control Center", 13, "bold", "#0d47a1")
txt(8, 90.8, "· 바이낸스 API 수신 → ★중앙에서 1분봉(1m) 1개로 만든다 (데이터 단일출처)", 11)
txt(8, 88.6, "· 슬롯에 매매봇 로딩 → 경쟁시켜 챔피언 관리", 11)
# 룩어헤드 게이트
box(52, 85.2, 41, 4.0, "#ffcdd2", ec="#c62828", lw=2.0)
txt(53, 88.6, "★미래참조차단 게이트 (룩어헤드 OFF)", 10.5, "bold", "#b71c1c")
txt(53, 86.6, "봉 '마감 후에만' 전달 (4h봉은 08:00에야 공개)", 9.8, "normal", "#b71c1c")

# ── [1] 매매신호 (봇 A/B) ──
box(6, 69, 41, 11.5, "#e8f5e9")
txt(8, 79.6, "[1] 매매신호 봇A  Signal Bot A", 12.5, "bold", "#1b5e20")
txt(8, 77.0, "· 1m 받아 → 자기 TF(예 4h)로 변환", 10.5)
txt(8, 75.0, "· 장세판별(레짐) → 진입/청산 신호", 10.5)
txt(8, 72.4, "· 출력 = Signal 객체(방향·SL·이유)\n  ※봇은 '신호만' (비용 모름)", 10, "normal", "#444")

box(53, 69, 41, 11.5, "#e8f5e9")
txt(55, 79.6, "[1] 매매신호 봇B  Signal Bot B", 12.5, "bold", "#1b5e20")
txt(55, 77.0, "· 같은 1m → 봇B의 TF로 변환", 10.5)
txt(55, 75.0, "· 봇마다 다른 전략·TF, 같은 데이터", 10.5)
txt(55, 72.4, "· 슬롯에서 챔피언과 경쟁", 10)

# ── [2] 매매결정 ──
box(6, 54, 88, 11, "#fff8e1")
txt(8, 64.1, "[2] 매매결정  Rauto 두뇌  Decision / Portfolio", 13, "bold", "#e65100")
txt(8, 61.4, "· 봇 신호들을 취합 → 진입/청산 '결정'은 Rauto가 한다 (봇은 제안만)", 11)
txt(8, 59.2, "· 사이징 · 듀얼 k배분 · ★MDD-20 리스크게이트 · 챔피언 선발", 11)
txt(8, 56.6, "· 출력 = 주문(Order): 방향·수량·레버·지정가/시장가 의도", 10.5, "normal", "#444")

# ── [3] RautoCEX (1순위) ──
box(6, 33.5, 88, 17.5, "#ede7f6", ec="#4527a0", lw=2.4)
txt(8, 49.9, "[3] ★RautoCEX  체결 + 비용  (★착수 1순위 — 먼저 떼어낸다)", 13, "bold", "#311b92")
txt(8, 47.3, "거래소를 '독립 모듈'로. 비용·체결 판단을 여기 '한 곳'에만 둔다 → 봇 고쳐도 비용 재확인 끝.", 10.5, "normal", "#333")
box(9, 38.2, 40, 8.0, "#d1c4e9")
txt(10.5, 45.2, "체결 판단", 10.5, "bold", "#311b92")
txt(10.5, 43.2, "· FillModel: 지정가(메이커)/시장가(테이커)\n  · 그 레벨에 1m 도달? → 체결/미체결 사전판정\n· SlippageModel: 시장가만 슬립(스프+호가충격)", 9.5)
box(51, 38.2, 42, 8.0, "#d1c4e9")
txt(52.5, 45.2, "비용·마진", 10.5, "bold", "#311b92")
txt(52.5, 43.2, "· FeeModel: maker2 / taker4 / 펀딩\n· MarginModel: 격리마진·유지증거금·강제청산\n  (rauto_paper_engine 이미 있음)", 9.5)
box(9, 34.3, 84, 3.2, "#b39ddb")
txt(10.5, 36.9, "[Sim 백테 모드]  <->  [Live 실거래소 모드]  : 같은 인터페이스, 실거래 땐 Sim 끄고 거래소 체결/비용 따름", 10, "bold", "#311b92")

# ── [4] 결과분석 ──
box(6, 24, 88, 7.5, "#e0f2f1")
txt(8, 30.6, "[4] 결과분석  Back2TV  (이미 완성)", 12.5, "bold", "#00695c")
txt(8, 28.0, "· 원장 → 분석·Pine·CPCV·사례6선. 실거래용 실시간 모니터링은 별도 재구성.", 10.5)

# 화살표 (흐름)
arrow(28, 84.5, 26, 80.5); arrow(72, 84.5, 74, 80.5)
ax.text(20.5, 82.6, "1m 전달", fontsize=9, color="#1565c0", ha="center")
arrow(26, 69, 40, 65.2, c="#2e7d32"); arrow(74, 69, 60, 65.2, c="#2e7d32")
ax.text(50, 67.0, "Signal", fontsize=9.5, color="#2e7d32", ha="center", fontweight="bold")
arrow(50, 54, 50, 51.2, c="#e65100"); ax.text(56, 52.5, "Order(주문)", fontsize=9.5, color="#e65100", ha="center", fontweight="bold")
arrow(50, 33.5, 50, 31.6, c="#4527a0"); ax.text(58, 32.5, "실현손익·원장", fontsize=9.5, color="#4527a0", ha="center", fontweight="bold")

# ── 착수 순서 strip (④) ──
box(6, 11.5, 88, 9.5, "#fce4ec", ec="#ad1457", lw=2.0)
txt(8, 20.1, "착수 순서 (④ 점진 — 한 번에 다 안 한다)", 12.5, "bold", "#880e4f")
steps = ["①RautoCEX 떼기\n비용 4곳→1곳\n앵커 +1852% 재현", "②중앙 1m +\n룩어헤드 게이트", "③신호/결정 분리\nrun_strategy 순화", "④관제센터\n슬롯·챔피언"]
xs = [9, 31, 53, 75]
for i, (sx, s) in enumerate(zip(xs, steps)):
    box(sx, 12.6, 19, 5.4, "#f8bbd0")
    txt(sx + 9.5, 17.4, s, 9.3, "bold", "#880e4f", ha="center")
    if i < 3: arrow(sx + 19, 15.3, xs[i+1], 15.3, c="#ad1457", lw=2.0)
txt(8, 12.2, "★각 단계: '같은 config → 같은 수익'(앵커 회귀테스트 §15.2) 통과해야 다음으로.", 9.6, "bold", "#880e4f")

# ── §7 2레이어 경고 callout ──
box(6, 2.5, 88, 6.5, "#fff3e0", ec="#ef6c00", lw=1.8)
txt(8, 8.1, "[주의] 절대 지킬 것 (§7 비용 2레이어) — 이걸 어기면 '갑/을 혼동'이 다시 살아난다", 11.5, "bold", "#e65100")
txt(8, 5.6, "· 신호선정 비용 4bp(모듈1, '어느 봉에 진입하나' 고르는 임계값, P&L 아님)  ≠  실행 비용(RautoCEX, 진짜 P&L).", 10)
txt(8, 3.6, "· 둘은 '다른 것'. RautoCEX로 모으는 건 실행비용만. 이름을 selection_cost vs execution_cost로 갈라 박는다.", 10)

fig.savefig(os.path.join(OUT, "260625_01_Rauto_Sys_Reform_ModuleMap.png"), dpi=140, bbox_inches="tight")
plt.close(fig)
print("[저장]", os.path.join(OUT, "260625_01_Rauto_Sys_Reform_ModuleMap.png"))
