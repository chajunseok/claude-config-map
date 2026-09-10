// core — 상수·전역 상태(S)·DOM/포맷 헬퍼·fetch 래퍼·설정 조회·스캔 인덱스·훅/카드 데이터 헬퍼
"use strict";
// ponytail: 상태는 scan 응답 하나. 라우터·프레임워크 없음.
var MIN_VER = [2,1,199];
// 액티비티 바 = 사이드바 내용 전환. 에디터는 언제나 열린 파일의 원문.
var VIEWS = [["files","파일"],["rules","규칙"],["skills","스킬"],["hooks","훅"],["mcp","MCP"]];
var VIEW_TITLE = {files:"탐색기", rules:"규칙", skills:"스킬·에이전트·커맨드", hooks:"훅", mcp:"MCP"};
// 사이드바 역할 한 줄 설명 — 사이드바 상단 문구와 액티비티 바 툴팁이 같은 문장을 쓴다
var VIEW_HINT = {
  files:"전역 · 프로젝트 · 플러그인 설정 파일 트리. 클릭하면 에디터에서 원문·편집",
  rules:"선택 프로젝트에 실제로 적용되는 CLAUDE.md 체인 — 적용 순서대로",
  skills:"전역 · 이 프로젝트 · 플러그인의 스킬/에이전트/커맨드와 이 프로젝트에서의 ON/OFF",
  hooks:"settings.json 훅을 이벤트별 매처 → 명령 순서로. 색은 출처(전역/프로젝트/플러그인)",
  mcp:"MCP 서버를 출처별로"};
// 사이드바 컨텍스트 줄(툴바 아래 한 줄) — 그 목록이 무엇을 기준으로 정렬·수집됐는지
var VIEW_CTX = {rules:"적용 순서", skills:"ON/OFF 대상", hooks:"세션 이벤트 순",
                mcpOne:"전역 + 이 프로젝트", mcpAll:"전역 + 모든 프로젝트"};
var KIND_KO = {skill:"스킬", agent:"에이전트", command:"커맨드"};
var SCOPE_KO = {global:"전역",
  "global-rules":"전역 rules", project:"프로젝트", "project-local":"프로젝트 로컬",
  "project-rules":"프로젝트 rules", subdir:"하위 폴더"};
var COVER_KO = {home:"홈 디렉터리", "drive-root":"드라이브 루트", ancestor:"상위 폴더 중복"};
var MAX_TABS = 6;
var MAX_LINE_ROWS = 2000;
// sseq: 스캔 세대, fseq: 파일 세대, eseq: 유효 규칙 세대 / dead: 서버 종료 후 렌더 중단
// side: 사이드바 내용 ("files"|"rules"|"skills"|"hooks"|"mcp") — 에디터와 무관
// selHook/selMcp: 훅·MCP 사이드바에서 고른 항목 (인스펙터 표시용)
var S = {scan:null, project:null, side:"files", file:null, fileErr:null, filePath:null, msg:null, msgOk:false,
         fseq:0, sseq:0, eseq:0, loading:false, dead:false, scanErr:false,
         tabs:[], meta:Object.create(null), expanded:Object.create(null),
         eff:null, effErr:null, errOpen:false, selHook:null, selMcp:null,
         // cardq: 스킬 뷰 검색·종류 필터. 재스캔·프로젝트 전환에도 유지 (loadScan 이 건드리지 않음)
         cardq:{q:"", kinds:{skill:true, agent:true, command:true}},
         // toggleTarget: 토글 저장 대상 파일. toggleErr: 직전 토글 실패 메시지 (툴바 아래 한 줄)
         toggleTarget:"settings.local.json", toggleErr:null,
         // edit: 편집 중일 때만 객체 {path,text,dirty,issues,busy,conflict,msg,msgCls,range}
         //   range: 섹션 편집이면 {start,end,title} — 저장이 /api/save-range 로 간다
         edit:null, issues:null,
         // folds[path] = {헤딩 start: true} — 접힌 섹션. 파일 재로드·저장·재스캔에도 유지
         folds:Object.create(null),
         // conflicts: /api/rules 의 충돌 목록, conflictSel: 인스펙터에서 펼쳐 본 제목
         conflicts:null, conflictSel:null,
         // fileCache[path] = /api/file 응답 (충돌 본문 표시용) — 재스캔 시 비운다
         fileCache:Object.create(null), cacheBusy:Object.create(null),
         // cmpq: 규칙 사이드바의 제목 비교 검색어
         cmpq:"",
         // fileq/hookq/mcpq: 뷰별 툴바 상태. cardq 와 같이 재스캔·프로젝트 전환에도 유지
         fileq:{q:"", shared:false},
         hookq:{q:"", src:{global:true, project:true, plugin:true}},
         mcpq:{q:"", tr:{command:false, url:false}}};
