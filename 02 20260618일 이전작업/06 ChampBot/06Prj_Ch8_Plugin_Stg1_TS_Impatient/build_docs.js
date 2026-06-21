const fs = require("fs");
const path = require("path");
const G = require("child_process").execSync("npm root -g").toString().trim();
const docx = require(path.join(G, "docx"));
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
        AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType, PageBreak } = docx;

const PKG = __dirname;
const RES = path.join(PKG, "results");
const PLUGINF = path.join(PKG, "plugin", "ts_impatient_plugin.py");
const IMPF = path.join(PKG, "plugin", "bots", "bot_trendstack_impatient.py");

const FONT = "Arial";
const styles = {
  default: { document: { run: { font: FONT, size: 20 } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 30, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 260, after: 140 }, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 24, bold: true, color: "2E5496" }, paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 22, bold: true, color: "333333" }, paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2 } },
  ],
};
const numbering = { config: [
  { reference: "b", levels: [{ level: 0, format: "bullet", text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 560, hanging: 280 } } } }] }] };

const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const P = (t, o = {}) => new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: t, ...o })] });
const B = t => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 40 }, children: [new TextRun(t)] });
const BR = () => new Paragraph({ children: [new PageBreak()] });
function box(lines, fill = "FFF2CC") {
  return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [9360], rows: [
    new TableRow({ children: [new TableCell({ width: { size: 9360, type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 150, right: 150 },
      borders: { top:{style:BorderStyle.SINGLE,size:6,color:"D6B656"}, bottom:{style:BorderStyle.SINGLE,size:6,color:"D6B656"},
                 left:{style:BorderStyle.SINGLE,size:6,color:"D6B656"}, right:{style:BorderStyle.SINGLE,size:6,color:"D6B656"} },
      children: lines.map(l => new Paragraph({ spacing:{after:40}, children:[new TextRun({text:l.t, bold:!!l.b, color:l.c||"000000", size:l.s||20})] })) })] })] });
}
function table(headers, rows, widths) {
  const tot = widths.reduce((a,c)=>a+c,0);
  const bd = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
  const borders = { top: bd, bottom: bd, left: bd, right: bd };
  const hr = new TableRow({ tableHeader:true, children: headers.map((h,i)=> new TableCell({ borders,
    width:{size:widths[i],type:WidthType.DXA}, shading:{fill:"2E5496",type:ShadingType.CLEAR}, margins:{top:60,bottom:60,left:90,right:90},
    children:[new Paragraph({children:[new TextRun({text:h,bold:true,color:"FFFFFF",size:18})]})] })) });
  const drs = rows.map(r => new TableRow({ children: r.map((c,i)=> new TableCell({ borders,
    width:{size:widths[i],type:WidthType.DXA}, margins:{top:50,bottom:50,left:90,right:90},
    children:[new Paragraph({children:[new TextRun({text:String(c),size:18})]})] })) }));
  return new Table({ width:{size:tot,type:WidthType.DXA}, columnWidths:widths, rows:[hr,...drs] });
}
function code(file, title) {
  const out = [H3(title)];
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
  for (const ln of lines)
    out.push(new Paragraph({ spacing:{after:0}, shading:{fill:"F4F4F4",type:ShadingType.CLEAR},
      children:[new TextRun({ text: ln.length?ln:" ", font:"Consolas", size:15 })] }));
  return out;
}
function img(file, w, h, cap) {
  if (!fs.existsSync(file)) return [P("("+path.basename(file)+" 없음)")];
  return [ new Paragraph({ alignment: AlignmentType.CENTER, children:[ new ImageRun({ type:"png",
      data: fs.readFileSync(file), transformation:{width:w,height:h},
      altText:{title:cap,description:cap,name:cap} })] }),
    new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:120}, children:[new TextRun({text:cap,italics:true,size:16,color:"666666"})] }) ];
}

