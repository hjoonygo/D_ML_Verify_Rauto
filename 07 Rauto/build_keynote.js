const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType } = require('docx');
const FONT="Malgun Gothic";
const bd={style:BorderStyle.SINGLE,size:1,color:"CCCCCC"}; const borders={top:bd,bottom:bd,left:bd,right:bd};
function H1(t){return new Paragraph({heading:HeadingLevel.HEADING_1,children:[new TextRun(t)]});}
function H2(t){return new Paragraph({heading:HeadingLevel.HEADING_2,children:[new TextRun(t)]});}
function P(t,o={}){return new Paragraph({spacing:{after:70},children:[new TextRun({text:t,...o})]});}
function B(t){return new Paragraph({numbering:{reference:"b",level:0},spacing:{after:40},children:[new TextRun(t)]});}
function cell(t,w,hdr){return new TableCell({borders,width:{size:w,type:WidthType.DXA},
  shading:hdr?{fill:"1F4E79",type:ShadingType.CLEAR}:undefined,margins:{top:60,bottom:60,left:110,right:110},
  children:[new Paragraph({children:[new TextRun({text:t,bold:!!hdr,color:hdr?"FFFFFF":undefined,size:19})]})]});}
function table(cols,rows){const tot=cols.reduce((a,b)=>a+b.w,0);
  return new Table({width:{size:tot,type:WidthType.DXA},columnWidths:cols.map(c=>c.w),
    rows:[new TableRow({tableHeader:true,children:cols.map(c=>cell(c.t,c.w,true))}),
      ...rows.map(r=>new TableRow({children:r.map((t,i)=>cell(t,cols[i].w))}))]});}