/* 비교 가상 탭: 경로 자리에 "compare:<제목>" 을 쓴다 — 탭·에디터 기존 흐름을 그대로 탄다 */
var CMP = "compare:";
function isCompare(p){ return String(p||"").indexOf(CMP) === 0; }
function cmpTitle(p){ return String(p||"").slice(CMP.length); }
// 충돌 제목 → 항목. 제목이 __proto__ 여도 안전하도록 프로토타입 없는 객체
function conflictMap(){
  var m = Object.create(null);
  (S.conflicts||[]).forEach(function(c){ if(c && c.title) m[c.title] = c; });
  return m;
}
// 줄 배열 → 저장 본문 조립 (백엔드 replace_range 와 같은 정규화)
function rangeLines(text){
  return String(text||"").replace(/\r\n/g,"\n").replace(/\n+$/,"").split("\n");
}
function spliceLines(text, start, end, newText){
  var lines = String(text||"").split("\n");
  var args = [start, end - start].concat(rangeLines(newText));
  Array.prototype.splice.apply(lines, args);
  return lines.join("\n");
}
function retryBtn(fn){ var b = el("button","linkbtn", t("다시 시도")); b.onclick = fn; return b; }
// 개발용 훅: #sample 이면 정적 서버의 scan-sample.json을 스캔 응답 대신 사용
var SAMPLE = location.hash === "#sample";

function el(tag, cls, text){var e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e;}
function badge(text, cls){return el("span","badge"+(cls?" "+cls:""), text);}

function viewHint(text){return el("p","hint", text);}

/* ---------- 공용 UI 부품 (사이드바 4층 규격) ---------- */
var SVG_NS = "http://www.w3.org/2000/svg";
// 24 viewBox · stroke currentColor · fill none. 텍스트 라벨이 따로 있으므로 aria-hidden
var ICONS = {
  files:["M4 4h6l2 2h8v14H4z"],
  rules:["M6 4h12v16H6z","M9 9h6","M9 13h6","M9 17h3"],
  skills:["M12 3l2.5 5.5L20 9.5l-4 3.9.9 5.6L12 16.4 7.1 19l.9-5.6-4-3.9 5.5-1z"],
  hooks:["M4 12h4","M16 12h4","M8 12a4 4 0 0 1 8 0","M8 12a4 4 0 0 0 8 0"],
  mcp:["M5 7h14","M5 12h14","M5 17h14","M8 5v4","M16 10v4","M11 15v4"],
  rescan:["M20 12a8 8 0 1 1-2.3-5.7","M20 4v5h-5"],
  quit:["M12 3v9","M6.3 7.3a8 8 0 1 0 11.4 0"]};
