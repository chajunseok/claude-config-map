// sidebar — 액티비티 바와 사이드바 5종. 4층 규격: 헤더 → 툴바 → [컨텍스트 줄] → 그룹 헤더 → 28px 행
"use strict";
/* ---------- 액티비티 바 (아이콘 18px + 10px 라벨 + 왼쪽 인디케이터) ---------- */
function actBtn(name, label, title){
  var b = el("button");
  b.appendChild(icon(name));
  b.appendChild(el("span", null, label));
  b.title = title;
  return b;
}
function renderActivity(){
  var bar = clear(document.getElementById("views"));
  VIEWS.forEach(function(v){
    var b = actBtn(v[0], t(v[1]), t(VIEW_TITLE[v[0]]) + " — " + t(VIEW_HINT[v[0]]));
    b.setAttribute("role","tab");
    b.setAttribute("aria-selected", String(S.side === v[0]));
    b.setAttribute("aria-controls","sidebody");
    b.id = "tab-"+v[0];
    b.onclick = function(){ setSide(v[0]); };
    bar.appendChild(b);
  });
  // 하단 툴 — 상태바의 재스캔·종료와 같은 핸들러 (두 곳에서 찾을 수 있게)
  var tools = clear(document.getElementById("acttools"));
  tools.appendChild(el("div","divider"));
  // 언어 토글 — 라벨은 지금 언어의 반대쪽
  var lg = actBtn("lang", LANG === "ko" ? "EN" : "한", t("언어 전환"));
  lg.setAttribute("aria-label", t("언어 전환"));
  lg.onclick = function(){
    if(S.edit && !confirm(t("저장하지 않은 변경이 있습니다. 언어를 바꾸면 사라집니다. 계속할까요?"))) return;
    setLang(LANG === "ko" ? "en" : "ko");
  };
  tools.appendChild(lg);
  var re = actBtn("rescan", t(S.loading ? "스캔 중" : "재스캔"), t("설정을 다시 스캔"));
  re.disabled = S.loading;
  re.onclick = loadScan;
  tools.appendChild(re);
  var sd = actBtn("quit", t("종료"), t("서버 종료"));
  sd.onclick = shutdown;
  tools.appendChild(sd);
  document.getElementById("sidebody").setAttribute("aria-labelledby","tab-"+S.side);
}
// 사이드바 전환은 에디터를 건드리지 않는다 — 편집 중에도 목록 탐색 가능
function setSide(name){
  S.side = name;
  renderActivity();
  renderSide();
}

/* ---------- 공통 ---------- */
function isOpen(id, dflt){ var v = S.expanded[id]; return v === undefined ? !!dflt : v; }
function setOpen(id, dflt){ S.expanded[id] = !isOpen(id, dflt); renderSide(); }
function baseName(path){ var seg = String(path||"").split(/[\\/]/); return seg[seg.length-1] || String(path||""); }
function sideBody(){ return clear(document.getElementById("sidebody")); }
function sideCount(text){ document.getElementById("side-count").textContent = text || ""; }
function sideMsg(parent, text, cls){ parent.appendChild(el("div","pad "+(cls || "hint"), text)); }
// 표시명: 하위 폴더 CLAUDE.md 는 프로젝트 기준 상대경로
function labelOf(f){
  var m = S.meta[f.path];
  return (m && m.label) || f.name || f.path || t("(이름 없음)");
}
function fileTitle(f, extra){
  var s = (f.path || "") + " · " + t(f.shared ? "팀 공유" : "개인");
  if(extra) s += " · " + extra;
  return s;
}
function searchInput(ph, key, get, set){
  var inp = el("input");
  inp.type = "search";
  inp.placeholder = ph;
  inp.setAttribute("aria-label", ph);
  inp.setAttribute("data-key", key);
  inp.value = get();
  inp.oninput = function(){ set(inp.value); };
  return inp;
}
function chipBtn(label, on, key, onclick){
  var b = el("button","chip", label);
  b.setAttribute("aria-pressed", String(!!on));
  b.setAttribute("data-key", key);
  b.onclick = function(){ onclick(b); };
  return b;
}
function ctxOn(ctx, label){
  ctx.className = "ctxline";
  ctx.hidden = false;
  if(label) ctx.appendChild(el("span", null, label));
  return ctx;
}

