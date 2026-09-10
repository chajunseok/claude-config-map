// sidebar — 액티비티 바와 사이드바 5종(탐색기 트리·규칙·스킬·훅·MCP) 렌더와 선택
"use strict";
/* ---------- 액티비티 바 ---------- */
function renderActivity(){
  var bar = clear(document.getElementById("views"));
  VIEWS.forEach(function(v){
    var b = el("button", null, v[1]);
    b.setAttribute("role","tab");
    b.setAttribute("aria-selected", String(S.side === v[0]));
    b.setAttribute("aria-controls","sidebody");
    b.id = "tab-"+v[0];
    b.title = VIEW_TITLE[v[0]] + " — " + VIEW_HINT[v[0]];
    b.onclick = function(){ setSide(v[0]); };
    bar.appendChild(b);
  });
  document.getElementById("sidebody").setAttribute("aria-labelledby","tab-"+S.side);
}
// 사이드바 전환은 에디터를 건드리지 않는다 — 편집 중에도 목록 탐색 가능
function setSide(name){
  S.side = name;
  renderActivity();
  renderSide();
}

/* ---------- 탐색기 트리 ---------- */
function isOpen(id, dflt){ var v = S.expanded[id]; return v === undefined ? !!dflt : v; }
function setOpen(id, dflt){ S.expanded[id] = !isOpen(id, dflt); renderSide(); }
function rowEl(depth){
  var d = el("div","row d"+depth);
  d.style.paddingLeft = (6 + depth*14) + "px";
  return d;
}
// 표시명: 하위 폴더 CLAUDE.md 는 프로젝트 기준 상대경로
function labelOf(f){
  var m = S.meta[f.path];
  return (m && m.label) || f.name || f.path || "(이름 없음)";
}
function mainBtn(text, num, cls){
  var b = el("button","mn");
  b.appendChild(el("span","nm"+(cls?" "+cls:""), text));
  if(num != null) b.appendChild(el("span","num", String(num)));
  return b;
}
// 접기 행: 화살표는 표시용, 행 전체 버튼이 토글
function foldRow(parent, depth, id, dflt, label, num, cls){
  var open = isOpen(id, dflt);
  var r = rowEl(depth);
  r.appendChild(el("span","arw", open ? "▾" : "▸"));
  var b = mainBtn(label, num, cls);
  b.setAttribute("aria-expanded", String(open));
  b.setAttribute("data-key", id);
  b.onclick = function(){ setOpen(id, dflt); };
  r.appendChild(b);
  parent.appendChild(r);
  return open;
}
function fileTitle(f, extra){
  var t = (f.path || "") + " · " + (f.shared ? "팀 공유" : "개인");
  if(extra) t += " · " + extra;
  return t;
}
function fileRow(parent, depth, f, opts){
  opts = opts || {};
  var r = rowEl(depth);
  if(S.filePath === f.path) r.classList.add("sel");
  r.appendChild(el("span","arw",""));
  var b = mainBtn(labelOf(f), null, opts.cls);
  b.title = fileTitle(f, opts.note);
  b.setAttribute("data-key", f.path);
  b.onclick = function(){ openFile(f.path); };
  r.appendChild(b);
  parent.appendChild(r);
}
// 없는 항목: 클릭 불가 행
function emptyRow(parent, depth, label){
  var r = rowEl(depth);
  r.appendChild(el("span","arw",""));
  var b = mainBtn(label, null, "off");
  b.disabled = true;
  b.setAttribute("aria-disabled","true");
  r.appendChild(b);
  parent.appendChild(r);
}
function listNode(parent, depth, id, title, arr, kind, proj){
  arr = arr || [];
  if(!arr.length) return;
  var ov = kind ? skillOverrides(proj) : null;
  if(!foldRow(parent, depth, id, false, title, arr.length)) return;
  arr.forEach(function(f){
    var offed = ov && kind !== "agent" && ov[overrideKey(f, kind)] === "off";
    fileRow(parent, depth+1, f, offed ? {cls:"off", note:"skillOverrides OFF"} : null);
  });
}
function settingsNode(parent, depth, id, obj){
  var ks = keys(obj);
  if(!ks.length) return;
  if(!foldRow(parent, depth, id, false, "settings", ks.length)) return;
  ks.forEach(function(k){
    var v = obj[k];
    if(!v) return;
    fileRow(parent, depth+1, {path:v.path, name:k, size:v.size, mtime:v.mtime, shared:v.shared});
  });
}
function globalCount(g){
  return (g.claude_md?1:0) + len(g.rules) + keys(g.settings).length + len(g.skills) + len(g.agents) + len(g.commands);
}
function projCount(p){
  return len(p.claude_md) + len(p.rules) + keys(p.settings).length + len(p.skills) + len(p.agents) + len(p.commands);
}
function sideBody(){ return clear(document.getElementById("sidebody")); }
function sideCount(text){ document.getElementById("side-count").textContent = text || ""; }
// 사이드바 다시 그리기 — 재렌더 시 포커스 행 유지 (data-key 로 같은 버튼을 다시 찾는다)
function renderSide(){
  var host = document.getElementById("sidebody"), a = document.activeElement;
  var k = (a && host.contains(a)) ? a.getAttribute("data-key") : null;
  document.getElementById("side-title").textContent = VIEW_TITLE[S.side] || "";
  document.getElementById("sidehint").textContent = VIEW_HINT[S.side] || "";
  sideCount("");
  clear(host);
  if(S.side === "files") renderTreeBody(host);
  else if(S.side === "rules") renderRulesSide(host);
  else if(S.side === "skills") renderSkillsSide(host);
  else if(S.side === "hooks") renderHooksSide(host);
  else renderMcpSide(host);
  if(!k) return;
  var all = host.querySelectorAll("[data-key]");
  for(var i=0;i<all.length;i++){ if(all[i].getAttribute("data-key") === k){ all[i].focus(); return; } }
}
function renderTreeBody(root){
  if(!S.scan) return;
  var g = S.scan.global || {};
  var projects = S.scan.projects || [], plugins = S.scan.plugins || [];
  sideCount(projects.length + " 프로젝트");

  if(foldRow(root, 0, "g", true, "전역", globalCount(g), "b")){
    if(g.claude_md) fileRow(root, 1, g.claude_md);
    else emptyRow(root, 1, "CLAUDE.md 없음");
    listNode(root, 1, "g.rules", "rules", g.rules);
    settingsNode(root, 1, "g.settings", g.settings);
    listNode(root, 1, "g.skills", "skills", g.skills, "skill");
    listNode(root, 1, "g.agents", "agents", g.agents, "agent");
    listNode(root, 1, "g.commands", "commands", g.commands, "command");
  }
  if(foldRow(root, 0, "p", true, "프로젝트", projects.length, "b")){
    projects.forEach(function(p){ projectNode(root, p); });
  }
  if(foldRow(root, 0, "l", true, "플러그인", plugins.length, "b")){
    plugins.forEach(function(pl){ pluginNode(root, pl); });
  }
}
// 프로젝트 행은 화살표(접기)와 이름(선택)이 다른 동작 — 버튼 2개
function projectNode(parent, p){
  var id = "p:"+p.path, open = isOpen(id, false), gone = p.exists === false;
  var r = rowEl(1);
  var sel = S.project && S.project.path === p.path;
  if(sel) r.classList.add("sel");
  var tg = el("button","arw", open ? "▾" : "▸");
  tg.setAttribute("aria-expanded", String(open));
  tg.setAttribute("aria-label", (p.name||p.path)+" 하위 항목 "+(open?"접기":"펼치기"));
  tg.disabled = gone;
  if(gone) tg.textContent = "";
  tg.setAttribute("data-key", "tg:"+id);
  tg.onclick = function(){ setOpen(id, false); };
  r.appendChild(tg);
  var notes = [];
  if(gone) notes.push("경로 없음");
  if(p.coverage === "root-only") notes.push("루트만 · "+(COVER_KO[p.coverage_reason]||p.coverage_reason||"사유 미상"));
  if(p.truncated || p.incomplete) notes.push("일부만 스캔");
  var cls = gone ? "gone" : (notes.length ? "warn b" : "b");
  var d = dedupProj(p);
  var nb = mainBtn(p.name || p.path, gone ? null : projCount(d), cls);
  nb.title = p.path + (notes.length ? " · " + notes.join(" · ") : "");
  nb.setAttribute("data-key", id);
  if(sel) nb.setAttribute("aria-current","true");
  nb.onclick = function(){ selectProject(p); };
  r.appendChild(nb);
  parent.appendChild(r);
  if(gone || !open) return;
  (d.claude_md||[]).forEach(function(f){
    var lazy = f.scope === "subdir";
    fileRow(parent, 2, f, lazy ? {cls:"warn", note:"지연 로드"} : null);
  });
  listNode(parent, 2, id+".rules", "rules", d.rules);
  settingsNode(parent, 2, id+".settings", d.settings);
  listNode(parent, 2, id+".skills", "skills", d.skills, "skill", p);
  listNode(parent, 2, id+".agents", "agents", d.agents, "agent", p);
  listNode(parent, 2, id+".commands", "commands", d.commands, "command", p);
}
function pluginNode(parent, pl){
  var id = "l:"+pl.key, gone = pl.exists === false, offed = !gone && pluginOff(pl);
  var label = (pl.name || pl.key) + " " + (pl.version || "?");
  var cls = gone ? "gone" : (offed ? "off" : null);
  var open = foldRow(parent, 1, id, false, label, null, cls);
  var head = parent.lastChild.querySelector(".mn");
  head.title = (pl.path || "") + (gone ? " · 경로 없음" : (offed ? " · 플러그인 OFF" : ""));
  if(gone || !open) return;
  if(pl.manifest && pl.manifest.path)
    fileRow(parent, 2, {path:pl.manifest.path, name:"plugin.json", size:pl.manifest.size, mtime:pl.manifest.mtime, shared:pl.manifest.shared});
  listNode(parent, 2, id+".skills", "skills", pl.skills);
  listNode(parent, 2, id+".commands", "commands", pl.commands);
}
function selectProject(p){
  if(!guardEdit()) return;
  S.project = p;
  renderSide();
  loadEff();
  renderInspector();
  // ponytail: 사이드바 전환은 액티비티 바만 한다 — 프로젝트를 고른다고 트리를 감추지 않는다
}