function icon(name){
  var svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox","0 0 24 24");
  svg.setAttribute("width","18");
  svg.setAttribute("height","18");
  svg.setAttribute("fill","none");
  svg.setAttribute("stroke","currentColor");
  svg.setAttribute("stroke-width","1.6");
  svg.setAttribute("stroke-linecap","round");
  svg.setAttribute("stroke-linejoin","round");
  svg.setAttribute("aria-hidden","true");
  (ICONS[name] || []).forEach(function(d){
    var p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  });
  return svg;
}
// 행 오른쪽 메타 — 행당 태그 1개가 원칙 (나머지는 title 과 인스펙터가 텍스트로 남긴다)
function tag(text, cls){ return el("span","tag"+(cls ? " "+cls : ""), text); }
function warnEl(text){ return el("span","wn", "⚠ " + text); }
// 텍스트 없는 스위치 — aria-label·aria-checked 필수
function switchEl(o){
  var b = el("button","sw");
  b.setAttribute("role","switch");
  b.setAttribute("aria-checked", String(!!o.on));
  b.setAttribute("aria-label", o.label);
  if(o.key) b.setAttribute("data-key", o.key);
  if(o.title) b.title = o.title;
  b.disabled = !!o.disabled;
  if(o.onToggle) b.onclick = function(){ o.onToggle(b); };
  return b;
}
// 그룹 헤더 — 본문은 접기 button, 오른쪽 ctrl 은 형제 (중첩 button 금지). 열림 여부를 돌려준다
function groupHd(parent, o){
  var open = o.force ? true : isOpen(o.id, o.dflt);
  var wrap = el("div","grp");
  if(o.first) wrap.style.marginTop = "0";
  var b = el("button","grphd");
  b.setAttribute("aria-expanded", String(open));
  b.setAttribute("data-key", o.id);
  b.appendChild(el("span","arw", open ? "▾" : "▸"));
  b.appendChild(el("span","gt", o.title));
  if(o.count != null) b.appendChild(el("span","num", String(o.count)));
  if(o.title2) b.title = o.title2;
  b.onclick = o.onToggle || function(){ setOpen(o.id, o.dflt); };
  wrap.appendChild(b);
  if(o.ctrl) wrap.appendChild(o.ctrl);
  parent.appendChild(wrap);
  return open;
}
/* 28px 행. 구성 순서: 화살표 → [순번] → 이름 → [sub] → [경고] → [태그] → [숫자] → [스위치]
   래퍼 div + 본문 button + 형제 스위치 — 중첩 button 금지 */
function uiRow(parent, o){
  var wrap = el("div","r" + (o.src ? " src-"+o.src : "") + (o.sel ? " sel" : "") + (o.dim ? " dim" : ""));
  wrap.style.paddingLeft = (8 + (o.depth || 0) * 14) + "px";
  if(o.arrowBtn){
    var ab = el("button","arw", o.arrowBtn.open ? "▾" : "▸");
    ab.setAttribute("aria-expanded", String(!!o.arrowBtn.open));
    ab.setAttribute("aria-label", o.arrowBtn.label);
    ab.setAttribute("data-key", o.arrowBtn.key);
    if(o.arrowBtn.disabled){ ab.disabled = true; ab.textContent = ""; }
    ab.onclick = o.arrowBtn.onclick;
    wrap.appendChild(ab);
  }
  var b = el("button","rmain");
  if(o.key) b.setAttribute("data-key", o.key);
  if(o.title) b.title = o.title;
  if(o.ariaCurrent) b.setAttribute("aria-current","true");
  if(o.expanded != null) b.setAttribute("aria-expanded", String(o.expanded));
  if(!o.arrowBtn) b.appendChild(el("span","arw", o.arrow || ""));
  if(o.num != null && o.rnum) b.appendChild(el("span","rnum", String(o.num)));
  b.appendChild(el("span","nm"+(o.bold ? " b" : ""), o.name));
  if(o.sub) b.appendChild(el("span","sub", o.sub));
  if(o.warn) b.appendChild(warnEl(o.warn));
  if(o.tag) b.appendChild(tag(o.tag, o.tagCls));
  else if(o.count != null) b.appendChild(el("span","num", String(o.count)));
  if(o.onclick) b.onclick = o.onclick;
  else{ b.disabled = true; b.setAttribute("aria-disabled","true"); }
  wrap.appendChild(b);
  if(o.sw) wrap.appendChild(o.sw);
  parent.appendChild(wrap);
  return wrap;
}
function clear(n){while(n.firstChild) n.removeChild(n.firstChild); return n;}
function kb(n){return (typeof n==="number"? (n/1024).toFixed(1) : "?")+" KB";}
function ymd(mtime){
  if(typeof mtime!=="number") return "-";
  var d=new Date(mtime*1000), p=function(x){return (x<10?"0":"")+x;};
  return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());
}
function len(a){ return (a||[]).length; }
function keys(o){ return Object.keys(o||{}); }
// 파싱 실패면 null (버전 미확인)
function cmpVer(str){
  var m=/(\d+)\.(\d+)\.(\d+)/.exec(str||"");
  if(!m) return null;
  for(var i=0;i<3;i++){ var a=parseInt(m[i+1],10); if(a!==MIN_VER[i]) return a-MIN_VER[i]; }
  return 0;
}
async function getJSON(url){
  var r = await fetch(url), b=null;
  try{ b = await r.json(); }catch(e){}
  if(!r.ok) throw new Error((b&&b.error)||("HTTP "+r.status));
  if(b==null) throw new Error(t("응답을 읽지 못했습니다"));
  return b;
}
// 편집용 POST: 상태코드로 분기해야 하므로 throw 하지 않고 {status, ok, body} 를 준다
async function postJSON(url, body){
  var r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
                            body: JSON.stringify(body)}), b = null;
  try{ b = await r.json(); }catch(e){}
  return {status:r.status, ok:r.ok, body:b || {}};
}
function resErr(res){ return (res.body && res.body.error) || ("HTTP "+res.status); }