// ===================== HANDOVER =====================
const handover = [];
handover.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{before:600,after:120}, children:[new TextRun({text:"인수인계보고서 (Handover)", bold:true, size:44, color:"1F3864"})] }));
handover.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:60}, children:[new TextRun({text:"06Prj_Ch8_Plugin_Stg1 — TrendStack Impatient(성급) 실행 Plugin", size:26, color:"2E5496"})] }));
handover.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:300}, children:[new TextRun({text:"작성=Claude Code(PC) · 2026-06-15 · 본진 D:\\ML\\Verify", size:18, color:"666666"})] }));
handover.push(box([
  {t:"★ Output of Chat (이 채팅의 핵심 산출물)", b:true, c:"1F3864", s:24},
  {t:"1) 성급(Impatient) TS 실행 Plugin — 진입 지정가 / 청산 시장가. 백테 6관문 통과 후보.", b:true},
  {t:"2) 검증된 알파 후보: 성급TS + 참을성SW (k0.85 · SW 추세장 OFF · 지정가). §9 교체 후보.", b:true},
  {t:"3) 방법론 TIL 7건(Guide v5에 추가) — 특히 '봇 성격별 참을성 정반대 법칙'.", b:true},
  {t:"핵심수치(실비용~8bp, 3년): 성급TS단독 +1368% / MDD -18.3% / Calmar 75 / CPCV표준6 p25+1027%·최악경로+830%.", b:false},
], "E2EFDA"));
handover.push(BR());

handover.push(H1("1. 작업 히스토리"));
handover.push(H2("1.1 작업 파일 리스트 (Plugin + 연구코드 + 결과물)"));
handover.push(table(["분류","파일","목적"], [
  ["Plugin","ts_impatient_plugin.py","성급 TS 실행 plugin(신호+실행프로파일 진입지정가/청산시장가)"],
  ["Plugin-신호","bots/bot_trendstack_impatient.py","성급 신호봇(서브클래스 _step, 피벗대기 제거, 워밍업가드)"],
  ["Plugin-deps","bots/(엔진·poc·regime·contract·paper_engine)","§8 해시락 무수정 의존"],
  ["연구","bt3y_ab.py","3년 A/B(기존 vs 성급) 충실 백테(replay+사후사이징)"],
  ["연구","validate_ab.py","비용 민감도 스윕(4~30bp)+거래당 net R+§9 재현 진단"],
  ["연구","realistic_exec.py / measure_slippage.py","현실 체결모델·실측 슬리피지(타이밍갭≈0)"],
  ["연구","sw_variants.py","SW 3종(참을성/성급/중간)+듀얼 조합 MDD 쿠션"],
  ["연구","optimize_dual.py","듀얼 장세조절(k·ER댐핑) 재최적화 14bp+OOS"],
  ["연구","cpcv_alpha.py","CPCV 표준6(15경로) 과최적합 검증"],
  ["연구","verify_limit_fill.py","7h/8h 지정가 체결률 검증(100%)"],
  ["연구","graph_*.py","비교 그래프 생성(영문 라벨)"],
  ["결과","ledger_*/opt_*/sw_*.csv","거래원장·최적화·SW 변종 결과"],
  ["결과","final_3way.png / sw_compare.png / *.png","비교 그래프"],
], [1400, 3200, 4760]));

handover.push(H2("1.2 파일 명명 규칙"));
handover.push(B("패키지/zip: (Proj)_Ch(회차)_(채팅창명)_Stg(작업번호)_(작업명). 본건=06Prj_Ch8_Plugin_Stg1_TS_Impatient."));
handover.push(B("모든 하위 파일명 영문(한글명=zip 에러). 연구코드=동사_대상.py, 결과=대상.csv/png."));
handover.push(B("인수인계 문서=Handover_06Prj_Ch8_Plugin_stg1.docx / KeyNote_06Prj_Ch8_Plugin_stg1.docx."));