/* ---------- 툴바 (뷰가 바뀔 때만 다시 만든다 — 검색 포커스·IME 보존) ---------- */
var SIDETOOL = null;
function buildTool(slot){
  var tb = el("div","tbar");
  if(S.side === "files"){
    tb.appendChild(searchInput(t("파일·프로젝트 검색"),"fileq",
      function(){ return S.fileq.q; },
      function(v){ S.fileq.q = v; renderSide(); }));
    tb.appendChild(chipBtn(t("팀 공유"), S.fileq.shared, "chip:shared", function(b){
      S.fileq.shared = !S.fileq.shared;
      b.setAttribute("aria-pressed", String(S.fileq.shared));
      renderSide();
    }));
  }else if(S.side === "rules"){
    var inp = searchInput(t("제목으로 프로젝트 간 비교"),"cmpq",
      function(){ return S.cmpq; }, function(v){ S.cmpq = v; });
    inp.onkeydown = function(ev){
      if(ev.key !== "Enter") return;
      ev.preventDefault();
      openCompare(inp.value);
    };
    tb.appendChild(inp);
    tb.appendChild(chipBtn(t("⇄ 비교"), false, "cmpgo", function(){ openCompare(S.cmpq); }));
  }else if(S.side === "skills"){
    tb.appendChild(searchInput(t("이름·설명 검색"),"cardq",
      function(){ return S.cardq.q; },
      function(v){ S.cardq.q = v; renderCardBody(); }));
    ["skill","agent","command"].forEach(function(k){
      tb.appendChild(chipBtn(t(KIND_KO[k]), S.cardq.kinds[k], "chip:"+k, function(b){
        S.cardq.kinds[k] = !S.cardq.kinds[k];
        b.setAttribute("aria-pressed", String(!!S.cardq.kinds[k]));
        renderCardBody();
      }));
    });
  }else if(S.side === "hooks"){
    tb.appendChild(searchInput(t("이벤트·매처·명령 검색"),"hookq",
      function(){ return S.hookq.q; },
      function(v){ S.hookq.q = v; renderSide(); }));
    [["global","전역"],["project","프로젝트"],["plugin","플러그인"]].forEach(function(p){
      tb.appendChild(chipBtn(t(p[1]), S.hookq.src[p[0]], "hchip:"+p[0], function(b){
        S.hookq.src[p[0]] = !S.hookq.src[p[0]];
        b.setAttribute("aria-pressed", String(!!S.hookq.src[p[0]]));
        renderSide();
      }));
    });
  }else{
    tb.appendChild(searchInput(t("서버 이름 검색"),"mcpq",
      function(){ return S.mcpq.q; },
      function(v){ S.mcpq.q = v; renderSide(); }));
    ["command","url"].forEach(function(k){
      tb.appendChild(chipBtn(k, S.mcpq.tr[k], "mchip:"+k, function(b){
        S.mcpq.tr[k] = !S.mcpq.tr[k];
        b.setAttribute("aria-pressed", String(!!S.mcpq.tr[k]));
        renderSide();
      }));
    });
  }
  slot.appendChild(tb);
}
// 사이드바 다시 그리기 — 재렌더 시 포커스 행 유지 (data-key 로 같은 버튼을 다시 찾는다)
function renderSide(){
  var host = document.getElementById("sidebody"), a = document.activeElement;
  var k = (a && host.contains(a)) ? a.getAttribute("data-key") : null;
  // 같은 뷰 재렌더면 스크롤 위치 유지 — clear() 가 스크롤을 0으로 되돌리고 focus() 가 행을 끌어와 위치가 튀는 것 방지
  var top = (SIDETOOL === S.side) ? host.scrollTop : 0;
  document.getElementById("side-title").textContent = t(VIEW_TITLE[S.side] || "");
  sideCount("");
  if(SIDETOOL !== S.side){
    SIDETOOL = S.side;
    buildTool(clear(document.getElementById("sidetool")));
  }
  var ctx = clear(document.getElementById("sidectx"));
  ctx.hidden = true;
  clear(host);
  if(S.side === "files") renderTreeBody(host);
  else if(S.side === "rules") renderRulesSide(host, ctx);
  else if(S.side === "skills") renderSkillsSide(host, ctx);
  else if(S.side === "hooks") renderHooksSide(host, ctx);
  else renderMcpSide(host, ctx);
  renderStatus();
  host.scrollTop = top;
  if(!k) return;
  var all = host.querySelectorAll("[data-key]");
  for(var i=0;i<all.length;i++){
    if(all[i].getAttribute("data-key") === k){ all[i].focus({preventScroll:true}); return; }
  }
}

