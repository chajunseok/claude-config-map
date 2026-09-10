// main — 하단 상태바·스캔 로드·서버 종료·전역 키보드/언로드 핸들러·부트
"use strict";
/* ---------- 하단 상태바 ---------- */
function hms(t){
  var d = new Date(t);
  if(isNaN(d.getTime())) return "-";
  var p = function(x){ return (x<10?"0":"")+x; };
  return p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds());
}
// 우측 상태 문구 — 지금 무엇을 보고 있는지 한 줄
function statusText(){
  if(S.edit) return "편집 중 · " + baseName(S.edit.path);
  if(S.filePath && isCompare(S.filePath))
    return "비교: " + cmpTitle(S.filePath) + " · " + len(S.file && S.file.matches) + "곳";
  if(S.side === "rules"){
    var n = len(S.eff);
    if(!n) return "";
    var cur = -1;
    S.eff.forEach(function(it, i){ if(it.path === S.filePath) cur = i; });
    return (cur >= 0 ? (cur+1) + " / " + n : n + " 파일") + " · 아래가 위를 덮어씀";
  }
  if(S.side === "skills") return "토글 저장 → " + S.toggleTarget;
  if(S.side === "hooks"){
    if(!S.selHook) return "";
    var f = hookFile(S.selHook.source);
    return f ? baseName(f) : hookSource(S.selHook.source).label;
  }
  if(S.side === "mcp"){
    if(!S.selMcp) return "";
    return S.selMcp.file ? baseName(S.selMcp.file) : (S.selMcp.label || "");
  }
  if(S.filePath && S.file)
    return baseName(S.filePath) + " · " + String(S.file.text || "").split("\n").length + "줄";
  return "";
}
function sbtn(text, fn, disabled){
  var b = el("button","sbtn", text);
  b.disabled = !!disabled;
  b.onclick = fn;
  return b;
}
function renderStatus(){
  var bar = document.getElementById("statusbar");
  if(!bar || S.dead) return;
  clear(bar);
  bar.appendChild(el("span", null, S.scan ? "스캔 " + hms(S.scan.scanned_at)
                                          : (S.loading ? "스캔 중…" : "스캔 -")));
  var c = cmpVer(S.scan && S.scan.claude_version);
  bar.appendChild(el("span", c === null ? "warn" : null,
    "Claude Code " + (c === null ? "버전 미확인" : S.scan.claude_version)));
  var errs = (S.scan && S.scan.errors) || [];
  if(errs.length){
    var eb = el("button","sbtn err","오류 "+errs.length+"건");
    eb.setAttribute("aria-expanded", String(S.errOpen));
    eb.onclick = function(){ S.errOpen = !S.errOpen; renderInspector(); renderStatus(); };
    bar.appendChild(eb);
  }
  if(S.msg) bar.appendChild(el("span", "smsg " + (S.msgOk ? "ok" : "err"), S.msg));
  if(S.scanErr) bar.appendChild(retryBtn(loadScan));
  bar.appendChild(el("span","spacer"));
  var t = statusText();
  if(t) bar.appendChild(el("span","stxt", t));
  bar.appendChild(sbtn(S.loading ? "스캔 중…" : "재스캔", loadScan, S.loading));
  bar.appendChild(sbtn("종료", shutdown));
}

async function shutdown(){
  if(S.dead) return;
  if(!guardEdit()) return;
  var fail = null;
  try{
    var r = await fetch("/api/shutdown",{method:"POST"}), b = null;
    try{ b = await r.json(); }catch(e){}
    if(!r.ok || !b || b.ok !== true) fail = (b && b.error) || ("HTTP "+r.status);
  }catch(e){ fail = e.message; }
  if(fail){  // 실패면 UI 유지, 상태바에만 표시
    S.msg = "종료하지 못했습니다: "+fail; S.msgOk = false;
    renderStatus();
    return;
  }
  S.dead = true;
  document.body.textContent = "";
  var p = el("p",null,"서버가 종료되었습니다");
  p.style.padding = "24px";
  document.body.appendChild(p);
}