handover.push(H2("1.3 코드 목적 & 신뢰도 검증 방법"));
handover.push(B("신호 동치(live≡replay): bot_trendstack_impatient는 라이브 on_bar 경로와 replay_7h가 거래·R 100% 일치(동치 True) — 워밍업 가드로 초기봉 1거래 불일치 해소."));
handover.push(B("§8 해시 무수정: 엔진/기존봇 5종 바이트 동일 확인(check 19/19). 성급봇은 서브클래스 _step 오버라이드만."));
handover.push(B("백테 충실성: replay로 거래 생성 → 실 OPVnN 사이징·업트렌드숏컷 → 검증된 rauto_paper_engine.resolve_replay(1m MAE·하드스탑·MMR) P&L."));
handover.push(B("과최적합 점검 2중: OOS(2023-24 학습→2025-26 검증 통과) + CPCV 표준6(15경로 p25·최악경로 둘 다 >0)."));
handover.push(B("비용 정직: §7 2레이어(신호 4bp는 거래선정용·P&L 금지 / 실행 14bp). 본건 실비용=진입메이커2bp+청산시장6bp≈8bp."));

handover.push(H2("1.4 결과물 사용법"));
handover.push(B("재현: research_code/ 의 .py를 D:\\ML\\Verify 기준 경로에서 실행(Merged_Data.csv 필요). graph_*.py는 csv 읽어 png 생성."));
handover.push(B("Plugin 사용: plugin/ts_impatient_plugin.py의 make_bot()으로 신호봇 생성, route_signal()로 주문 라우팅 명세 획득(주문모듈이 소비)."));

handover.push(H2("1.5 비망록 — 사용자(캡틴) 강조·약속 사항"));
handover.push(box([
  {t:"· §0 절대선: 월 +10%·매월 양수·MDD -20% 이내. 본 성급TS 단독 -18.3%(실비용)로 충족.", b:false},
  {t:"· §7 비용 2레이어 혼동 금지(캡틴이 매우 강조). 신호엔진 COST 0.0004 변경 금지.", b:true},
  {t:"· 진입=지정가, 청산=시장가 (캡틴 확정 2026-06-15). 7h/8h 긴봉이라 지정가 100% 체결.", b:true},
  {t:"· '성급'은 추세추종에만 약. 평균회귀(SW)엔 독(칼잡기) — 봇 성격별로만 적용.", b:true},
  {t:"· 확정 알파는 반드시 00ALPHA_Confirm_Bot 저장(§3 참조).", b:true},
], "FCE4D6"));
handover.push(P("[참조] 범용 환경·규칙은 Basic_Trading_Environment_Setup.docx(V3.3) 준수: 단일포지션·선보고후작업·미래참조차단·합격기준(전기간+인접TF고원+상위거래제거후 PF+train/test).", {italics:true, size:18}));
handover.push(BR());