/* ---------- 1. 탐색기 트리 ---------- */
// 검색: 이름·경로 부분일치. 매칭 행과 그 조상만 보이고, 검색 중엔 접힘을 무시한다
function fq(){ return S.fileq.q.trim().toLowerCase(); }
function fileFilterOn(){ return !!fq() || !!S.fileq.shared; }
function hitFile(f, all){
  if(!f || !f.path) return false;
  if(S.fileq.shared && !f.shared) return false;
  var q = fq();
  if(!q || all) return true;
  return String(f.name||"").toLowerCase().indexOf(q) >= 0
      || String(f.path||"").toLowerCase().indexOf(q) >= 0;
}
function hitCount(arr, all){
  var n = 0;
  (arr||[]).forEach(function(f){ if(hitFile(f, all)) n++; });
  return n;
}
function setFiles(o){ return keys(o).map(function(k){ return o[k]; }); }
// 트리 안의 폴더 행 — 화살표 + 굵은 이름 + 숫자
function treeFold(parent, depth, id, label, count, src, dflt){
  var open = fileFilterOn() ? true : isOpen(id, dflt);
  uiRow(parent, {depth:depth, src:src, arrow: open ? "▾" : "▸", name:label, bold:true,
    count:count, key:id, expanded:open, onclick: function(){ setOpen(id, dflt); }});
  return open;
}
function fileRow(parent, depth, f, src, opts){
  opts = opts || {};
  var lazy = f.scope === "subdir";
  uiRow(parent, {depth:depth, src:src, sel: S.filePath === f.path, dim: !!opts.dim,
    name: labelOf(f), key: f.path, title: fileTitle(f, opts.note),
    warn: lazy ? t("지연") : null,
    tag: lazy ? null : (opts.tag || t(f.shared ? "팀 공유" : "개인")),
    tagCls: (!lazy && !opts.tag && f.shared) ? "shared" : opts.tagCls,
    onclick: function(){ openFile(f.path); }});
}
function emptyRow(parent, depth, label, src){
  uiRow(parent, {depth:depth, src:src, dim:true, name:label});
}
function listNode(parent, depth, id, title, arr, kind, proj, src, all){
  var items = (arr||[]).filter(function(f){ return hitFile(f, all); });
  if(!items.length) return;
  var ov = kind ? skillOverrides(proj) : null;
  if(!treeFold(parent, depth, id, title, items.length, src, false)) return;
  items.forEach(function(f){
    var offed = ov && kind !== "agent" && ov[overrideKey(f, kind)] === "off";
    fileRow(parent, depth+1, f, src, offed ? {dim:true, note:t("skillOverrides OFF")} : null);
  });
}
function settingsNode(parent, depth, id, obj, src, all){
  var items = setFiles(obj).filter(function(f){ return hitFile(f, all); });
  if(!items.length) return;
  if(!treeFold(parent, depth, id, "settings", items.length, src, false)) return;
  keys(obj).forEach(function(k){
    var v = obj[k];
    if(!v || items.indexOf(v) < 0) return;
    fileRow(parent, depth+1, {path:v.path, name:k, size:v.size, mtime:v.mtime, shared:v.shared}, src);
  });
}
function globalFiles(g){
  return [g.claude_md].concat(g.rules||[], g.skills||[], g.agents||[], g.commands||[],
                              setFiles(g.settings));
}
function projFiles(d){
  return (d.claude_md||[]).concat(d.rules||[], d.skills||[], d.agents||[], d.commands||[],
                                  setFiles(d.settings));
}
function projNameHit(p){
  var q = fq();
  if(!q) return true;
  return String(p.name||"").toLowerCase().indexOf(q) >= 0
      || String(p.path||"").toLowerCase().indexOf(q) >= 0;
}
function renderTreeBody(root){
  if(!S.scan) return;
  var g = S.scan.global || {};
  var projects = S.scan.projects || [], plugins = S.scan.plugins || [];
  sideCount(t("{n} 프로젝트", {n:projects.length}));
  if(groupHd(root, {id:"g", title:t("전역"), count:hitCount(globalFiles(g), false), dflt:true,
                    force:fileFilterOn()})){
    if(g.claude_md && hitFile(g.claude_md, false)) fileRow(root, 0, g.claude_md, "global");
    else if(!g.claude_md && !fileFilterOn()) emptyRow(root, 0, t("CLAUDE.md 없음"), "global");
    listNode(root, 0, "g.rules", "rules", g.rules, null, null, "global", false);
    settingsNode(root, 0, "g.settings", g.settings, "global", false);
    listNode(root, 0, "g.skills", "skills", g.skills, "skill", null, "global", false);
    listNode(root, 0, "g.agents", "agents", g.agents, "agent", null, "global", false);
    listNode(root, 0, "g.commands", "commands", g.commands, "command", null, "global", false);
  }
  if(groupHd(root, {id:"p", title:t("프로젝트"), count:projects.length, dflt:true,
                    force:fileFilterOn()})){
    projects.forEach(function(p){ projectNode(root, p); });
  }
  if(groupHd(root, {id:"l", title:t("플러그인"), count:plugins.length, dflt:true,
                    force:fileFilterOn()})){
    plugins.forEach(function(pl){ pluginNode(root, pl); });
  }
}
// 프로젝트 행은 화살표(접기)와 이름(선택)이 다른 동작 — 형제 버튼 2개
function projectNode(parent, p){
  var id = "p:"+p.path, gone = p.exists === false;
  var open = fileFilterOn() ? true : isOpen(id, false);
  var sel = !!(S.project && S.project.path === p.path);
  var d = dedupProj(p), nameHit = projNameHit(p);
  var cnt = gone ? 0 : hitCount(projFiles(d), nameHit);
  var keep = nameHit && !S.fileq.shared;   // 이름이 걸린 프로젝트는 파일이 없어도 남긴다
  if(fileFilterOn() && !cnt && !keep) return;
  var notes = [];
  if(gone) notes.push(t("경로 없음"));
  if(p.coverage === "root-only")
    notes.push(t("루트만 · {n}",
                 {n: COVER_KO[p.coverage_reason] ? t(COVER_KO[p.coverage_reason])
                                                 : (p.coverage_reason || t("사유 미상"))}));
  if(p.truncated || p.incomplete) notes.push(t("일부만 스캔"));
  var warn = gone ? null
    : (p.coverage === "root-only" ? t("루트만")
                                  : ((p.truncated || p.incomplete) ? t("일부만") : null));
  uiRow(parent, {depth:0, src:"project", sel:sel, dim:gone, bold:true,
    arrowBtn:{open:open, disabled:gone, key:"tg:"+id,
              label:t(open ? "{n} 하위 항목 접기" : "{n} 하위 항목 펼치기",
                      {n:p.name||p.path}),
              onclick:function(){ setOpen(id, false); }},
    name: p.name || p.path, key:id, ariaCurrent:sel,
    title: p.path + (notes.length ? " · " + notes.join(" · ") : ""),
    warn: warn, tag: gone ? t("경로 없음") : null, count: (gone ? null : cnt),
    // 이름 클릭 = 선택 + 접혀 있고 하위 항목이 있으면 바로 펼침 (닫기는 화살표로만)
    onclick: function(){ if(!gone && !open && cnt > 0) S.expanded[id] = true; selectProject(p); }});
  if(gone || !open) return;
  (d.claude_md||[]).forEach(function(f){
    if(!hitFile(f, nameHit)) return;
    fileRow(parent, 1, f, "project", f.scope === "subdir" ? {note:t("지연 로드")} : null);
  });
  listNode(parent, 1, id+".rules", "rules", d.rules, null, null, "project", nameHit);
  settingsNode(parent, 1, id+".settings", d.settings, "project", nameHit);
  listNode(parent, 1, id+".skills", "skills", d.skills, "skill", p, "project", nameHit);
  listNode(parent, 1, id+".agents", "agents", d.agents, "agent", p, "project", nameHit);
  listNode(parent, 1, id+".commands", "commands", d.commands, "command", p, "project", nameHit);
}
function pluginNode(parent, pl){
  var id = "l:"+pl.key, gone = pl.exists === false, offed = !gone && pluginOff(pl);
  var nameHit = !fq() || String(pl.name || pl.key).toLowerCase().indexOf(fq()) >= 0;
  var files = gone ? [] : [pl.manifest].concat(pl.skills||[], pl.commands||[]);
  var cnt = hitCount(files, nameHit);
  if(fileFilterOn() && !cnt && !(nameHit && !S.fileq.shared)) return;
  var label = (pl.name || pl.key) + " " + (pl.version || "?");
  var open = fileFilterOn() ? true : isOpen(id, false);
  uiRow(parent, {depth:0, src:"plugin", dim: gone || offed, bold:true,
    arrowBtn:{open:open, disabled:gone, key:"tg:"+id,
              label:t(open ? "{n} 하위 항목 접기" : "{n} 하위 항목 펼치기",
                      {n:label}),
              onclick:function(){ setOpen(id, false); }},
    name: label, key:id, expanded:open,
    title: (pl.path || "") + (gone ? " · " + t("경로 없음")
                                  : (offed ? " · " + t("플러그인 OFF") : "")),
    tag: gone ? t("경로 없음") : (offed ? "OFF" : null), tagCls: offed ? "off" : null,
    count: (gone || offed) ? null : cnt,
    onclick: function(){ setOpen(id, false); }});
  if(gone || !open) return;
  if(pl.manifest && pl.manifest.path && hitFile(pl.manifest, nameHit))
    fileRow(parent, 1, {path:pl.manifest.path, name:"plugin.json", size:pl.manifest.size,
                        mtime:pl.manifest.mtime, shared:pl.manifest.shared}, "plugin");
  listNode(parent, 1, id+".skills", "skills", pl.skills, null, null, "plugin", nameHit);
  listNode(parent, 1, id+".commands", "commands", pl.commands, null, null, "plugin", nameHit);
}
function selectProject(p){
  if(!guardEdit()) return;
  S.project = p;
  renderSide();
  loadEff();
  renderInspector();
  // ponytail: 사이드바 전환은 액티비티 바만 한다 — 프로젝트를 고른다고 트리를 감추지 않는다
}

