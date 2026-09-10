// editor — 탭 스트립·파일 열기·원문 렌더·편집 모드(검증/저장/재읽기)
"use strict";
/* ---------- 에디터 탭 줄 ---------- */
function addTab(path){
  if(S.tabs.some(function(x){ return x.path === path; })) return;   // 이미 열린 탭은 위치 유지
  var m = S.meta[path] || {};
  var seg = String(path).split(/[\\/]/);
  var t = {path:path, name: m.label || seg[seg.length-1] || path, sub: m.origin || ""};
  S.tabs.push(t);
  if(S.tabs.length > MAX_TABS) S.tabs = S.tabs.slice(S.tabs.length - MAX_TABS);
}
function closeTab(path){
  if(S.edit && S.edit.path === path && !guardEdit()) return;
  var i = S.tabs.findIndex(function(x){ return x.path === path; });
  if(i < 0) return;
  S.tabs.splice(i, 1);
  if(S.filePath !== path){ renderTabstrip(); return; }
  var next = S.tabs[i] || S.tabs[i-1];
  if(next){ openFile(next.path); return; }
  S.fseq++;    // 진행 중 파일 응답 무효
  S.file = null; S.fileErr = null; S.filePath = null; S.issues = null;
  renderSide(); renderTabstrip(); renderInspector();
  renderRaw();
}
function renderTabstrip(){
  var strip = clear(document.getElementById("tabstrip"));
  strip.setAttribute("role","tablist");
  var path = clear(document.getElementById("pathline"));
  if(!S.tabs.length) strip.appendChild(el("div","tab empty","열린 파일 없음"));
  S.tabs.forEach(function(t){
    var d = el("div","tab"+(t.path === S.filePath ? " act" : ""));
    var b = el("button","tabname");
    b.setAttribute("role","tab");
    b.setAttribute("aria-selected", String(t.path === S.filePath));
    if(t.path === S.filePath) b.setAttribute("aria-controls","panel");
    b.appendChild(el("span","tf", t.name));
    if(t.sub) b.appendChild(el("span","ts", t.sub));
    b.title = t.path;
    b.onclick = function(){ openFile(t.path); };
    d.appendChild(b);
    var x = el("button","tabx","×");
    x.setAttribute("aria-label", t.name + " 닫기");
    x.onclick = function(){ closeTab(t.path); };
    d.appendChild(x);
    strip.appendChild(d);
  });
  path.textContent = S.filePath || "";
}

/* ---------- 에디터 패널 — 언제나 열린 파일의 원문 ---------- */
function panel(){ return clear(document.getElementById("panel")); }

// 파일이 어떤 프로젝트 소속이면 그 프로젝트로 컨텍스트를 맞춘다 (전역·플러그인 파일이면 유지)
function syncProject(path){
  var m = S.meta[path];
  if(!m || !m.project) return;
  if(S.project && S.project.path === m.project) return;
  var pr = ((S.scan && S.scan.projects) || []).filter(function(x){ return x.path === m.project; })[0];
  if(!pr) return;
  S.project = pr;
  loadEff();   // 트리·인스펙터 렌더는 openFile 이 이어서 수행
}
async function openFile(path){
  if(!guardEdit()) return;
  syncProject(path);
  S.file = null; S.fileErr = null; S.filePath = path; S.issues = null;
  S.selHook = null; S.selMcp = null;   // 파일을 열면 훅·MCP 선택 해제
  addTab(path);
  renderSide();
  renderTabstrip();
  // 파일은 자체 세대(fseq) + 스캔 세대(sseq)만 본다
  var sseq = S.sseq, fseq = ++S.fseq;
  renderRaw();  // filePath 기준 "불러오는 중" 표시
  renderInspector();
  var file = null, err = null;
  try{
    file = await getJSON("/api/file?path="+encodeURIComponent(path));
  }catch(e){
    err = "파일을 불러오지 못했습니다: "+path+" — "+e.message;
  }
  if(S.dead || sseq !== S.sseq || fseq !== S.fseq) return;
  S.file = file; S.fileErr = err;
  renderRaw();
  renderInspector();
}
function renderRaw(){
  var p = panel();
  if(S.edit && S.edit.path === S.filePath) return renderEdit(p);
  if(S.fileErr){ p.appendChild(el("div","pad")).appendChild(el("p","err", S.fileErr)); return; }
  if(!S.file){
    var pd = p.appendChild(el("div","pad"));
    // 파일이 열리면 툴바가 역할을 설명하므로, 미선택일 때만 한 줄 설명
    if(!S.filePath) pd.appendChild(viewHint("왼쪽 목록에서 항목을 선택하세요 · 액티비티 바로 파일/규칙/스킬/훅/MCP 전환"));
    pd.appendChild(el("p","hint", S.filePath ? "불러오는 중… "+S.filePath : "열린 파일이 없습니다."));
    return;
  }
  p.appendChild(readBar());
  if(S.issues && S.issues.length) p.appendChild(issueList(S.issues));
  var lines = (S.file.text || "").split("\n");
  var box = el("div","code");
  // ponytail: 2000줄까지만 줄 단위 행, 나머지는 pre 한 덩어리 (행이 많으면 렌더가 느려짐)
  var n = Math.min(lines.length, MAX_LINE_ROWS);
  for(var i=0;i<n;i++){
    var row = el("div","line");
    row.appendChild(el("span","ln", String(i+1)));
    row.appendChild(el("span","src", lines[i]));
    box.appendChild(row);
  }
  if(lines.length > n) box.appendChild(el("pre","rest", lines.slice(n).join("\n")));
  p.appendChild(box);
}