/* 2. 유효 규칙 — 인스펙터 `함께 적용됨`과 같은 데이터를 공유 */
async function loadEff(){
  var proj = (S.project && S.project.exists !== false) ? S.project.path : null;
  S.eff = null; S.effErr = null;
  var seq = ++S.eseq;
  if(!proj) return;
  var sseq = S.sseq, items = null, err = null;
  try{
    items = await getJSON("/api/effective?project="+encodeURIComponent(proj));
  }catch(e){ err = e.message; }
  if(S.dead || seq !== S.eseq || sseq !== S.sseq) return;
  if(!S.project || S.project.path !== proj) return;   // 프로젝트가 바뀐 응답은 버린다
  S.eff = items; S.effErr = err;
  renderInspector();
  if(S.side === "rules") renderSide();
}
/* 사이드바 공통 행 — 본문 버튼 + (선택) 오른쪽 컨트롤. 중첩 button 금지라 래퍼는 div */
function baseName(path){ var seg = String(path||"").split(/[\/]/); return seg[seg.length-1] || String(path||""); }
function sideItem(parent, o){
  var wrap = el("div","sitem"+(o.cls ? " "+o.cls : "")+(o.sel ? " sel" : ""));
  var b = el("button","srow");
  if(o.key) b.setAttribute("data-key", o.key);
  if(o.title) b.title = o.title;
  if(o.sel) b.setAttribute("aria-current","true");
  var l1 = el("div","l1");
  if(o.lead) l1.appendChild(o.lead);
  l1.appendChild(el("span","t", o.text));
  b.appendChild(l1);
  if(o.badges && o.badges.length){
    var l2 = el("div","l2");
    o.badges.forEach(function(x){ if(x) l2.appendChild(x); });
    b.appendChild(l2);
  }
  if(o.onclick) b.onclick = o.onclick;
  wrap.appendChild(b);
  if(o.ctrl) wrap.appendChild(o.ctrl);
  parent.appendChild(wrap);
  return wrap;
}
function sideMsg(parent, text, cls){ parent.appendChild(el("div","pad "+(cls || "hint"), text)); }