/* ---------- 설정 조회 헬퍼 ---------- */
function settingsData(obj){
  var out = {};
  keys(obj).forEach(function(k){
    var d = obj[k] && obj[k].data;
    if(d && typeof d === "object") out[k] = d;
  });
  return out;
}
// 전역 settings.json → 전역 local → 프로젝트 settings.json → 프로젝트 local 순 병합 (뒤가 우선)
// proj 미지정이면 선택 프로젝트(S.project) 기준
function mergedSetting(key, proj){
  var res = Object.create(null), sets = [];
  var pr = (proj === undefined) ? S.project : proj;
  if(S.scan && S.scan.global) sets.push(S.scan.global.settings);
  if(pr && pr.exists !== false) sets.push(pr.settings);
  sets.forEach(function(obj){
    var all = settingsData(obj);
    ["settings.json","settings.local.json"].forEach(function(k){
      var v = all[k] && all[k][key];
      if(v && typeof v === "object") keys(v).forEach(function(n){ res[n] = v[n]; });
    });
  });
  return res;
}
function skillOverrides(proj){ return mergedSetting("skillOverrides", proj); }
function enabledPlugins(){ return mergedSetting("enabledPlugins"); }
// skillOverrides 키: 스킬은 SKILL.md면 부모 디렉터리명, 아니면 파일명(확장자 제외).
// 커맨드는 파일명에서 확장자(.md/.toml 등) 제거. 에이전트는 오버라이드 대상 아님.
function overrideKey(f, kind){
  var name = String(f.name || "");
  if(kind === "skill" && name === "SKILL.md"){
    var seg = String(f.path || "").split(/[\\/]/);
    return seg[seg.length-2] || name;
  }
  return name.replace(/\.[^.\\/]+$/,"");
}
function pluginOff(pl){ return enabledPlugins()[pl.key] === false; }
// 병합값의 출처 — mergedSetting 과 같은 순서로 훑고 마지막에 이긴 파일을 돌려준다.
// 없으면 null (= 기본값). 전역 두 파일은 묶어서 "전역 설정".
function settingSource(section, key){
  var found = null;
  function look(obj, glabel){
    var all = settingsData(obj);
    ["settings.json","settings.local.json"].forEach(function(k){
      var v = all[k] && all[k][section];
      if(v && typeof v === "object" && Object.prototype.hasOwnProperty.call(v, key))
        found = {value:v[key], file:k, label: glabel || (k === "settings.json" ? "팀 설정" : "개인 설정")};
    });
  }
  if(S.scan && S.scan.global) look(S.scan.global.settings, "전역 설정");
  if(S.project && S.project.exists !== false) look(S.project.settings, null);
  return found;
}
// 토글 가능 = 존재하는 프로젝트가 선택돼 있을 때만
function toggleReady(){ return !!(S.project && S.project.exists !== false); }
// 프로젝트 settings 두 파일에 실제로 적힌 토글 키 수 (전역 제외)
function projToggleCount(p){
  var all = settingsData(p.settings), out = {skills:0, plugins:0};
  [["skillOverrides","skills"],["enabledPlugins","plugins"]].forEach(function(pair){
    var seen = Object.create(null);
    ["settings.json","settings.local.json"].forEach(function(k){
      var v = all[k] && all[k][pair[0]];
      if(v && typeof v === "object") keys(v).forEach(function(n){ seen[n] = true; });
    });
    out[pair[1]] = keys(seen).length;
  });
  return out;
}

