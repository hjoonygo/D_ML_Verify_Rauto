const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType,
  TableOfContents, PageBreak } = require('docx');

const FONT = "Malgun Gothic";
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const HEAD_FILL = "1F4E79", HEAD_TXT = "FFFFFF";

function H1(t){ return new Paragraph({ heading: HeadingLevel.HEADING_1, children:[new TextRun(t)] }); }
function H2(t){ return new Paragraph({ heading: HeadingLevel.HEADING_2, children:[new TextRun(t)] }); }
function P(t, opt={}){ return new Paragraph({ spacing:{after:80}, children:[new TextRun({text:t, ...opt})] }); }
function B(t){ return new Paragraph({ numbering:{reference:"b", level:0}, spacing:{after:40}, children:[new TextRun(t)] }); }
function cell(t, w, {hdr=false, fill=null, bold=false}={}){
  return new TableCell({ borders, width:{size:w, type:WidthType.DXA},
    shading: (hdr||fill)?{fill: hdr?HEAD_FILL:fill, type:ShadingType.CLEAR}:undefined,
    margins:{top:60,bottom:60,left:110,right:110},
    children:[new Paragraph({children:[new TextRun({text:t, bold:hdr||bold, color:hdr?HEAD_TXT:undefined, size:19})]})] });
}
function table(cols, rows){
  const total = cols.reduce((a,b)=>a+b.w,0);
  const head = new TableRow({ tableHeader:true, children: cols.map(c=>cell(c.t, c.w, {hdr:true})) });
  const body = rows.map(r=> new TableRow({ children: r.map((t,i)=>cell(t, cols[i].w)) }));
  return new Table({ width:{size:total,type:WidthType.DXA}, columnWidths: cols.map(c=>c.w), rows:[head,...body] });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id:"Heading1", name:"Heading 1", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{size:30, bold:true, font:FONT, color:"1F4E79"},
        paragraph:{spacing:{before:260, after:140}, outlineLevel:0,
          border:{bottom:{style:BorderStyle.SINGLE, size:6, color:"1F4E79", space:2}}} },
      { id:"Heading2", name:"Heading 2", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{size:24, bold:true, font:FONT, color:"2E5E8C"},
        paragraph:{spacing:{before:160, after:90}, outlineLevel:1} },
    ]
  },
  numbering: { config: [
    { reference:"b", levels:[{level:0, format:LevelFormat.BULLET, text:"•", alignment:AlignmentType.LEFT,
      style:{paragraph:{indent:{left:560, hanging:260}}}}] },
  ]},
  sections: [{
    properties: { page: { size:{width:12240, height:15840}, margin:{top:1300,right:1300,bottom:1300,left:1300} } },
    children: [
      new Paragraph({ spacing:{after:60}, children:[new TextRun({text:"Rauto 인수인계보고서", bold:true, size:40, color:"1F4E79"})] }),
      new Paragraph({ spacing:{after:40}, children:[new TextRun({text:"Live Control App & AWS 운영 인프라 구축", size:26, color:"2E5E8C"})] }),
      new Paragraph({ spacing:{after:200}, children:[new TextRun({text:"07Prj_Rauto_Phone · 2026-06-20 · Captain Gho HyoungJoon · 작성 Claude(Opus)", size:19, color:"666666"})] }),
      new TableOfContents("목차", { hyperlink:true, headingStyleRange:"1-2" }),
      new Paragraph({ children:[new PageBreak()] }),

      // 1. Output of Chat
      H1("1. Output of Chat — 이번 세션 핵심 산출"),
      P("한 줄: “전략은 됐다. 이제 안 죽는 운영을 만든다.” 알파 사냥에서 운영 안정성으로 무게중심을 옮긴 세션.", {bold:true}),
      B("운영 전략 전환 확정: 위험순위 = 상태불일치+주문중복 > 해킹. 전략 30% / 운영 70%."),
      B("Rauto Control App을 b25 → b33로 대폭 강화: RBAC·인증·시크릿파일·토큰만료, Bot로딩·슬롯제거·녹색R(실거래인증), 텍스트선택차단, self-locating 서버."),
      B("AWS 운영 인프라 확립: NSSM 서비스(창 없음·재부팅 생존), ★SSH 직접접속 구축 — Claude가 캡틴 PC에서 AWS를 직접 진단·수정·배포."),
      B("2대 치명 버그를 SSH로 직접 수정(인코딩 크래시·AppDirectory 경로깨짐) + 중복R3 슬롯버그 수정."),
      B("확정 알파 동결 재확인(챔피언/CVD 무변경). CVD 변형(누적/연속/윈도우) 검증 = 교체 무의미."),

      // 2. 운영 전략 전환
      H1("2. 운영 전략 전환 (ChatGPT 다라운드 토론 결론)"),
      P("ChatGPT와 다라운드 토론 후 수렴한 운영 설계 원칙(전부 Work Order에 박제):"),
      B("거래소 = 항상 진실(SoT). 재시작 시 로컬 버리고 거래소서 포지션 재구축(State Recovery)."),
      B("연속손실 halt 폐기 → Expectancy Drift Monitor(우리 승률34/손익비3.7 추세봇엔 연패가 정상동작). 우리 36mo 데이터로 입증."),
      B("자동청산 = 고아/반대 포지션만. 수량 drift = 알림+정지. 레버 하드캡 24(전략 22 보존, 버그만 차단)."),
      B("Idempotency = Binance newClientOrderId 네이티브. 멱등 재시도, 중복주문 0."),
      B("★서버 다운 시 안전 = 거래소에 상시 STOP(트레일링) 거치 — 봇/서버/폰 다 죽어도 거래소가 청산(라이브 단계 구현)."),

      // 3. 확정 알파 동결
      H1("3. 확정 알파 — 동결 (변경 시 CPCV 재검증 + 승인)"),
      table(
        [{t:"항목",w:2600},{t:"내용",w:6760}],
        [
          ["챔피언 (성급왕TS)","+11,397% / MDD-17.3% / 668거래 / 승률34% / PF1.90 / 손익비3.69 (§15 4봇 무변경)"],
          ["CVD 알파","롤링 7h 순테이커 흡수 — 동결. 누적/연속/다른윈도우 전부 검증 → 교체 무의미."],
          ["듀얼/CVD 변종","R3/R4 듀얼, R5/R6/R7 CVD 페이퍼 가동 중(검증값 유지)."],
        ]
      ),

      // 4. Control App 기능
      H1("4. Rauto Control App — 신규 기능 (b33)"),
      table(
        [{t:"기능",w:2400},{t:"내용",w:5260},{t:"상태",w:1700}],
        [
          ["RBAC + 인증","Bearer 토큰→역할(admin/view), 서버단 403, 토큰 만료일, 감사로그, PII 마스킹(수익률공개/금액숨김)","완료"],
          ["시크릿 파일","env 우선 + 없으면 rauto_secrets.txt(Gmail·텔레그램·토큰). setx 상속함정 영구회피","완료"],
          ["Bot로딩","AWS 봇 레지스트리 목록 → 선택 → 빈 슬롯 로딩(/load)","완료"],
          ["슬롯제거","선택 슬롯의 실제 폴더 기준 제거. 챔피언+실거래중이면 차단(긴급중지 먼저)","완료"],
          ["녹색 R","러너 첫줄 RAUTO_LIVE_CERTIFIED 마커 = 실거래 인증봇만 실거래 허용·표시","완료"],
          ["텍스트선택 차단","길게눌러 선택 시 잘라내기/복사 안 뜸(user-select:none)","완료"],
          ["self-locating","어느 폴더서 실행해도 repo·상태·데이터 자동탐색(하드코딩 제거)","완료"],
          ["이메일/텔레그램","챔피언 성과 동시 발송(종합표+거래내역)","완료"],
        ]
      ),

      // 5. AWS 인프라
      H1("5. AWS 배포 인프라 & 원격 운영"),
      H2("서비스화 (창 없이 상시·재부팅 생존)"),
      B("RautoControl(대시보드+봇 autoload) · DautoCollector(가격수집) = NSSM 서비스, AUTO_START."),
      B("sshd(OpenSSH) · Tailscale = AUTO_START. → AWS 재부팅 시 전부 자동 복구(사람 손 0)."),
      H2("★SSH 직접접속 (이번 세션의 최대 인프라 성과)"),
      B("OpenSSH 서버를 AWS에 설치 + Claude 공개키 등록 → 비번 없이 접속."),
      B("주소: administrator@ec2amaz-cor6gpg.tail305e55.ts.net · 키: ~/.ssh/rauto_aws (캡틴 PC)."),
      B("→ Claude가 캡틴 PC 터미널로 AWS를 직접: 코드 배포(scp)·서비스 재시작·로그·진단·수정. 받아치기 relay 종료."),
      B("통제권: 키는 캡틴 PC에만. 차단 = AWS authorized_keys 줄 삭제 or Stop-Service sshd. 위험/되돌리기 어려운 건 사전확인."),
      H2("재부팅 연속성"),
      B("AWS 재부팅: 완전 자동(서비스·봇·접속 다 자동시작)."),
      B("PC 재부팅: 인프라(키·Tailscale) 자동 유지. 단 Claude 대화 세션은 재시작 — 메모리·INDEX·STATE로 이어받음(재설정 0)."),

      // 6. 버그·검증
      H1("6. 검증 · 버그 수정 (신뢰)"),
      table(
        [{t:"증상",w:2400},{t:"원인",w:4760},{t:"수정",w:2200}],
        [
          ["서비스가 즉시 정지","control_server의 ★·한글 print가 서비스 stdout=cp1252서 UnicodeEncodeError 크래시","sys.stdout/stderr.reconfigure(utf-8) — 코드 자체로 보장"],
          ["NSSM 프로세스 못띄움","배치 AppDirectory \"%~dp0\"가 끝 백슬래시+따옴표로 'C:\\Temp\"'(잘못된경로)","\"%~dp0.\" 로 교정"],
          ["슬롯제거 중복 안됨","R3가 폴더3·4 양쪽에 같은이름 — removeSlot이 이름→폴더3만 삭제","aggregate가 _folder 태그 + removeSlot이 폴더기준 + 로딩시 슬롯번호 폴더맞춤"],
          ["폰 옛화면 고착","서비스워커 sw.js 캐시(rauto-v25)가 옛 대시보드 서빙","캐시버전 v33으로 올려 자동갱신"],
        ]
      ),
      P("CVD 변형 검증(궁금증): 누적/연속 CVD raw=최악(IC-0.035·MDD-27.6%), 다른윈도우도 노이즈 — 롤7h 동결 확정.", {size:19}),

      // 7. 미결·다음
      H1("7. 미결 · 다음 (Work Order 요약)"),
      H2("7/1 도쿄 소액 실거래 전 MUST"),
      B("LiveExecutor 구축(현재 주문코드 0): State Recovery → Order 멱등 → Intent Log → Shadow Ledger+Reconciliation → Risk 하드캡 → Expectancy Drift Monitor."),
      B("★서버다운 안전 = 거래소 STOP(고정 or 트레일링 콜백≥10bp) 상시 거치 + 독립 하트비트."),
      B("NSSM 서비스(완료) + 테스트넷 1일 + 거래소 서브계정 + API키(출금차단·IP화이트=Elastic IP). 시드 300 USDT, 챔피언 1봇부터."),
      H2("법률 게이트 (유료 서비스 개시 전 필수)"),
      B("지인 수익 30% 분배 = 한국 자본시장법상 무등록 투자일임업 위험(형사). → 금융 전문 변호사 검토 + Binance 공식 카피트레이딩(거래소 중개) 경로."),
      H2("지인 배포 (신뢰·접근성)"),
      B("60대 카톡 사용자 기준. 신뢰 = 거래소(Binance)가 증인: 공개프로필 + 읽기전용 API 실데이터. 접근성 = 공개 성과페이지(push) 링크(앱설치0). 단 실거래(7/1) 후 진짜 증명."),

      // 산출물 위치
      H1("8. 산출물 위치"),
      table(
        [{t:"산출물",w:3400},{t:"위치",w:5960}],
        [
          ["배포본","D:\\ML\\Verify\\07 Rauto\\Rauto_Control_b33_Deploy.zip"],
          ["AWS 가동본","C:\\Temp\\ (RautoControl 서비스) · 봇 = C:\\RautoRepo / C:\\Rauto1~7"],
          ["Work Order","D:\\ML\\Verify\\07 Rauto\\Rauto_WorkOrder_PreLive_MustFix.txt"],
          ["마스터계획·데이터시트","D:\\ML\\Verify\\07 Rauto\\Rauto_LiveOps_Master_Plan.txt · Rauto_Validation_Datasheet_for_ChatGPT.txt"],
          ["시간순 기록","D:\\ML\\Verify\\00WorkHstr\\00WorkHstr_INDEX.txt"],
          ["규칙·메모리","CLAUDE.md(§1 self-locating 추가) · memory\\ (self-locating·context-first 등)"],
          ["G드라이브 백업","G:\\내 드라이브\\...\\자동매매\\07 Rauto\\ (본 보고서 + 배포 zip)"],
        ]
      ),
      P("끝. 다음 세션은 CLAUDE.md → STATE → INDEX → 본 보고서 순으로 펼치면 그대로 이어집니다.", {italics:true, size:19, color:"666666"}),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync("Handover_Rauto_Phone_LiveOps_20260620.docx", buf);
  console.log("written", buf.length, "bytes"); });