handover.push(H1("2. 시스템 아키텍처 · 로직 · 함수/상수 설명"));
handover.push(H2("2.1 전체 아키텍처"));
handover.push(B("1m MarketBar 스트림 → 봇이 7h봉 누적 → 7h 마감 시 _step(신호 상태머신) → Signal(ENTER/EXIT)."));
handover.push(B("ENTER 시 사이징(OPVnN dev배수 + 업트렌드숏컷 feat_struct_8) → size_pct·leverage. 실행=plugin EXEC_PROFILE(진입 지정가/청산 시장가)."));
handover.push(B("청산: trend_flip(슈퍼트렌드 반전) 또는 SL(피보 트레일링 스톱). 본 프로파일은 청산 전부 시장가."));
handover.push(H2("2.2 ★성급(Impatient)의 유일 차이 — 진입 1줄"));
handover.push(box([
  {t:"기존(인내): le = Trend[i]==1 and new_pl and not isnan(lastPH)  (피벗 새 확정 대기)", b:false},
  {t:"성급(분기): le = Trend[i]==1 and not isnan(lastPH) and not isnan(lastPL)  (피벗 대기 제거)", b:true},
  {t:"→ 추세 방향이면 즉시 진입. 청산·SL·사이징·게이트는 전부 동일. + 워밍업 가드(i<6 skip)로 동치 보존.", b:false},
], "DEEBF7"));
handover.push(H2("2.3 주요 함수"));
handover.push(table(["함수","역할"], [
  ["_step(i,arr,sig,dz_oi,eh)","신호 상태머신: 청산검사→피보트레일→진입판정. 성급은 진입조건만 오버라이드"],
  ["compute_signals(df7)","Trend(피벗슈퍼트렌드)·ADX·chop·ATR·ER·bandw·drop·피벗 1회 사전계산(과거봉만)"],
  ["compute_poc / dev_rdir","7h 거래량프로파일 POC, dev=(진입가-POC)/ATR, rdir=-sign(dev) (OPVnN 사이징용)"],
  ["replay_7h","검증용 7h 일괄 리플레이(라이브 on_bar와 동치)"],
  ["resolve_replay(R,mae,fund)","실행엔진 P&L: 정상=R×노출 / 강제청산=−노출×(hsd+COST+|fund|)"],
], [2600, 6760]));
handover.push(H2("2.4 상수/설정"));
handover.push(table(["상수","값","의미"], [
  ["BASE_SIZE_PCT / BASE_LEV","7.0864% / 22","증거금%·레버(EXP 1.559)"],
  ["OPV / NMULT / N_BOOST","0.25 / 0.6 / 1.0","OPVnN dev임계·반대배수·동일배수(§9 확정)"],
  ["gate_er","0.45","OI무덤구간 진입 ER게이트"],
  ["COST(신호) / COST·SLIP(실행)","0.0004 / 0.0014·0.0005","§7 2레이어(혼동금지)"],
  ["EXEC 실비용","~8bp","진입 메이커2 + 청산 테이커6 (지정가/시장가)"],
  ["k_ALLOC / ER댐핑","0.85 / SW추세장OFF","듀얼 재최적(14bp+OOS)"],
], [2600, 2400, 4360]));
handover.push(BR());

handover.push(H1("3. 인수인계 주의점 (점프·미검증 + 알파 저장)"));
handover.push(H2("3.1 확신 없어 검증 필요한 부분"));
handover.push(B("[신뢰15] 메이커/테이커 큐 위치: 지정가가 100% '터치'되나, 실제 메이커 체결 여부는 1분봉으론 불가 → 테스트넷/소액실거래 확인. 단 최악=8bp 이미 통과."));
handover.push(B("[신뢰55] SW의 MDD 쿠션은 모듈(−16.8→−15.5). SW가 현재 라이브 0거래 → 06-19 실가동 확인 필요."));
handover.push(B("[신뢰90] 절대 수익률(+1368% 등)은 레버 복리라 큰 수치 — 부호·CPCV 일관성이 핵심. 라이브가 최종."));
handover.push(B("[주의] §9 +827% vs 본 재구성 차이=경로(stg6 하드스탑 vs 라이브봇 fib트레일). 절대값 직접비교 금지."));
handover.push(B("[점프 경계] 본건은 전표본+OOS+CPCV까지 했으나, 정식 채택은 06-19 라이브 페이퍼 통과 후 캡틴 승인."));
handover.push(H2("3.2 ★알파 저장 (반드시)"));
handover.push(box([
  {t:"이 매매봇/전략(성급 TS 실행 Plugin)은 백테 6관문을 통과한 확정 알파 후보입니다.", b:true, c:"C00000"},
  {t:"최종 채택(06-19 라이브 통과) 시 반드시 아래 폴더에 정리·저장하십시오 (세션 간 유실 방지):", b:true},
  {t:"G:\\내 드라이브\\00AI개발지식DB\\자산관리\\유동자산\\자동매매\\06 ChampBot\\00ALPHA_Confirm_Bot", b:true, c:"C00000"},
], "FCE4D6"));
handover.push(BR());