/* ---------- 2. 규칙 (적용 체인) ---------- */
async function loadEff(){
  var proj = (S.project && S.project.exists !== false) ? S.project.path : null;
  S.eff = null; S.effErr = null; S.conflicts = null; S.conflictSel = null;
  var seq = ++S.eseq;
  if(!proj) return;
  var sseq = S.sseq, body = null, err = null;
  try{
    body = await getJSON("/api/rules?project="+encodeURIComponent(proj));
  }catch(e){ err = e.message; }
  if(S.dead || seq !== S.eseq || sseq !== S.sseq) return;
  if(!S.project || S.project.path !== proj) return;   // 프로젝트가 바뀐 응답은 버린다
  S.eff = body ? (body.files || []) : null;
  S.conflicts = body ? (body.conflicts || []) : null;
  S.effErr = err;
  renderInspector();
  if(S.side === "rules") renderSide();
}
/* 제목으로 프로젝트 간 비교 — Enter 또는 칩이면 compare:<제목> 가상 탭 */
function openCompare(title){
  title = String(title || "").trim();
  if(title) openFile(CMP + title);
}
function rulesCtx(ctx){
  ctxOn(ctx, t("프로젝트"));
  var projs = ((S.scan && S.scan.projects) || []).filter(function(p){ return p.exists !== false; });
  var sel = el("select");
  sel.setAttribute("aria-label", t("규칙을 볼 프로젝트"));
  sel.setAttribute("data-key","rulesproj");
  projs.forEach(function(p){
    var op = el("option", null, p.name || p.path);
    op.value = p.path;
    sel.appendChild(op);
  });
  sel.value = S.project ? S.project.path : "";
  sel.onchange = function(){
    var p = projs.filter(function(x){ return x.path === sel.value; })[0];
    if(p) selectProject(p);
  };
  ctx.appendChild(sel);
  ctx.appendChild(el("span","cr", t(VIEW_CTX.rules)));
}
function renderRulesSide(root, ctx){
  if(!S.project){ sideMsg(root, t("파일 사이드바에서 프로젝트를 선택하세요.")); return; }
  if(S.project.exists === false){ sideMsg(root, t("경로가 존재하지 않는 프로젝트입니다.")); return; }
  rulesCtx(ctx);
  var pname = S.project.name || S.project.path;
  if(S.effErr){
    sideMsg(root, t("유효 규칙을 불러오지 못했습니다: {e}", {e:tMsg(S.effErr)}), "err");
    root.appendChild(el("div","pad")).appendChild(retryBtn(loadEff));
    return;
  }
  if(!S.eff){ sideMsg(root, t("불러오는 중…")); return; }
  if(!S.eff.length){ sideCount(t("{n} 파일", {n:0}));
                     sideMsg(root, t("적용되는 규칙 파일이 없습니다.")); return; }
  sideCount(t("{n} 파일", {n:S.eff.length}));
  var conf = conflictMap();
  var groups = [{id:"rg", title:t("전역"), src:"global", items:[]},
                {id:"rp", title:t("프로젝트 · {n}", {n:pname}), src:"project", items:[]}];
  S.eff.forEach(function(it, i){
    groups[it.scope === "global" ? 0 : 1].items.push({it:it, i:i});
  });
  groups.forEach(function(gr){
    if(!gr.items.length) return;
    if(!groupHd(root, {id:gr.id, title:gr.title, count:gr.items.length, dflt:true})) return;
    gr.items.forEach(function(e){
      var it = e.it, m = S.meta[it.path] || {};
      uiRow(root, {depth:0, src:gr.src, sel: S.filePath === it.path, num:e.i+1, rnum:true,
        name: m.label || baseName(it.path), key: it.path,
        title: it.path + " · " + t(SCOPE_KO[it.scope] || it.scope)
             + " · " + t(it.shared ? "팀 공유" : "개인"),
        warn: it.error ? t("읽기 실패") : (it.lazy ? t("지연") : null),
        tag: (it.error || it.lazy) ? null : t(it.shared ? "팀 공유" : "개인"),
        tagCls: it.shared ? "shared" : null,
        onclick: function(){ openFile(it.path); }});
      (it.sections || []).forEach(function(sec){
        if(!sec || sec.level < 2) return;
        uiRow(root, {depth:1, src:gr.src, dim:true,
          name: "## " + (sec.title || t("(제목 없음)")),
          key: it.path + "#" + sec.start,
          title: it.path + " · L" + (sec.start + 1)
               + (conf[sec.title] ? " · " + t("전역과 프로젝트에 같은 제목 섹션") : ""),
          warn: conf[sec.title] ? t("충돌") : null,
          onclick: function(){ openFile(it.path, {line:sec.start}); }});
      });
    });
  });
}