const doc=new Document({
  styles:{default:{document:{run:{font:FONT,size:21}}},paragraphStyles:[
    {id:"Heading1",name:"Heading 1",basedOn:"Normal",next:"Normal",quickFormat:true,
      run:{size:28,bold:true,font:FONT,color:"1F4E79"},
      paragraph:{spacing:{before:240,after:120},outlineLevel:0,border:{bottom:{style:BorderStyle.SINGLE,size:6,color:"1F4E79",space:2}}}},
    {id:"Heading2",name:"Heading 2",basedOn:"Normal",next:"Normal",quickFormat:true,
      run:{size:23,bold:true,font:FONT,color:"2E5E8C"},paragraph:{spacing:{before:140,after:80},outlineLevel:1}}]},
  numbering:{config:[{reference:"b",levels:[{level:0,format:LevelFormat.BULLET,text:"•",alignment:AlignmentType.LEFT,
    style:{paragraph:{indent:{left:560,hanging:260}}}}]}]},
  sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1300,right:1300,bottom:1300,left:1300}}},children:[
    new Paragraph({spacing:{after:60},children:[new TextRun({text:"KeyNote — Rauto LiveControlApp (07Prj_Rauto_Phone_Stg5)",bold:true,size:32,color:"1F4E79"})]}),
    new Paragraph({spacing:{after:160},children:[new TextRun({text:"2026-06-20 · 제어앱 b25→b33 기술 상세 · AWS 운영 인프라 · 버그 수정",size:19,color:"666666"})]}),

    H1("1. 제어앱 기능 (control_server.py / control_dashboard.html)"),
    table([{t:"기능",w:2300},{t:"구현 요점",w:5360},{t:"엔드포인트",w:1700}],[
      ["RBAC+인증","RAUTO_TOKENS=tok:role[:만료일]. 미설정=OFF(호환). admin전용 /cmd·/email·/load·/remove=403. view=상태조회+PII마스킹. 감사로그(audit.log).","/whoami"],
      ["시크릿 파일","env 우선, 없으면 rauto_secrets.txt(KEY=VALUE). GMAIL_PW·TELEGRAM·RAUTO_TOKENS. setx 상속함정 회피.","-"],
      ["Bot로딩","BOT_REGISTRY(이름→러너+env). 목록→빈슬롯 로딩, 슬롯번호 폴더맞춤(중복방지).","/bots /load"],
      ["슬롯제거","선택 슬롯 _folder 기준 삭제. 챔피언+실거래중이면 차단(긴급중지 먼저).","/remove"],
      ["녹색 R","러너 첫5줄 RAUTO_LIVE_CERTIFIED 마커=실거래 인증봇만 허용·표시.","-"],
      ["self-locating","env 우선+드라이브 stat/glob 탐색(REPO·STATE_GLOB·FLAG_DIR). 하드코딩경로 제거.","-"],
      ["텍스트선택 차단","CSS user-select:none + touch-callout:none(길게눌러 복사메뉴 제거).","-"],
    ]),

    H1("2. AWS 운영 인프라"),
    H2("서비스화 (NSSM)"),
    B("RautoControl(서버+봇 autoload)·DautoCollector(수집) = NSSM 서비스, AUTO_START. sshd·Tailscale도 AUTO_START → 재부팅 자동복구."),
    B("AppEnvironmentExtra PYTHONIOENCODING=utf-8. AppDirectory는 \"%~dp0.\"(끝 백슬래시 따옴표 이스케이프 버그 회피)."),
    H2("SSH 직접접속 (운영의 핵심)"),
    B("OpenSSH 서버 설치 + 공개키(administrators_authorized_keys, icacls 권한고정) → 비번없이 접속."),
    B("administrator@ec2amaz-cor6gpg.tail305e55.ts.net · 키 ~/.ssh/rauto_aws(캡틴 PC). Claude가 scp 배포·서비스 재시작·로그·진단 직접 수행."),

    H1("3. 버그 수정 (전부 SSH로 직접)"),
    table([{t:"증상",w:2300},{t:"원인",w:4760},{t:"수정",w:2300}],[
      ["서비스 즉시정지","서비스 stdout=cp1252서 ★·한글 print UnicodeEncodeError","sys.stdout/stderr.reconfigure('utf-8','replace')"],
      ["NSSM 프로세스 못띄움","AppDirectory \"%~dp0\"=끝백슬래시+따옴표로 'C:\\Temp\"'(잘못된경로)","\"%~dp0.\""],
      ["슬롯제거 중복안됨","R3가 폴더3·4 같은이름→removeSlot이 이름→폴더3만 삭제","aggregate가 _folder 태그 + removeSlot 폴더기준 + 로딩시 슬롯번호 폴더맞춤"],
      ["R3/R4 자산곡선·최근1주 X","AWS가 옛 듀얼러너(equity 마지막400분·wk=None)","고친 러너 배포+재실행(전구간 38.7일·wk dict)"],
      ["슬롯제거 후 부활","AUTOLOAD ON=git루프가 state.json 없으면 재생성","RAUTO_AUTOLOAD=0"],
      ["폰 옛화면 고착","sw.js 캐시 rauto-v25","캐시버전 v33으로 올려 자동갱신"],
    ]),

    H1("4. 검증"),
    B("로컬: RBAC(401/403/마스킹/감사)·cert읽기·/remove guard·자동로딩게이트·JS문법(node --check) 전부 PASS."),
    B("SSH 실측: 서비스 RUNNING·8787 LISTENING·b33 서빙·R3/R4 wk dict·폴더 고유(중복0)·AUTOLOAD=0 확인."),
    B("알파 무변경: CVD 변형검증=교체무의미(누적raw IC-0.035), 롤7h 동결. 챔피언/§15 4봇 보존."),
    P("코드 전문·재현 데이터 = 07Prj_Rauto_Phone_Stg5_Repro_Package.zip(code/verify/data/docs). 상세 이력 = INDEX·STATE_Rauto.txt.",{italics:true,size:19,color:"666666"}),
  ]}]
});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync("D:/ML/Verify/00WorkHstr/00Basic_Setup_Package/KeyNote_07Prj_Rauto_Phone_Stg5_LiveControlApp.docx",b);console.log("KeyNote written",b.length);});