handover.push(H1("4. 개발 토론 과정 (요약 — 상세는 KeyNote)"));
handover.push(B("ML 강반전 갈아타기(RevSwitch) → N=50 표본부족으로 ML 폐기 → '모델 분기(성급 TS)'로 전환."));
handover.push(B("성급 TS 빌드→동치버그(워밍업) 발견·수정→라이브 31일 +20.67%(vs 기존 +13.65%) 검증→AWS 병렬배포."));
handover.push(B("3년 A/B→비용 스윕(격차 진짜 확인)→SW 3종(성급SW는 역효과)→듀얼 재최적(14bp)→지정가 체결검증→CPCV 통과."));
handover.push(P("→ 각 단계 핵심로직·검증로직은 KeyNote_06Prj_Ch8_Plugin_stg1.docx 에 고딩 수준 + 코드 전문으로 수록.", {italics:true}));
handover.push(...img(path.join(RES,"final_3way.png"), 620, 413, "그림 1. 최종 3종 비교 @ 현실 14bp (TS단독 / 듀얼기본 / 듀얼재최적) — TS단독은 14bp서 -20% 위반, 지정가 8bp면 -18.3%."));
handover.push(BR());

handover.push(H1("5. 다음 채팅 작업 계획"));
handover.push(box([{t:"기준점 = Output of Chat(맨 위 박스). 다음 작업은 이를 출발점으로 잡는다.", b:true}], "E2EFDA"));
handover.push(B("1순위: 06-19 공식 1주 페이퍼 종료 → §5 템플릿 7일 보고. 성급TS(분기, AWS 가동중) vs 기존 직접비교, SW 실가동 확인."));
handover.push(B("2순위: 라이브/테스트넷에서 지정가 메이커 체결률·실슬리피지 로깅(주문모듈 = LiveTransition 체크리스트 B)."));
handover.push(B("3순위: '성급' 확장 알파 연구(부분익절·재진입·멀티TF·강신호 게이팅) — 미검증, 별도 사이클."));
handover.push(B("4순위: 듀얼 재최적 config(k0.85/SW추세OFF) CPCV 정식 스탬프 후 §9 교체 검토."));

handover.push(H1("6. 다음 채팅 시작 시 비판적으로 검토할 사항"));
handover.push(B("절대 수익률을 인용하지 말 것(레버복리 과대). PF·CPCV p25·MDD로만 판단."));
handover.push(B("성급TS 단독 채택은 지정가(메이커) 전제. 시장가 진입으로 바뀌면 14bp→-20% 위반 재확인 필요."));
handover.push(B("SW가 라이브에서 실제 거래하는지 — 0거래면 듀얼 쿠션 무의미, TS 단독+레버하향 대안 검토."));
handover.push(B("CPCV 절대수치(+1027%)는 MDD 무제약 복리라 부풀려짐 — 부호/일관성만 채택근거."));

handover.push(H1("부록 A. 신뢰도 점수표"));
handover.push(table(["항목","신뢰도","근거"], [
  ["성급>기존 (전 연도·장세·롱숏)","95","3년 A/B, 라이브31일 동방향"],
  ["성급 엣지 견고(과최적합 아님)","90","CPCV 표준6 p25·최악경로 >0 (4·8bp), OOS 통과"],
  ["지정가 100% 체결(7h/8h)","95","verify_limit_fill 716/93건 100%"],
  ["성급TS 단독 MDD -18.3% (실8bp)","90","resolve_replay 1m MAE, -20% 이내"],
  ["SW는 참을성 유지(성급SW 역효과)","90","SW 3종, 성급SW 2026 PF0.77"],
  ["SW MDD 쿠션","55","듀얼 -16.8→-15.5, SW 라이브 0거래라 미실증"],
  ["메이커 실체결(저비용)","15","1분봉 한계, 테스트넷 필요"],
  ["라이브 최종 성과","15","06-19 페이퍼 대기"],
], [4200, 1200, 3960]));
handover.push(P("신뢰도 척도: 95=직접측정 / 55=통계추론 / 15=가설 / 0=모름.", {italics:true, size:18}));
handover.push(H1("부록 B. Key 파일 리스트"));
handover.push(B("Plugin: ts_impatient_plugin.py + bots/(7종)"));
handover.push(B("연구코드 20종 + 결과물 csv/png (research_code/, results/)"));
handover.push(B("KeyNote_06Prj_Ch8_Plugin_stg1.docx (코드 전문 수록)"));
handover.push(B("Guide_AlphaDiscovery_Method_v5.docx (TIL 7건 추가)"));
handover.push(B("Hstr_Ver_Up_TrendStack_Bot.zip (데이터추출 코드+데이터)"));