/* 사이드바 2. 규칙 — 적용 순서대로. 본문은 에디터가 보여준다 */
function renderRulesSide(root){
  if(!S.project){ sideMsg(root, "파일 사이드바에서 프로젝트를 선택하세요."); return; }
  if(S.project.exists === false){ sideMsg(root, "경로가 존재하지 않는 프로젝트입니다."); return; }
  var pname = S.project.name || S.project.path;
  sideCount(pname);
  if(S.effErr){
    sideMsg(root, "유효 규칙을 불러오지 못했습니다: "+S.effErr, "err");
    root.appendChild(el("div","pad")).appendChild(retryBtn(loadEff));
    return;
  }
  if(!S.eff){ sideMsg(root, "불러오는 중…"); return; }
  if(!S.eff.length){ sideMsg(root, "적용되는 규칙 파일이 없습니다."); return; }
  sideCount(S.eff.length + "개 · " + pname);
  S.eff.forEach(function(it, i){
    var m = S.meta[it.path] || {};
    sideItem(root, {text: m.label || baseName(it.path), key: it.path, title: it.path,
      sel: S.filePath === it.path, lead: el("span","rnum", String(i+1)),
      badges: [badge(SCOPE_KO[it.scope] || it.scope),
               it.shared ? badge("팀 공유","shared") : null,
               it.lazy ? badge("지연 로드","warn") : null],
      onclick: function(){ openFile(it.path); }});
  });
}