/* ---------- 3. 스킬·에이전트·커맨드 ---------- */
// 행 오른쪽 ON/OFF 스위치 (스킬·커맨드만)
function skillSwitch(c){
  var cur = skillOverrides()[c.key] || "on", on = cur !== "off";
  return switchEl({on:on, label: t("{n} — 이 프로젝트에서 사용", {n:c.name}),
    title: t("이 프로젝트에서 사용"),
    key:"sw:"+c.kind+":"+c.key, disabled: !toggleReady(),
    onToggle: function(sw){ doToggle("skillOverrides", c.key, on ? "off" : "on", [sw]); }});
}
// 플러그인 그룹 헤더의 ON/OFF — enabledPlugins 는 플러그인 단위
function pluginSwitch(pl){
  var on = !pluginOff(pl);
  return switchEl({on:on, label:t("{n} — 이 프로젝트에서 플러그인 사용",
                                 {n:pl.name || pl.key}),
    title:t("이 프로젝트에서 플러그인 사용"), key:"plsw:"+pl.key, disabled: !toggleReady(),
    onToggle: function(b){ doToggle("enabledPlugins", pl.key, on ? false : true, [b]); }});
}
function renderSkillsSide(root, ctx){
  if(!S.scan) return;
  ctxOn(ctx, t(VIEW_CTX.skills));
  ctx.appendChild(el("span","cv", toggleReady() ? S.toggleTarget : t("프로젝트 미선택")));
  var body = el("div");
  body.id = "cardbody";
  root.appendChild(body);
  renderCardBody();
}
// 툴바는 다시 그리지 않는다 — 행 영역만 갱신해야 입력 포커스가 유지된다
function renderCardBody(){
  var body = document.getElementById("cardbody");
  if(!body) return;
  clear(body);
  var all = collect(), shown = all.filter(cardMatch);
  sideCount(t("표시 {n} / 전체 {a}", {n:shown.length, a:all.length}));
  var pMap = Object.create(null);
  ((S.scan && S.scan.plugins) || []).forEach(function(pl){ pMap[pl.name || pl.key] = pl; });
  var order = [], by = Object.create(null);
  shown.forEach(function(c){
    var s = cardSrc(c);
    if(!by[s.key]){ by[s.key] = {src:s, items:[]}; order.push(by[s.key]); }
    by[s.key].items.push(c);
  });
  order.sort(function(a,b){ return a.src.rank - b.src.rank || a.src.label.localeCompare(b.src.label); });
  if(!order.length){ sideMsg(body, t("조건에 맞는 항목이 없습니다.")); return; }
  var searching = !!S.cardq.q.trim();
  order.forEach(function(sec){
    var id = "cards:" + sec.src.key, dflt = sec.src.rank < 2;
    var pl = sec.src.plugin ? pMap[sec.src.plugin] : null;
    var srcCls = sec.src.rank === 0 ? "global" : (sec.src.rank === 1 ? "project" : "plugin");
    // 검색 중에는 매칭이 있는 섹션을 펼쳐 보여준다 — 저장된 접힘 상태는 그대로
    var open = groupHd(body, {id:id, title:sec.src.label, count:sec.items.length, dflt:dflt,
      force:searching, ctrl: (pl && pl.exists !== false) ? pluginSwitch(pl) : null,
      onToggle: function(){ S.expanded[id] = !isOpen(id, dflt); renderCardBody(); }});
    if(!open) return;
    sec.items.forEach(function(c){
      // 에이전트는 skillOverrides 대상이 아니고, 플러그인 내부 항목은 플러그인 단위로만 켜고 끈다
      var sw = (c.kind !== "agent" && !c.pluginOwned && toggleReady()) ? skillSwitch(c) : null;
      uiRow(body, {depth:0, src:srcCls, sel: S.filePath === c.path, dim: !!c.off,
        name: c.name, key: c.path,
        title: c.path + (c.off ? " · " + t(c.offLabel || "OFF") : ""),
        tag: t(KIND_KO[c.kind] || c.kind), tagCls: "k-"+c.kind, sw: sw,
        onclick: function(){ openFile(c.path); }});
    });
  });
}