const docH = new Document({ styles, numbering, sections:[{ properties:{ page:{ size:{width:12240,height:15840}, margin:{top:1200,right:1440,bottom:1200,left:1440} } }, children: handover }] });
Packer.toBuffer(docH).then(b => { fs.writeFileSync(path.join(PKG,"docs","Handover_06Prj_Ch8_Plugin_stg1.docx"), b); console.log("Handover OK", b.length); });

// ===================== KEYNOTE =====================
const kn = [];
kn.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{before:600,after:120}, children:[new TextRun({text:"KeyNote", bold:true, size:44, color:"1F3864"})] }));
kn.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:60}, children:[new TextRun({text:"06Prj_Ch8_Plugin_Stg1 — 핵심 로직·검증 로직 상세 (고딩 설명 + 코드 전문)", size:24, color:"2E5496"})] }));
kn.push(new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:240}, children:[new TextRun({text:"2026-06-15 · Claude Code(PC)", size:18, color:"666666"})] }));

kn.push(H1("1. 핵심 로직 — '성급(Impatient)'이란"));
kn.push(P("고딩 설명: 추세추종 봇은 '추세가 생겼다'를 확인하려고 피벗(저점/고점)이 새로 찍힐 때까지 기다립니다(인내). 그 대기가 평균 9봉=63시간. 그 사이 가격은 이미 가버립니다. '성급'은 그 대기를 없애고 추세 방향이면 바로 들어갑니다 → 추세 초반을 더 먹습니다."));
kn.push(P("왜 추세추종엔 약인가: 추세는 '빨리 타는' 게 이득이라 일찍 진입이 좋습니다. 반대로 평균회귀(SW)는 '떨어지다 멈춘 걸 확인'하고 사야 안전한데, 성급하면 떨어지는 칼을 잡습니다 → SW엔 독. (봇 성격별 정반대 법칙)"));

kn.push(H1("2. 검증 로직 — 6관문"));
kn.push(B("① 동치(live≡replay) True: 라이브 경로와 일괄 리플레이가 같은 거래. 워밍업 가드로 초기봉 1건 불일치 해소."));
kn.push(B("② 비용 민감도 스윕(4~30bp): 전 구간 성급 우위 → 비용/빈도 아티팩트 아님. 거래당 net R(빈도무관)도 우월."));
kn.push(B("③ SW 3종: 참을성SW만 매년 흑자, 성급SW는 2026 PF0.77(칼잡기), 중간 최악 → SW는 참을성."));
kn.push(B("④ 듀얼 재최적 14bp+OOS: k0.85/SW추세OFF → -17.9%. 학습→검증 통과(과최적합 아님)."));
kn.push(B("⑤ 지정가 체결 100%(7h/8h 긴봉) — 욕심(passive)은 역선택."));
kn.push(B("⑥ CPCV 표준6(15경로): p25+1027%·최악경로+830%(4bp), +841%/+681%(8bp) — 전 경로 흑자."));
kn.push(...img(path.join(RES,"sw_compare.png"), 620, 360, "그림. SW 3종 — 성급/중간은 MDD 악화·PF 저하(평균회귀에 성급은 독)."));
kn.push(BR());

kn.push(H1("3. 코드 전문 — Plugin 모듈"));
kn.push(...code(PLUGINF, "3.1 ts_impatient_plugin.py"));
kn.push(BR());
kn.push(...code(IMPF, "3.2 bot_trendstack_impatient.py (성급 신호봇 — 서브클래스 _step)"));

const docK = new Document({ styles, numbering, sections:[{ properties:{ page:{ size:{width:12240,height:15840}, margin:{top:1200,right:1440,bottom:1200,left:1440} } }, children: kn }] });
Packer.toBuffer(docK).then(b => { fs.writeFileSync(path.join(PKG,"docs","KeyNote_06Prj_Ch8_Plugin_stg1.docx"), b); console.log("KeyNote OK", b.length); });