/* ---------- 스캔 인덱스 (경로 → 표시용 메타) ---------- */
// 재스캔 후 선택 복원 + 인스펙터 속성 표시. API 계약의 "직전 스캔에 등장한 경로"와 동일 범위.
// 프로젝트 경로 기준 상대경로 (구분자 /), 접두어가 아니면 null
function relLabel(path, base){
  var p = String(path||"").replace(/\\/g,"/");
  var b = String(base||"").replace(/\\/g,"/").replace(/\/+$/,"");
  if(!b) return null;
  return p.toLowerCase().indexOf(b.toLowerCase()+"/") === 0 ? p.slice(b.length+1) : null;
}
// 홈 디렉터리 프로젝트는 ~/.claude 항목을 전역과 같은 경로로 다시 싣는다 — 전역 쪽만 렌더
var GPATHS = Object.create(null);
function dedupProj(p){
  if(p.coverage_reason !== "home") return p;
  var dup = function(f){ return !!(f && f.path && GPATHS[f.path]); };
  var q = {};
  keys(p).forEach(function(k){ q[k] = p[k]; });
  ["claude_md","rules","skills","agents","commands"].forEach(function(k){
    if(Array.isArray(p[k])) q[k] = p[k].filter(function(f){ return !dup(f); });
  });
  var st = Object.create(null);
  keys(p.settings).forEach(function(k){ if(!dup(p.settings[k])) st[k] = p.settings[k]; });
  q.settings = st;
  return q;
}
function scanIndex(sc){
  var set = Object.create(null);
  GPATHS = Object.create(null);
  function add(f, m){
    if(!f || !f.path || set[f.path]) return;
    var lazy = f.scope === "subdir";
    set[f.path] = {scope:m.scope, origin:m.origin, project:m.project || null, shared:!!f.shared,
                   lazy:lazy, label: lazy ? relLabel(f.path, m.project) : null};
  }
  function addAll(a, m){ (a||[]).forEach(function(f){ add(f, m); }); }
  function addSettings(o, m){ keys(o).forEach(function(k){ add(o[k], m); }); }
  function addKinds(o, origin, prefix, proj){
    addAll(o.skills, {scope:prefix+" skills", origin:origin, project:proj});
    addAll(o.agents, {scope:prefix+" agents", origin:origin, project:proj});
    addAll(o.commands, {scope:prefix+" commands", origin:origin, project:proj});
  }
  var g = sc.global || {};
  [g.claude_md].concat(g.rules||[], g.skills||[], g.agents||[], g.commands||[],
    keys(g.settings).map(function(k){ return g.settings[k]; }))
    .forEach(function(f){ if(f && f.path) GPATHS[f.path] = true; });
  add(g.claude_md, {scope:"전역", origin:"전역"});
  addAll(g.rules, {scope:"전역 rules", origin:"전역"});
  addSettings(g.settings, {scope:"전역 settings", origin:"전역"});
  addKinds(g, "전역", "전역");
  (sc.projects||[]).forEach(function(p){
    var o = p.name || p.path;
    (p.claude_md||[]).forEach(function(f){
      add(f, {scope: f.scope === "subdir" ? "하위 폴더" : "프로젝트", origin:o, project:p.path});
    });
    addAll(p.rules, {scope:"프로젝트 rules", origin:o, project:p.path});
    addSettings(p.settings, {scope:"프로젝트 settings", origin:o, project:p.path});
    addKinds(p, o, "프로젝트", p.path);
  });
  (sc.plugins||[]).forEach(function(pl){
    var o = "플러그인 " + (pl.name || pl.key);
    add(pl.manifest, {scope:"플러그인", origin:o});
    addAll(pl.skills, {scope:"플러그인 skills", origin:o});
    addAll(pl.commands, {scope:"플러그인 commands", origin:o});
  });
  return set;
}