/* ---------- 4. 훅 흐름 ---------- */
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
function hookMatch(h){
  var cls = hookSource(h.source).cls;
  if(cls && !S.hookq.src[cls]) return false;
  var q = S.hookq.q.trim().toLowerCase();
  if(!q) return true;
  return String(h.event||"").toLowerCase().indexOf(q) >= 0
      || String(h.matcher||"").toLowerCase().indexOf(q) >= 0
      || hookCmds(h).join(" ").toLowerCase().indexOf(q) >= 0;
}
function renderHooksSide(root, ctx){
  var hooks = ((S.scan && S.scan.hooks) || []).filter(hookMatch);
  sideCount(hooks.length + "");
  ctxOn(ctx, t(VIEW_CTX.hooks));
  if(!hooks.length){ sideMsg(root, t("표시할 훅이 없습니다.")); return; }
  var g = groupHooks(hooks), sel = S.selHook ? hookKey(S.selHook) : null;
  g.order.forEach(function(ev){
    if(!groupHd(root, {id:"hook:"+ev, title:t(ev), count:g.byEvent[ev].length, dflt:true})) return;
    g.byEvent[ev].forEach(function(h){
      var src = hookSource(h.source), cmds = hookCmds(h);
      var first = cmds.length ? baseName(String(cmds[0]).split(/\s+/)[0]) : "";
      uiRow(root, {depth:0, src: src.cls || null, sel: sel === hookKey(h),
        name: h.matcher || t("(전체)"), key: "hook:"+hookKey(h),
        sub: first + (cmds.length > 1 ? "…" : ""),
        title: src.label + " → " + (cmds.join(" · ") || t("(명령 없음)")),
        warn: h.warn === "duplicate-star" ? t("중복") : null,
        count: cmds.length,
        onclick: function(){ selectHook(h); }});
    });
  });
}