/* ---------- 부트 ---------- */
async function loadScan(){
  if(S.dead || S.loading) return;   // 진행 중 재스캔 재요청은 무시
  if(!guardEdit()) return;
  // 복원용 선택은 미리 잡아 두고, 상태 교체는 완료 시점에만
  var prevProject = S.project && S.project.path, prevFile = S.filePath;
  var seq = ++S.sseq;   // 실패해도 되돌리지 않는다
  S.loading = true; S.msg = null; S.msgOk = false; S.scanErr = false;
  renderActivity();
  renderStatus();
  renderInspector();
  sideBody().appendChild(el("div","pad hint","스캔 중…"));
  panel().appendChild(el("div","pad hint","스캔 중…"));
  var scan = null, err = null;
  try{
    scan = await getJSON(SAMPLE ? "./scan-sample.json" : "/api/scan");
  }catch(e){ err = e.message; }
  S.loading = false;
  if(S.dead || seq !== S.sseq) return;
  if(err){  // 이전 스캔 데이터는 유지 — 사이드바도 그대로 두어 에디터와 어긋나지 않게
    S.msg = "스캔에 실패했습니다: "+err; S.msgOk = false; S.scanErr = true;
    renderActivity();
    renderStatus();
    if(S.scan) renderSide();
    // 세대(sseq)는 되돌리지 않는다 — 스캔 중 도착해 폐기된 응답은 지금 다시 요청해 복구
    // 복구 호출을 패널 렌더보다 먼저 — 복구가 패널을 다시 그려도 오류는 인스펙터에 남는다
    if(S.project && !S.eff && !S.effErr) loadEff();
    if(S.filePath && !S.file && !S.fileErr) openFile(S.filePath);
    renderInspector();
    var q = panel(), qp = el("div","pad");
    q.appendChild(qp);
    qp.appendChild(el("p","err", S.msg));
    qp.appendChild(retryBtn(loadScan));
    return;
  }
  S.scan = scan;
  S.meta = scanIndex(scan);
  // 이전 선택 복원
  S.project = null; S.file = null; S.fileErr = null; S.filePath = null;
  S.eff = null; S.effErr = null; S.eseq++; S.selHook = null; S.selMcp = null;
  S.fileCache = Object.create(null); S.cacheBusy = Object.create(null);
  // 비교 가상 탭은 스캔 메타에 없으므로 예외
  S.tabs = S.tabs.filter(function(t){ return isCompare(t.path) || !!S.meta[t.path]; });
  if(prevProject){
    var found = (scan.projects||[]).filter(function(x){ return x.path === prevProject; })[0];
    if(found) S.project = found;
    else { S.msg = "재스캔 후 프로젝트가 사라져 선택을 해제했습니다: "+prevProject; S.msgOk = false; }
  }
  if(prevFile && !isCompare(prevFile) && !S.meta[prevFile]){
    S.fileErr = "재스캔 후 파일이 사라졌습니다: "+prevFile;
    prevFile = null;
  }
  if(S.project) loadEff();
  renderActivity();
  renderSide();
  renderTabstrip();
  renderInspector();
  renderRaw();
  if(prevFile) openFile(prevFile);
}
// 편집 중 Ctrl+S = 저장, 브라우저 닫기 = 경고
document.addEventListener("keydown", function(ev){
  if(!S.edit || !(ev.ctrlKey || ev.metaKey)) return;
  if(ev.key !== "s" && ev.key !== "S") return;
  ev.preventDefault();
  doSave();
});
window.addEventListener("beforeunload", function(ev){
  if(S.edit && S.edit.dirty){ ev.preventDefault(); ev.returnValue = ""; }
});
renderActivity();
renderSide();
renderTabstrip();
renderInspector();
renderStatus();
loadScan();