// PRD §5 우선순위: 전역 스킬 → 프로젝트 스킬 → 에이전트 → 커맨드(전역·프로젝트) → 플러그인
function rankOf(kind, scope){       // scope: 0 전역, 1 프로젝트, 2 플러그인
  if(scope === 2) return 5;
  if(kind === "skill") return scope;
  if(kind === "agent") return 2 + scope;
  return 4;
}
// skills/ 아래 SKILL.md 가 아닌 부속 문서(reference.md 등)는 스킬이 아니다
function isSkillFile(f){ return !!f.name_meta || f.name === "SKILL.md"; }
function collect(){
  var out = [], g = (S.scan && S.scan.global) || {}, ov = skillOverrides();
  function push(arr, kind, scope, origin, extra){
    (arr||[]).forEach(function(f){
      if(kind === "skill" && !isSkillFile(f)) return;
      var key = overrideKey(f, kind);
      out.push({name:f.name_meta || key, kind:kind, origin:origin, rank:rankOf(kind, scope),
                desc:f.description, path:f.path, key:key, pluginOwned: scope === 2,
                off: extra ? extra.off : (kind !== "agent" && ov[key] === "off"),
                offLabel: extra ? extra.offLabel : "이 프로젝트에서 OFF"});
    });
  }
  push(g.skills,"skill",0,"전역"); push(g.agents,"agent",0,"전역"); push(g.commands,"command",0,"전역");
  if(S.project && S.project.exists !== false){
    push(S.project.skills,"skill",1,"프로젝트");
    push(S.project.agents,"agent",1,"프로젝트");
    push(S.project.commands,"command",1,"프로젝트");
  }
  ((S.scan && S.scan.plugins) || []).forEach(function(pl){
    if(pl.exists === false) return;
    // 플러그인 스킬에는 skillOverrides 미적용 (F7) — 플러그인 단위 OFF만
    var extra = {off: pluginOff(pl), offLabel:"플러그인 OFF"}, origin = "플러그인:"+(pl.name || pl.key);
    push(pl.skills,"skill",2,origin,extra);
    push(pl.commands,"command",2,origin,extra);
  });
  out.sort(function(a,b){ return a.rank - b.rank || a.name.localeCompare(b.name); });
  return out;
}
// 출처 섹션 — collect() 의 origin 문자열에서 되읽는다 (collect 는 그대로 둔다)
function cardSrc(c){
  // origin 값(내부 식별자)은 그대로 비교하고, label 만 표시용으로 번역한다
  if(c.origin === "전역") return {key:"g", label:t("전역"), rank:0};
  if(c.origin === "프로젝트") return {key:"p", label:t("이 프로젝트"), rank:1};
  var nm = c.origin.indexOf("플러그인:") === 0 ? c.origin.slice(5) : c.origin;
  return {key:"pl:"+nm, label:t("플러그인 {n}", {n:nm}), rank:2, plugin:nm};
}
function cardMatch(c){
  if(!S.cardq.kinds[c.kind]) return false;
  var q = S.cardq.q.trim().toLowerCase();
  if(!q) return true;
  return String(c.name||"").toLowerCase().indexOf(q) >= 0
      || String(c.desc||"").toLowerCase().indexOf(q) >= 0;
}

var LEVELS = [["on","on (제한 없음)"],["name-only","name-only (이름만)"],
              ["user-invocable-only","user-invocable-only (사용자 호출만)"],["off","off (사용 안 함)"]];

function hookCmds(h){
  return Array.isArray(h.commands) ? h.commands : (h.commands ? [h.commands] : []);
}
function hookSource(src){
  src = String(src || "");
  if(src.indexOf("global:") === 0) return {cls:"global", label:t("전역 · {n}", {n:src.slice(7)})};
  if(src.indexOf("plugin:") === 0) return {cls:"plugin", label:t("플러그인 · {n}", {n:src.slice(7)})};
  if(src.indexOf("project:") === 0){
    var rest = src.slice(8), i = rest.lastIndexOf(":");
    return i > 0 ? {cls:"project", label:t("프로젝트 · {p} · {f}", {p:rest.slice(0,i), f:rest.slice(i+1)})}
                 : {cls:"project", label:t("프로젝트 · {n}", {n:rest})};
  }
  return {cls:"", label:src || t("출처 미상")};
}
function groupHooks(hooks){
  // 이벤트명이 constructor/__proto__ 여도 안전하도록 프로토타입 없는 객체
  var order = [], byEvent = Object.create(null);
  hooks.forEach(function(h){
    var e = h.event || "(이벤트 없음)";
    if(!byEvent[e]){ byEvent[e] = []; order.push(e); }
    byEvent[e].push(h);
  });
  return {order:order, byEvent:byEvent};
}