/* ---------- 5. MCP ---------- */
// 출처 그룹: {key, label, src, off, file, items:[{name, config}]}
function mcpGroups(){
  var order = [], by = Object.create(null);
  function grp(key, label, src, file, off){
    if(!by[key]){
      by[key] = {key:key, label:label, src:src, file:file || null, off:!!off, items:[]};
      order.push(by[key]);
    }
    return by[key];
  }
  ((S.scan && S.scan.mcp) || []).forEach(function(m){
    var s = m.source || "(출처 없음)";
    var label = s === "global" ? t("전역")
      : s.indexOf("project:") === 0 ? t("프로젝트 · {n}", {n:s.slice(8)})
      : s.indexOf("plugin:") === 0 ? t("플러그인 · {n}", {n:s.slice(7)}) : t(s);
    var src = s === "global" ? "global"
      : s.indexOf("project:") === 0 ? "project"
      : s.indexOf("plugin:") === 0 ? "plugin" : null;
    grp("src:"+s, label, src).items.push(m);
  });
  ((S.scan && S.scan.plugins) || []).forEach(function(pl){
    if(pl.exists === false) return;
    var srv = pl.mcp_servers || {};
    keys(srv).forEach(function(n){
      grp("plugin:"+pl.key, t("플러그인 · {n}", {n:pl.name || pl.key}), "plugin", null, pluginOff(pl))
        .items.push({name:n, config:srv[n]});
    });
  });
  // 프로젝트 루트 .mcp.json — 선택 프로젝트가 있으면 그 프로젝트만
  var projs = (S.project && S.project.exists !== false) ? [S.project] : ((S.scan && S.scan.projects) || []);
  projs.forEach(function(pr){
    var mj = pr.mcp_json;
    if(!mj || !mj.data || typeof mj.data !== "object") return;
    var srv = mj.data.mcpServers || {};
    keys(srv).forEach(function(n){
      grp("pmcp:"+(mj.path || pr.path || ""), t("프로젝트 .mcp.json · {n}", {n:pr.name || pr.path}),
          "project", mj.path).items.push({name:n, config:srv[n]});
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
function mcpMatch(it){
  var cfg = (it.config && typeof it.config === "object") ? it.config : {};
  var tr = S.mcpq.tr;
  if(tr.command || tr.url){
    if(!((tr.command && cfg.command) || (tr.url && cfg.url))) return false;
  }
  var q = S.mcpq.q.trim().toLowerCase();
  if(!q) return true;
  return String(it.name||"").toLowerCase().indexOf(q) >= 0;
}
function renderMcpSide(root, ctx){
  ctxOn(ctx, t((S.project && S.project.exists !== false) ? VIEW_CTX.mcpOne : VIEW_CTX.mcpAll));
  var groups = mcpGroups().map(function(g){
    var q = {}; keys(g).forEach(function(k){ q[k] = g[k]; });
    q.items = g.items.filter(mcpMatch);
    return q;
  }).filter(function(g){ return g.items.length; });
  var n = 0;
  groups.forEach(function(g){ n += g.items.length; });
  sideCount(n + "");
  if(!groups.length){ sideMsg(root, t("표시할 MCP 서버가 없습니다.")); return; }
  groups.forEach(function(g){
    if(!groupHd(root, {id:"mcp:"+g.key, title:g.label, count:g.items.length, dflt:true})) return;
    g.items.forEach(function(it){
      var cfg = (it.config && typeof it.config === "object") ? it.config : {};
      var sel = {name:it.name, config:it.config, label:g.label, file:g.file};
      uiRow(root, {depth:0, src:g.src, dim:g.off,
        sel: !!(S.selMcp && S.selMcp.name === it.name && S.selMcp.label === g.label),
        name: it.name || t("(이름 없음)"), key: "mcp:"+g.key+":"+it.name,
        sub: cfg.command ? "command" : (cfg.url ? "url" : t("설정 없음")),
        title: g.label + " · " + (cfg.command || cfg.url || "-")
             + (g.off ? " · " + t("플러그인 OFF") : ""),
        tag: g.off ? "OFF" : null, tagCls: g.off ? "off" : null,
        onclick: function(){ selectMcp(sel); }});
    });
  });
}