/* 3. 스킬·에이전트·커맨드 */

// 사이드바 상단 검색 + 종류 칩. 툴바는 다시 그리지 않는다 — 행 영역만 갱신해야 입력 포커스가 유지된다
function cardBar(){
  var bar = el("div","tbar");
  var inp = el("input");
  inp.type = "search";
  inp.placeholder = "이름·설명 검색";
  inp.setAttribute("aria-label","스킬·에이전트·커맨드 이름·설명 검색");
  inp.setAttribute("data-key","cardq");
  inp.value = S.cardq.q;
  inp.oninput = function(){ S.cardq.q = inp.value; renderCardBody(); };
  bar.appendChild(inp);
  ["skill","agent","command"].forEach(function(k){
    var b = el("button","chip", KIND_KO[k]);
    b.setAttribute("aria-pressed", String(!!S.cardq.kinds[k]));
    b.setAttribute("data-key","chip:"+k);
    b.onclick = function(){
      S.cardq.kinds[k] = !S.cardq.kinds[k];
      b.setAttribute("aria-pressed", String(!!S.cardq.kinds[k]));
      renderCardBody();
    };
    bar.appendChild(b);
  });
  return bar;
}

// 사이드바 행 오른쪽 ON/OFF 스위치 (스킬·커맨드만)
function skillSwitch(c){
  var cur = skillOverrides()[c.key] || "on", on = cur !== "off";
  var sw = el("button","switch", on ? "ON" : "OFF");
  sw.setAttribute("role","switch");
  sw.setAttribute("aria-checked", String(on));
  sw.setAttribute("aria-label", c.name + " — 이 프로젝트에서 사용");
  sw.setAttribute("data-key","sw:"+c.kind+":"+c.key);
  sw.title = "이 프로젝트에서 사용";
  sw.disabled = !toggleReady();
  sw.onclick = function(){ doToggle("skillOverrides", c.key, on ? "off" : "on", [sw]); };
  return sw;
}

