// editor — 탭 스트립·파일 열기·원문 렌더·편집 모드(검증/저장/재읽기)
"use strict";
/* ---------- 에디터 탭 줄 ---------- */
function addTab(path){
  if(S.tabs.some(function(x){ return x.path === path; })) return;   // 이미 열린 탭은 위치 유지
  var m = S.meta[path] || {};
  var seg = String(path).split(/[\\/]/);
  var t = isCompare(path) ? {path:path, name:"비교: "+cmpTitle(path), sub:"제목 비교"}
                          : {path:path, name: m.label || seg[seg.length-1] || path, sub: m.origin || ""};
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
  if(!S.tabs.length) strip.appendChild(el("div","tab empty","열린 파일 없음"));
  // 같은 이름·출처 탭이 여럿이면(SKILL.md 등) 상위 폴더를 붙여 구분 — 경로는 다르므로 중복 탭이 아니다
  var seen = Object.create(null);
  S.tabs.forEach(function(t){ var k = t.name + "|" + t.sub; seen[k] = (seen[k] || 0) + 1; });
  S.tabs.forEach(function(t){
    var d = el("div","tab"+(t.path === S.filePath ? " act" : ""));
    var b = el("button","tabname");
    b.setAttribute("role","tab");
    b.setAttribute("aria-selected", String(t.path === S.filePath));
    if(t.path === S.filePath) b.setAttribute("aria-controls","panel");
    var seg = String(t.path).split(/[\\/]/), shown = t.name;
    if(!isCompare(t.path) && seen[t.name + "|" + t.sub] > 1 && seg.length > 1) shown = seg[seg.length-2] + "/" + t.name;
    b.appendChild(el("span","tf", shown));
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
  renderPathline();
}
/* 경로 줄 — 경로 + 오른쪽 읽기 모드 툴바 (편집 모드 툴바는 #panel 안 sticky 유지) */
function renderPathline(){
  var bar = clear(document.getElementById("pathline"));
  bar.appendChild(el("span","pp", S.filePath || ""));
  if(!S.filePath || isCompare(S.filePath)) return;
  if(S.edit && S.edit.path === S.filePath) return;
  if(!S.file) return;
  if(isPluginFile(S.filePath)) bar.appendChild(el("span","hint","읽기 전용 (플러그인)"));
  else bar.appendChild(ebtn("편집", function(){ startEdit(); }));
  if(keys(headMap()).length){
    bar.appendChild(ebtn("모두 접기", function(){ foldAll(true); }));
    bar.appendChild(ebtn("모두 펼치기", function(){ foldAll(false); }));
  }
  var m = S.meta[S.filePath] || {};
  if(m.shared) bar.appendChild(el("span","hint","팀 공유 · git"));
}
function ebtn(text, fn){ var b = el("button","ebtn", text); b.onclick = fn; return b; }

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
// opts.line: 렌더 후 그 줄로 스크롤 + 1.5초 하이라이트 (접혀 있으면 펼친다)
async function openFile(path, opts){
  if(!guardEdit()) return;
  opts = opts || {};
  if(!isCompare(path)) syncProject(path);
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
    file = isCompare(path)
      ? await getJSON("/api/compare?title="+encodeURIComponent(cmpTitle(path)))
      : await getJSON("/api/file?path="+encodeURIComponent(path));
  }catch(e){
    err = (isCompare(path) ? "비교하지 못했습니다: "+cmpTitle(path) : "파일을 불러오지 못했습니다: "+path)
        + " — " + e.message;
  }
  if(S.dead || sseq !== S.sseq || fseq !== S.fseq) return;
  S.file = file; S.fileErr = err;
  if(file && !isCompare(path)) S.fileCache[path] = file;
  renderRaw();
  renderInspector();
  if(opts.line != null) gotoLine(opts.line);
}
/* 줄로 이동 — 접힌 섹션 안이면 펼치고 다시 그린 뒤 1.5초 하이라이트 */
function gotoLine(line){
  var f = S.folds[S.filePath];
  if(f){
    var opened = false;
    ((S.file && S.file.sections) || []).forEach(function(sec){
      if(f[sec.start] && line > sec.start && line < sec.end){ delete f[sec.start]; opened = true; }
    });
    if(opened) renderRaw();
  }
  var row = document.querySelector('#panel .line[data-line="'+line+'"]');
  if(!row) return;
  row.scrollIntoView({block:"center"});
  row.classList.add("hl");
  setTimeout(function(){ row.classList.remove("hl"); }, 1500);
}
function renderRaw(){
  var p = panel();
  renderPathline();
  renderStatus();
  if(S.edit && S.edit.path === S.filePath) return renderEdit(p);
  if(S.fileErr){ p.appendChild(el("div","pad")).appendChild(el("p","err", S.fileErr)); return; }
  if(!S.file){
    var pd = p.appendChild(el("div","pad"));
    // 파일이 열리면 경로 줄 툴바가 역할을 설명하므로, 미선택일 때만 한 줄 설명
    if(!S.filePath) pd.appendChild(viewHint("왼쪽 목록에서 항목을 선택하세요 · 액티비티 바로 파일/규칙/스킬/훅/MCP 전환"));
    pd.appendChild(el("p","hint", S.filePath ? "불러오는 중… "+S.filePath : "열린 파일이 없습니다."));
    return;
  }
  if(isCompare(S.filePath)) return renderCompare(p);
  if(S.issues && S.issues.length) p.appendChild(issueList(S.issues));
  var lines = (S.file.text || "").split("\n");
  var heads = headMap(), folded = S.folds[S.filePath] || null;
  var box = el("div","code");
  // ponytail: 2000줄까지만 줄 단위 행, 나머지는 pre 한 덩어리 (행이 많으면 렌더가 느려짐)
  var n = Math.min(lines.length, MAX_LINE_ROWS);
  for(var i=0;i<n;i++){
    var sec = heads[i];
    box.appendChild(lineRow(i, lines[i], sec));
    if(!sec || !folded || !folded[i]) continue;
    var hid = Math.min(sec.end, lines.length) - i - 1;
    if(hid <= 0) continue;
    box.appendChild(el("div","folded", "… "+hid+"줄"));
    i = Math.min(sec.end, n) - 1;      // 접힌 구간은 건너뛴다
  }
  if(lines.length > n) box.appendChild(el("pre","rest", lines.slice(n).join("\n")));
  p.appendChild(box);
}
/* 헤딩 줄번호 → 섹션 (preamble 은 접기 대상 아님) */
function headMap(){
  var out = Object.create(null);
  ((S.file && S.file.sections) || []).forEach(function(sec){ if(sec.level > 0) out[sec.start] = sec; });
  return out;
}
function toggleFold(start){
  var f = S.folds[S.filePath] || (S.folds[S.filePath] = Object.create(null));
  if(f[start]) delete f[start]; else f[start] = true;
  renderRaw();
}
function foldAll(on){
  var f = Object.create(null);
  if(on) keys(headMap()).forEach(function(k){ f[k] = true; });
  S.folds[S.filePath] = f;
  renderRaw();
}
function lineRow(i, text, sec){
  var row = el("div","line");
  row.setAttribute("data-line", String(i));
  var ln = el("span","ln");
  if(sec){
    var open = !(S.folds[S.filePath] || {})[i];
    var fb = el("button","fold", open ? "▾" : "▸");
    fb.setAttribute("aria-expanded", String(open));
    fb.setAttribute("aria-label", (sec.title || "섹션") + " 접기·펼치기");
    fb.onclick = function(){ toggleFold(i); };
    ln.appendChild(fb);
  }
  ln.appendChild(el("span","lnn", String(i+1)));
  row.appendChild(ln);
  row.appendChild(el("span","src", text));
  if(sec && !isPluginFile(S.filePath)){
    var eb = el("button","seced","이 섹션 편집");
    eb.onclick = function(){ startEdit(sec); };
    row.appendChild(eb);
  }
  return row;
}
/* 비교 가상 탭 — 제목이 같은 섹션을 스택으로. 편집 없음 */
function renderCompare(p){
  var ms = (S.file && S.file.matches) || [];
  var bar = el("div","tbar");
  bar.appendChild(el("span","hint", "제목 비교 · " + cmpTitle(S.filePath) + " · " + ms.length + "곳"));
  p.appendChild(bar);
  if(!ms.length){ p.appendChild(el("div","pad")).appendChild(el("p","hint","같은 제목의 섹션이 없습니다.")); return; }
  var box = el("div","cmp");
  ms.forEach(function(m){
    var card = el("div","cmpitem");
    var h = el("button","cmphd");
    h.appendChild(el("span","t", m.project || "전역"));
    h.appendChild(badge(SCOPE_KO[m.scope] || m.scope));
    h.appendChild(el("span","p", m.path + " · L" + (m.start+1) + "–L" + m.end));
    h.title = m.path + " — 이 줄로 이동";
    h.onclick = function(){ openFile(m.path, {line:m.start}); };
    card.appendChild(h);
    card.appendChild(el("pre","cmpbody", m.text || ""));
    box.appendChild(card);
  });
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
// sec 를 주면 그 섹션 줄만 편집 — 저장은 /api/save-range
function startEdit(sec){
  if(!S.file || !S.filePath || isPluginFile(S.filePath) || isCompare(S.filePath)) return;
  var text = S.file.text || "", range = null;
  if(sec && sec.title != null){
    range = {start:sec.start, end:sec.end, title:sec.title};
    text = text.split("\n").slice(sec.start, sec.end).join("\n");
  }
  S.edit = {path:S.filePath, text:text, range:range, dirty:false,
            issues:null, busy:false, conflict:false, msg:null, msgCls:"",
            assist:newAssist()};
  S.issues = null;
  renderRaw();
  if(ED && ED.ta) ED.ta.focus();
}
// 편집을 버려도 되는지 — 버려도 되면 편집 상태를 지우고 true
function guardEdit(){
  if(!S.edit) return true;
  if(S.edit.dirty && !confirm("저장하지 않은 변경이 있습니다. 버릴까요?")) return false;
  var a = S.edit.assist;
  if(a && a.id) postJSON("/api/assist-cancel", {id:a.id}).catch(function(){});   // 응답은 무시
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
  if(e.range)
    bar.appendChild(el("span","rangelbl",
      "섹션 편집 중: " + (e.range.title || "(제목 없음)")
      + " (L" + (e.range.start+1) + "–L" + e.range.end + ")"));
  wrap.appendChild(bar);
  if(!e.assist) e.assist = newAssist();
  var as = buildAssist(e);
  wrap.appendChild(as.node);
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
  ED = {path:e.path, ta:ta, msg:msg, issues:iss, btns:[bV,bS,bC], st:st, assist:as.refs};
  refreshEdit();
  refreshAssist();
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
  try{ res = await postJSON("/api/validate", {path:path, text:fullText(S.edit)}); }
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
  var path = e.path, text = e.text, range = e.range;
  if(range && !text.trim()){
    e.msg = "섹션 본문이 비어 있습니다 — 섹션 삭제는 지원하지 않습니다."; e.msgCls = "bad";
    refreshEdit();
    return;
  }
  editBusy("저장 중…");
  var res = null, err = null;
  try{
    res = range
      ? await postJSON("/api/save-range", {path:path, mtime:(S.file && S.file.mtime),
                                           start:range.start, end:range.end, text:text})
      : await postJSON("/api/save", {path:path, text:text, mtime:(S.file && S.file.mtime)});
  }
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
      S.file.text = range ? spliceLines(S.file.text, range.start, range.end, text) : text;
      if(b.mtime != null) S.file.mtime = b.mtime;
      if(b.size != null) S.file.size = b.size;
      if(b.sections) S.file.sections = b.sections;
      S.fileCache[path] = S.file;
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
  if(S.filePath === path){ S.file = file; S.fileCache[path] = file; }
  S.edit.conflict = false;
  S.edit.msg = "디스크 내용을 다시 읽었습니다. 편집본은 그대로이며, 저장하면 덮어씁니다.";
  S.edit.msgCls = "";
  var moved = relocate(S.edit, file);
  if(moved){
    S.edit.msg = moved; S.edit.msgCls = "bad";
    renderRaw();          // 전체 편집으로 바뀌면 textarea 내용이 달라져 다시 그린다
    renderInspector();
    return;
  }
  refreshEdit();
  renderInspector();
}
// 섹션 편집 중 디스크가 바뀐 경우 — 같은 제목으로 범위를 다시 찾는다.
// 못 찾으면 전체 편집으로 전환하되 편집본은 원래 줄 범위에 끼워 넣어 살린다.
function relocate(e, file){
  if(!e.range) return null;
  var found = ((file && file.sections) || []).filter(function(s){
    return s.level > 0 && s.title === e.range.title; })[0];
  if(found){
    e.range = {start:found.start, end:found.end, title:found.title};
    return null;
  }
  var lines = String((file && file.text) || "").split("\n");
  var st = Math.min(e.range.start, lines.length), en = Math.min(e.range.end, lines.length);
  e.text = spliceLines(lines.join("\n"), st, en, e.text);
  e.range = null;
  return "섹션 제목을 디스크에서 찾지 못해 전체 편집으로 전환했습니다 — 원래 줄 범위에 편집본을 넣었으니 확인 후 저장하세요.";
}
// 섹션 편집이면 검증용 전문 합성
function fullText(e){
  if(!e.range) return e.text;
  return spliceLines((S.file && S.file.text) || "", e.range.start, e.range.end, e.text);
}

/* ---------- 편집 도우미 (F9) — Claude CLI 에 수정 지시 → diff → 적용 ---------- */
// ponytail: 작업 하나만 추적한다. 큐도 히스토리도 없음.
function newAssist(){
  return {prompt:"", model:"", id:null, status:null, elapsed:0,
          result:null, diff:null, changed:false, error:null, cost:null};
}
// 프롬프트 칸 DOM — 본문 textarea 와 달리 부분 갱신(refreshAssist)만 한다
function buildAssist(e){
  var a = e.assist;
  var box = el("div","assist");
  var row = el("div","arow");
  var pr = el("textarea","aprompt");
  pr.rows = 1;
  pr.value = a.prompt;
  pr.spellcheck = false;
  pr.placeholder = "Claude에게 수정 지시… (긴 문서는 섹션 편집 권장)";
  pr.setAttribute("aria-label","Claude 수정 지시");
  pr.oninput = function(){ if(S.edit && S.edit.assist) S.edit.assist.prompt = pr.value; };
  pr.onkeydown = function(ev){
    if(ev.key === "Enter" && !ev.shiftKey){ ev.preventDefault(); doAssist(); }
  };
  row.appendChild(pr);
  var sel = el("select","amodel");
  sel.setAttribute("aria-label","모델");
  [["","기본 모델"],["sonnet","sonnet"],["opus","opus"],["haiku","haiku"]].forEach(function(o){
    var op = el("option", null, o[1]);
    op.value = o[0];
    sel.appendChild(op);
  });
  sel.value = a.model || "";
  sel.onchange = function(){ if(S.edit && S.edit.assist) S.edit.assist.model = sel.value; };
  row.appendChild(sel);
  var go = ebtn("요청", doAssist);
  row.appendChild(go);
  box.appendChild(row);
  var msg = el("div","amsg");
  msg.setAttribute("aria-live","polite");
  box.appendChild(msg);
  var dv = el("pre","diffview");
  dv.hidden = true;
  box.appendChild(dv);
  var acts = el("div","aacts");
  acts.hidden = true;
  acts.appendChild(ebtn("적용", applyAssist));
  acts.appendChild(ebtn("버리기", discardAssist));
  box.appendChild(acts);
  return {node:box, refs:{prompt:pr, model:sel, go:go, msg:msg, diff:dv, acts:acts}};
}
// diff 헤더(---/+++)를 벌 변경 줄 수
function diffCount(diff){
  var n = 0;
  String(diff || "").split("\n").forEach(function(l){
    if(/^[+-]/.test(l) && !/^(\+\+\+|---)/.test(l)) n++;
  });
  return n;
}
function refreshAssist(){
  var e = S.edit;
  if(!e || !e.assist || !ED || ED.path !== e.path || !ED.assist) return;
  var a = e.assist, A = ED.assist, running = !!a.id;
  A.prompt.disabled = running;
  A.model.disabled = running;
  A.go.disabled = running || !!e.busy;
  var msg = clear(A.msg);
  msg.className = "amsg" + (a.error ? " err" : "");
  if(running){
    msg.appendChild(el("span", null, "요청 중… " + a.elapsed + "초"));
    var cb = el("button","linkbtn","취소");
    cb.onclick = cancelAssist;
    msg.appendChild(cb);
  }else if(a.error){
    msg.appendChild(el("span", null, a.error));
  }else if(a.status === "done"){
    msg.appendChild(el("span", null, a.changed
      ? "제안 (" + diffCount(a.diff) + "줄 변경)" + (a.cost != null ? " · $" + a.cost.toFixed(4) : "")
      : "변경 없음"));
  }else if(a.status === "applied"){
    msg.appendChild(el("span", null, "제안을 본문에 적용했습니다."));
  }else if(a.status === "discarded"){
    msg.appendChild(el("span", null, "제안을 버렸습니다."));
  }
  var show = a.status === "done" && a.changed && a.result != null;
  var dv = clear(A.diff);
  A.diff.hidden = !show;
  A.acts.hidden = !show;
  if(!show) return;
  String(a.diff || "").split("\n").forEach(function(line){
    var c = line.charAt(0);
    dv.appendChild(el("span", c === "+" ? "add" : c === "-" ? "del" : c === "@" ? "hunk" : null,
                      line + "\n"));
  });
}
async function doAssist(){
  var e = S.edit;
  if(!e || !e.assist || e.busy) return;
  var a = e.assist, path = e.path;
  if(a.id) return;                                  // 이미 실행 중
  var instruction = String(a.prompt || "").trim();
  a.result = null; a.diff = null; a.changed = false; a.cost = null; a.elapsed = 0;
  if(!instruction){
    a.status = null; a.error = "수정 지시를 입력하세요.";
    return refreshAssist();
  }
  a.error = null; a.status = "running"; a.id = "…";  // 요청 중 표시. 실제 id 는 202 응답
  refreshAssist();
  var res = null, err = null;
  try{
    res = await postJSON("/api/assist", {path:path, text:e.text, instruction:instruction,
                                         range:e.range || undefined, model:a.model || undefined});
  }catch(ex){ err = ex.message; }
  if(!editAlive(path) || S.edit.assist !== a) return;
  a.id = null;
  if(err || !res.ok){
    a.status = "error";
    a.error = err ? "요청하지 못했습니다: " + err
            : res.status === 503 ? "Claude Code CLI 를 찾지 못했습니다 — 설치·로그인 후 다시 시도"
            : res.status === 429 ? "이미 실행 중인 요청이 많습니다" : resErr(res);
    return refreshAssist();
  }
  a.id = res.body.id;
  refreshAssist();
  pollAssist(path, a.id);
}
// 1초 간격 폴링. 세대 가드: 편집이 끝났거나 다른 작업이면 조용히 멈춘다
function pollAssist(path, id){
  setTimeout(async function(){
    if(!assistAlive(path, id)) return;
    var b = null, err = null;
    try{ b = await getJSON("/api/assist?id=" + encodeURIComponent(id)); }
    catch(ex){ err = ex.message; }
    if(!assistAlive(path, id)) return;
    var a = S.edit.assist;
    if(err){
      a.id = null; a.status = "error"; a.error = "상태를 확인하지 못했습니다: " + err;
      return refreshAssist();
    }
    a.elapsed = Math.round((b.elapsed_ms || 0) / 1000);
    if(b.status === "running"){ refreshAssist(); return pollAssist(path, id); }
    a.id = null;
    a.status = b.status;
    if(b.status === "done"){
      a.result = b.result || ""; a.diff = b.diff || ""; a.changed = !!b.changed;
      a.cost = typeof b.cost_usd === "number" ? b.cost_usd : null;
      a.error = null;
    }else{
      a.error = b.status === "cancelled" ? "취소했습니다." : (b.error || "요청이 실패했습니다.");
    }
    refreshAssist();
  }, 1000);
}
function assistAlive(path, id){
  return editAlive(path) && !!S.edit.assist && S.edit.assist.id === id;
}
function cancelAssist(){
  var a = S.edit && S.edit.assist;
  if(!a || !a.id) return;
  postJSON("/api/assist-cancel", {id:a.id}).catch(function(){});
  a.id = null; a.status = "cancelled"; a.error = "취소했습니다.";
  refreshAssist();
}
// 적용 = textarea·S.edit.text 만 바꿈다. 저장·검증 흐름은 그대로
function applyAssist(){
  var e = S.edit, a = e && e.assist;
  if(!a || a.result == null || !ED || ED.path !== e.path) return;
  ED.ta.value = a.result;
  e.text = a.result;
  e.dirty = true;
  e.issues = null;                       // 본문이 바뀌었으므로 직전 검증 결과는 버린다
  if(ED.st) ED.st.textContent = "수정됨";
  a.result = null; a.diff = null; a.changed = false; a.status = "applied"; a.error = null;
  refreshEdit();
  refreshAssist();
}
function discardAssist(){
  var a = S.edit && S.edit.assist;
  if(!a) return;
  a.result = null; a.diff = null; a.changed = false; a.status = "discarded"; a.error = null;
  refreshAssist();
}