/* 1-1. 편집 모드 (F3·F4·F5) */
// ponytail: 줄번호·구문강조·diff 없음. textarea 하나 + 검증/저장 버튼.
var ED = null;   // 현재 그려진 편집 DOM 참조 {path, ta, msg, issues, btns}
function isPluginFile(path){
  var m = S.meta[path] || {};
  return String(m.origin || "").indexOf("플러그인 ") === 0;
}
function tbtn(text, fn){ var b = el("button", null, text); b.onclick = fn; return b; }
// 원문(읽기) 뷰 툴바 — 편집 진입 또는 읽기 전용 안내
function readBar(){
  var bar = el("div","tbar");
  if(isPluginFile(S.filePath)) bar.appendChild(el("span","hint","읽기 전용 (플러그인)"));
  else bar.appendChild(tbtn("편집", startEdit));
  var m = S.meta[S.filePath] || {};
  if(m.shared) bar.appendChild(el("span","hint","팀 공유 (git 추적)"));
  return bar;
}
function issueList(issues){
  var box = el("div","issues");
  if(!issues.length){ box.appendChild(el("div","hint","문제 없음")); return box; }
  issues.forEach(function(it){
    var lv = it.level === "error" ? "error" : "warnlv";
    var d = el("div","iss "+lv);
    d.appendChild(el("span","rl", (it.rule || "?") + (it.line != null ? " · "+it.line+"행" : "")));
    d.appendChild(document.createTextNode(it.message || ""));
    box.appendChild(d);
  });
  return box;
}
function startEdit(){
  if(!S.file || !S.filePath || isPluginFile(S.filePath)) return;
  S.edit = {path:S.filePath, text:S.file.text || "", dirty:false,
            issues:null, busy:false, conflict:false, msg:null, msgCls:""};
  S.issues = null;
  renderRaw();
  if(ED && ED.ta) ED.ta.focus();
}
// 편집을 버려도 되는지 — 버려도 되면 편집 상태를 지우고 true
function guardEdit(){
  if(!S.edit) return true;
  if(S.edit.dirty && !confirm("저장하지 않은 변경이 있습니다. 버릴까요?")) return false;
  S.edit = null; ED = null;
  return true;
}
function cancelEdit(){
  if(!guardEdit()) return;
  renderRaw();
  renderInspector();
}
function renderEdit(p){
  var e = S.edit, m = S.meta[e.path] || {};
  var wrap = el("div","edit");
  var bar = el("div","tbar");
  var bV = tbtn("검증", doValidate), bS = tbtn("저장", doSave), bC = tbtn("취소", cancelEdit);
  bar.appendChild(bV); bar.appendChild(bS); bar.appendChild(bC);
  var st = el("span","hint", e.dirty ? "수정됨" : "변경 없음");
  bar.appendChild(st);
  wrap.appendChild(bar);
  if(m.shared) wrap.appendChild(el("div","sharewarn","git 추적 파일 — 커밋하면 팀 전체에 적용됨"));
  var msg = el("div","edmsg");
  wrap.appendChild(msg);
  var ta = el("textarea","ta");
  ta.value = e.text;
  ta.spellcheck = false;
  ta.setAttribute("aria-label", e.path + " 편집");
  ta.oninput = function(){
    if(!S.edit) return;
    S.edit.text = ta.value; S.edit.dirty = true;
    st.textContent = "수정됨";
  };
  wrap.appendChild(ta);
  var iss = el("div");
  wrap.appendChild(iss);
  p.appendChild(wrap);
  ED = {path:e.path, ta:ta, msg:msg, issues:iss, btns:[bV,bS,bC]};
  refreshEdit();
}
// 검증/저장 응답만 반영 — textarea 는 다시 만들지 않는다 (커서·스크롤 유지)
function refreshEdit(){
  var e = S.edit;
  if(!e) return;
  if(!ED || ED.path !== e.path) return renderRaw();
  ED.btns.forEach(function(b){ b.disabled = !!e.busy; });
  var msg = clear(ED.msg);
  msg.className = "edmsg" + (e.msgCls ? " "+e.msgCls : "");
  if(e.msg) msg.appendChild(el("span", null, e.msg));
  if(e.conflict){
    var b = el("button","linkbtn","다시 읽기");
    b.onclick = reReadFile;
    msg.appendChild(b);
  }
  clear(ED.issues);
  if(e.issues) ED.issues.appendChild(issueList(e.issues));
}
function editBusy(text){
  S.edit.busy = true; S.edit.msg = text; S.edit.msgCls = "";
  refreshEdit();
}
// 응답 세대 가드: 서버 종료·편집 종료·다른 파일 편집이면 버린다
function editAlive(path){ return !S.dead && S.edit && S.edit.path === path; }
async function doValidate(){
  var e = S.edit;
  if(!e || e.busy) return;
  var path = e.path;
  editBusy("검증 중…");
  var res = null, err = null;
  try{ res = await postJSON("/api/validate", {path:path, text:S.edit.text}); }
  catch(ex){ err = ex.message; }
  if(!editAlive(path)) return;
  S.edit.busy = false;
  if(err || !res.ok){
    S.edit.issues = null;
    S.edit.msg = "검증하지 못했습니다: " + (err || resErr(res));
    S.edit.msgCls = "bad";
  }else{
    S.edit.issues = res.body.issues || [];
    S.edit.msg = null; S.edit.msgCls = "";
  }
  refreshEdit();
}
async function doSave(){
  var e = S.edit;
  if(!e || e.busy) return;
  if(e.conflict){
    e.msg = "디스크에서 변경됨 — 다시 읽기 후 저장하세요."; e.msgCls = "bad";
    refreshEdit();
    return;
  }
  var path = e.path, text = e.text;
  editBusy("저장 중…");
  var res = null, err = null;
  try{ res = await postJSON("/api/save", {path:path, text:text, mtime:(S.file && S.file.mtime)}); }
  catch(ex){ err = ex.message; }
  if(!editAlive(path)) return;
  S.edit.busy = false;
  if(err){
    S.edit.msg = "저장하지 못했습니다: " + err; S.edit.msgCls = "bad";
    return refreshEdit();
  }
  var b = res.body;
  if(res.status === 200){
    if(S.file && S.filePath === path){
      S.file.text = text;
      if(b.mtime != null) S.file.mtime = b.mtime;
      if(b.size != null) S.file.size = b.size;
    }
    S.edit = null; ED = null;
    S.issues = (b.issues && b.issues.length) ? b.issues : null;   // warn 은 저장 후에도 남긴다
    S.msg = "저장됨 · 백업 " + (b.backup || "(경로 미상)");
    S.msgOk = true;
    renderRaw();
    renderInspector();
    return;
  }
  if(res.status === 422){
    S.edit.issues = b.issues || [];
    S.edit.msg = "검증 오류가 있어 저장하지 않았습니다."; S.edit.msgCls = "bad";
  }else if(res.status === 409){
    S.edit.conflict = true;
    S.edit.msg = "디스크에서 변경됨 — 다시 읽기 후 저장할 수 있습니다.";
    S.edit.msgCls = "bad";
  }else{
    S.edit.msg = "저장하지 못했습니다: " + resErr(res); S.edit.msgCls = "bad";
  }
  refreshEdit();
}
// 409 복구: 디스크 원문만 다시 받는다 — textarea 편집본은 그대로 (§11.3)
async function reReadFile(){
  var e = S.edit;
  if(!e || e.busy) return;
  var path = e.path;
  editBusy("다시 읽는 중…");
  var file = null, err = null;
  try{ file = await getJSON("/api/file?path="+encodeURIComponent(path)); }
  catch(ex){ err = ex.message; }
  if(!editAlive(path)) return;
  S.edit.busy = false;
  if(err){
    S.edit.msg = "다시 읽지 못했습니다: " + err; S.edit.msgCls = "bad";
    return refreshEdit();
  }
  if(S.filePath === path) S.file = file;
  S.edit.conflict = false;
  S.edit.msg = "디스크 내용을 다시 읽었습니다. 편집본은 그대로이며, 저장하면 덮어씁니다.";
  S.edit.msgCls = "";
  refreshEdit();
  renderInspector();
}