// 플러그인 섹션 헤더의 ON/OFF — enabledPlugins 는 플러그인 단위
function pluginSwitch(pl){
  var on = !pluginOff(pl);
  var b = el("button","switch", on ? "ON" : "OFF");
  b.setAttribute("role","switch");
  b.setAttribute("aria-checked", String(on));
  b.setAttribute("aria-label", (pl.name || pl.key) + " — 이 프로젝트에서 플러그인 사용");
  b.setAttribute("data-key","plsw:"+pl.key);
  b.title = "이 프로젝트에서 플러그인 사용";
  b.disabled = !toggleReady();
  b.onclick = function(){ doToggle("enabledPlugins", pl.key, on ? false : true, [b]); };
  var wrap = el("span","ctl");
  wrap.appendChild(b);
  var src = settingSource("enabledPlugins", pl.key);
  if(src) wrap.appendChild(badge(src.label));
  return wrap;
}
/* 사이드바 3. 스킬·에이전트·커맨드 */
function renderSkillsSide(root){
  if(!S.scan) return;
  root.appendChild(cardBar());
  var body = el("div");
  body.id = "cardbody";
  root.appendChild(body);
  renderCardBody();
}
function renderCardBody(){
  var body = document.getElementById("cardbody");
  if(!body) return;
  clear(body);
  var all = collect(), shown = all.filter(cardMatch);
  sideCount("표시 " + shown.length + " / 전체 " + all.length);
  var pMap = Object.create(null);
  ((S.scan && S.scan.plugins) || []).forEach(function(pl){ pMap[pl.name || pl.key] = pl; });
  var order = [], by = Object.create(null);
  shown.forEach(function(c){
    var s = cardSrc(c);
    if(!by[s.key]){ by[s.key] = {src:s, items:[]}; order.push(by[s.key]); }
    by[s.key].items.push(c);
  });
  order.sort(function(a,b){ return a.src.rank - b.src.rank || a.src.label.localeCompare(b.src.label); });
  if(!order.length){ sideMsg(body, "조건에 맞는 항목이 없습니다."); return; }
  var searching = !!S.cardq.q.trim();
  order.forEach(function(sec){
    var id = "cards:" + sec.src.key, dflt = sec.src.rank < 2;
    // 검색 중에는 매칭이 있는 섹션을 펼쳐 보여준다 — 저장된 접힘 상태는 그대로
    var open = searching || isOpen(id, dflt);
    var h = el("button","cardsec");
    h.setAttribute("aria-expanded", String(open));
    h.setAttribute("data-key", id);
    h.appendChild(el("span","arw", open ? "▾" : "▸"));
    h.appendChild(el("span", null, sec.src.label + " (" + sec.items.length + ")"));
    var pl = sec.src.plugin ? pMap[sec.src.plugin] : null;
    if(pl && pluginOff(pl)) h.appendChild(badge("플러그인 OFF","off"));
    h.onclick = function(){ S.expanded[id] = !isOpen(id, dflt); renderCardBody(); };
    var hw = el("div","cardsechd");
    hw.appendChild(h);
    if(pl && pl.exists !== false) hw.appendChild(pluginSwitch(pl));
    body.appendChild(hw);
    if(!open) return;
    sec.items.forEach(function(c){
      // 에이전트는 skillOverrides 대상이 아니고, 플러그인 내부 항목은 플러그인 단위로만 켜고 끈다
      var ctrl = (c.kind !== "agent" && !c.pluginOwned && toggleReady()) ? skillSwitch(c) : null;
      sideItem(body, {text: c.name, key: c.path, title: c.path, sel: S.filePath === c.path,
        cls: c.off ? "dim" : "", ctrl: ctrl,
        badges: [badge(KIND_KO[c.kind] || c.kind, "k-"+c.kind),
                 c.off ? badge(c.offLabel || "OFF","off") : null],
        onclick: function(){ openFile(c.path); }});
    });
  });
}

/* 4. 훅 흐름 */

// 훅 출처가 settings 파일이면 그 파일 경로 — 플러그인 출처는 열 파일이 없다
function hookFile(src){
  src = String(src || "");
  var g = (S.scan && S.scan.global) || {};
  if(src.indexOf("global:") === 0){
    var e = (g.settings || {})[src.slice(7)];
    return (e && e.path) || null;
  }
  if(src.indexOf("project:") === 0){
    var rest = src.slice(8), i = rest.lastIndexOf(":");
    if(i <= 0) return null;
    var path = rest.slice(0, i), name = rest.slice(i+1);
    var pr = ((S.scan && S.scan.projects) || []).filter(function(x){ return x.path === path; })[0];
    var pe = pr && (pr.settings || {})[name];
    return (pe && pe.path) || null;
  }
  return null;
}
function hookKey(h){ return (h.event||"") + "|" + (h.matcher||"") + "|" + (h.source||""); }
function selectHook(h){
  var f = hookFile(h.source);
  if(f) openFile(f);      // openFile 이 선택을 지우므로 바로 되살린다
  S.selHook = h; S.selMcp = null;
  renderSide();
  renderInspector();
}
/* 사이드바 4. 훅 — 이벤트별 그룹 → 매처 행 */
function renderHooksSide(root){
  var hooks = (S.scan && S.scan.hooks) || [];
  sideCount(hooks.length + "개");
  if(!hooks.length){ sideMsg(root, "등록된 훅이 없습니다."); return; }
  var g = groupHooks(hooks), sel = S.selHook ? hookKey(S.selHook) : null;
  g.order.forEach(function(ev){
    root.appendChild(el("div","sechd", ev+" ("+g.byEvent[ev].length+")"));
    g.byEvent[ev].forEach(function(h){
      var src = hookSource(h.source), n = hookCmds(h).length;
      sideItem(root, {text: "매처 " + (h.matcher || "(없음)"), key: "hook:"+hookKey(h),
        title: src.label + " → " + (hookCmds(h).join(" · ") || "(명령 없음)"),
        cls: src.cls, sel: sel === hookKey(h),
        badges: [badge("명령 "+n+"개"),
                 h.warn === "duplicate-star" ? badge("⚠ * 매처와 중복 발화","warn") : null],
        onclick: function(){ selectHook(h); }});
    });
  });
}

/* 사이드바 5. MCP — 출처별 그룹 → 서버 행 */
// 출처 그룹: {key, label, file, items:[{name, config}]}
function mcpGroups(){
  var order = [], by = Object.create(null);
  function grp(key, label, file){
    if(!by[key]){ by[key] = {key:key, label:label, file:file || null, items:[]}; order.push(by[key]); }
    return by[key];
  }
  ((S.scan && S.scan.mcp) || []).forEach(function(m){
    var s = m.source || "(출처 없음)";
    var label = s === "global" ? "전역"
      : s.indexOf("project:") === 0 ? "프로젝트 · "+s.slice(8)
      : s.indexOf("plugin:") === 0 ? "플러그인 · "+s.slice(7) : s;
    grp("src:"+s, label).items.push(m);
  });
  ((S.scan && S.scan.plugins) || []).forEach(function(pl){
    if(pl.exists === false) return;
    var srv = pl.mcp_servers || {};
    keys(srv).forEach(function(n){
      grp("plugin:"+pl.key, "플러그인 · "+(pl.name || pl.key)).items.push({name:n, config:srv[n]});
    });
  });
  // 프로젝트 루트 .mcp.json — 선택 프로젝트가 있으면 그 프로젝트만
  var projs = (S.project && S.project.exists !== false) ? [S.project] : ((S.scan && S.scan.projects) || []);
  projs.forEach(function(pr){
    var mj = pr.mcp_json;
    if(!mj || !mj.data || typeof mj.data !== "object") return;
    var srv = mj.data.mcpServers || {};
    keys(srv).forEach(function(n){
      grp("pmcp:"+(mj.path || pr.path || ""), "프로젝트 .mcp.json · "+(pr.name || pr.path), mj.path)
        .items.push({name:n, config:srv[n]});
    });
  });
  return order;
}
function selectMcp(m){
  if(m.file) openFile(m.file);   // openFile 이 선택을 지우므로 바로 되살린다
  S.selMcp = m; S.selHook = null;
  renderSide();
  renderInspector();
}
function renderMcpSide(root){
  var groups = mcpGroups(), n = 0;
  groups.forEach(function(g){ n += g.items.length; });
  sideCount(n + "개");
  if(!groups.length){ sideMsg(root, "등록된 MCP 서버가 없습니다."); return; }
  groups.forEach(function(g){
    root.appendChild(el("div","sechd", g.label + " (" + g.items.length + ")"));
    g.items.forEach(function(it){
      var cfg = (it.config && typeof it.config === "object") ? it.config : {};
      var sel = {name:it.name, config:it.config, label:g.label, file:g.file};
      sideItem(root, {text: it.name || "(이름 없음)", key: "mcp:"+g.key+":"+it.name,
        title: g.label + " · " + (cfg.command || cfg.url || "-"),
        sel: !!(S.selMcp && S.selMcp.name === it.name && S.selMcp.label === g.label),
        badges: [badge(cfg.command ? "command" : (cfg.url ? "url" : "설정 없음"))],
        onclick: function(){ selectMcp(sel); }});
    });
  });
}
