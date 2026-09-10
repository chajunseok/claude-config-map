// inspector — 오른쪽 인스펙터 렌더와 토글 컨트롤(스킬 레벨·저장 대상·토글 반영)
"use strict";
// 인스펙터 토글 섹션의 경고·오류 줄 — 토글 컨트롤과 따로 갱신한다
function toggleNotes(){
  var box = el("div");
  box.id = "togglenotes";
  renderToggleNotes(box);
  return box;
}
function renderToggleNotes(box){
  box = box || document.getElementById("togglenotes");
  if(!box) return;
  clear(box);
  if(S.toggleTarget === "settings.json")
    box.appendChild(el("div","sharewarn","git 추적 파일 — 커밋하면 팀 전체에 적용됨"));
  var c = cmpVer(S.scan && S.scan.claude_version);
  if(c === null) box.appendChild(el("div","sharewarn","Claude Code 버전 미확인 — 스킬 토글 지원 여부 확인 불가"));
  else if(c < 0) box.appendChild(el("div","sharewarn","Claude Code 스킬 토글 미지원 버전 — 토글해도 적용되지 않을 수 있음"));
  if(S.toggleErr) box.appendChild(el("div","togglemsg", S.toggleErr));
}
// 인스펙터의 저장 대상 select
function targetSelect(){
  var wrap = el("div","ctl");
  var tgt = el("select","tgt");
  [["settings.local.json","settings.local.json (개인, 기본)"],
   ["settings.json","settings.json (팀 공유)"]].forEach(function(o){
    var op = el("option", null, o[1]);
    op.value = o[0];
    tgt.appendChild(op);
  });
  tgt.value = S.toggleTarget;
  tgt.disabled = !toggleReady();
  tgt.setAttribute("aria-label","토글 저장 대상 파일");
  tgt.onchange = function(){ S.toggleTarget = tgt.value; renderToggleNotes(); };
  wrap.appendChild(el("span","hint","저장 대상"));
  wrap.appendChild(tgt);
  return wrap;
}
// 컨트롤 변경 → POST /api/toggle → 200이면 제자리 반영, 실패면 오류 줄 + 컨트롤 원복
async function doToggle(section, key, value, ctrls){
  if(!toggleReady()) return;
  S.toggleErr = null;
  ctrls.forEach(function(c){ c.disabled = true; });
  renderToggleNotes();
  var sseq = S.sseq, res = null, err = null;
  try{
    res = await postJSON("/api/toggle", {project:S.project.path, section:section, key:key,
                                         value:value, target:S.toggleTarget});
  }catch(ex){ err = ex.message; }
  if(S.dead || sseq !== S.sseq) return;
  if(!err && res.status === 200){ applyToggle(res.body, section, key); return; }
  S.toggleErr = "토글하지 못했습니다: "
    + (err || ("HTTP " + res.status + " — " + ((res.body && res.body.error) || "요청 실패")));
  renderSide();          // 컨트롤 원복 = 현재 스캔 값 기준 재렌더
  renderInspector();
}
// 토글 성공 → 재스캔 없이 스캔 상태를 제자리에서 갱신하고 사이드바·인스펙터만 다시 그린다.
// ponytail: 서버 응답(path/value/created)이 곧 디스크 상태. 전체 재스캔은 사용자가 재스캔 버튼을 누를 때만.
function applyToggle(body, section, key){
  var p = S.project, sets = p.settings || (p.settings = {});
  var name = S.toggleTarget, entry = sets[name];
  if(!entry || !entry.data || typeof entry.data !== "object"){
    entry = sets[name] = {path: body.path, data: {}, mtime: null, size: null, shared: false};
  }
  var sec = entry.data[section];
  if(!sec || typeof sec !== "object") sec = entry.data[section] = {};
  if(body.value === null || body.value === undefined){
    delete sec[key];
    if(!keys(sec).length) delete entry.data[section];
  }else sec[key] = body.value;
  if(body.created) S.meta = scanIndex(S.scan);
  renderSide();
  renderInspector();
}

// 인스펙터 토글 줄 — 스위치 + 4단계 select
function skillCtrls(c){
  var row = el("div","ctl"), cur = skillOverrides()[c.key] || "on", on = cur !== "off";
  var sw = el("button","switch", on ? "ON" : "OFF");
  sw.setAttribute("role","switch");
  sw.setAttribute("aria-checked", String(on));
  sw.setAttribute("aria-label", c.name + " — 이 프로젝트에서 사용 (인스펙터)");
  sw.title = "이 프로젝트에서 사용";
  var sel = el("select","lvl");
  LEVELS.forEach(function(o){
    var op = el("option", null, o[1]);
    op.value = o[0];
    sel.appendChild(op);
  });
  sel.value = cur;
  sel.setAttribute("aria-label", c.name + " 사용 범위");
  var ctrls = [sw, sel], dis = !toggleReady();
  sw.disabled = dis; sel.disabled = dis;
  sw.onclick = function(){ doToggle("skillOverrides", c.key, on ? "off" : "on", ctrls); };
  sel.onchange = function(){ doToggle("skillOverrides", c.key, sel.value, ctrls); };
  row.appendChild(sw);
  row.appendChild(sel);
  return row;
}

/* 충돌 두 섹션을 세로로 나란히 — 본문은 /api/file 응답 캐시에서 잘라 쓴다 */
function conflictBodies(c){
  var box = el("div","cfbodies");
  (c.where || []).forEach(function(w){
    var card = el("div","cfcard");
    var h = el("button","cfhd");
    h.appendChild(badge(SCOPE_KO[w.scope] || w.scope));
    h.appendChild(el("span","p", w.path + " · L" + (w.start+1) + "–L" + w.end));
    h.title = w.path + " — 이 줄로 이동";
    h.onclick = function(){ openFile(w.path, {line:w.start}); };
    card.appendChild(h);
    var f = S.fileCache[w.path];
    if(!f){
      card.appendChild(el("div","hint","불러오는 중…"));
      ensureCache(w.path);
    }else if(f.error){
      card.appendChild(el("div","err", "읽지 못했습니다: " + f.error));
    }else{
      card.appendChild(el("pre","cfbody",
        String(f.text || "").split("\n").slice(w.start, w.end).join("\n")));
    }
    box.appendChild(card);
  });
  return box;
}
// ponytail: 캐시 무효화는 재스캔뿐 — 파일을 열거나 저장하면 그 경로만 갱신된다
async function ensureCache(path){
  if(S.fileCache[path] || S.cacheBusy[path]) return;
  S.cacheBusy[path] = true;
  var sseq = S.sseq, f = null;
  try{ f = await getJSON("/api/file?path="+encodeURIComponent(path)); }
  catch(e){ f = {text:"", error:e.message}; }
  delete S.cacheBusy[path];
  if(S.dead || sseq !== S.sseq) return;
  S.fileCache[path] = f;
  renderInspector();
}

/* ---------- 인스펙터 ---------- */
function section(parent, title){
  var s = el("section");
  s.appendChild(el("div","sec-t", title));
  parent.appendChild(s);
  return s;
}
function kvRow(grid, k, v, cls){
  grid.appendChild(el("span","k", k));
  grid.appendChild(el("span","v"+(cls?" "+cls:""), v));
}
function renderInspector(){
  var ins = clear(document.getElementById("inspector"));
  /* 스캔 */
  var sc = section(ins, "스캔");
  var g1 = el("div","kvgrid");
  if(S.scan){
    kvRow(g1, "시각", new Date(S.scan.scanned_at).toLocaleString("ko-KR"));
    var v = S.scan.claude_version, c = cmpVer(v);
    kvRow(g1, "Claude Code", c === null ? "미확인" : v, c === null ? "warn" : null);
    if(c === null) kvRow(g1, "경고", "버전 미확인 — 스킬 토글 지원 여부 확인 불가", "warn");
    else if(c < 0) kvRow(g1, "경고", "스킬 토글 미지원 버전", "warn");
  }else{
    kvRow(g1, "시각", S.loading ? "스캔 중…" : "-");
  }
  sc.appendChild(g1);
  if(S.msg) sc.appendChild(el("div", S.msgOk ? "hint" : "err", S.msg));
  if(S.scanErr) sc.appendChild(retryBtn(loadScan));
  var errs = (S.scan && S.scan.errors) || [];
  if(errs.length){
    var eb = el("button","linkbtn","오류 "+errs.length+"건");
    eb.setAttribute("aria-expanded", String(S.errOpen));
    eb.onclick = function(){ S.errOpen = !S.errOpen; renderInspector(); };
    sc.appendChild(eb);
    if(S.errOpen){
      var list = el("div"); list.id = "errlist";
      errs.forEach(function(e){ list.appendChild(el("div", null, (e.path||"")+" — "+(e.error||""))); });
      sc.appendChild(list);
    }
  }
  /* 속성 */
  var ps = section(ins, "속성");
  var g2 = el("div","kvgrid"), any = false;
  if(S.filePath){
    any = true;
    var m = S.meta[S.filePath] || {};
    kvRow(g2, "범위", m.scope || "-");
    kvRow(g2, "출처", m.origin || "-");
    kvRow(g2, "공유", m.shared ? "팀 공유 (git 추적)" : "개인", m.shared ? "shared" : null);
    if(m.lazy) kvRow(g2, "적재", "지연 로드 (해당 폴더 작업 시)", "warn");
    if(S.file && isCompare(S.filePath)){
      kvRow(g2, "비교 제목", cmpTitle(S.filePath));
      kvRow(g2, "매치", len(S.file.matches) + "곳");
    }else if(S.file){
      kvRow(g2, "크기", kb(S.file.size));
      kvRow(g2, "수정", ymd(S.file.mtime));
      kvRow(g2, "줄바꿈", (S.file.crlf ? "CRLF" : "LF") + " · BOM " + (S.file.bom ? "있음" : "없음"));
      if(S.file.sections) kvRow(g2, "섹션", S.file.sections.length + "개");
    }else if(S.fileErr){
      kvRow(g2, "본문", "불러오지 못함", "warn");
    }else{
      kvRow(g2, "본문", "불러오는 중…");
    }
  }
  if(!S.filePath && S.fileErr){
    any = true;
    kvRow(g2, "파일", S.fileErr, "warn");
  }
  if(S.project){
    any = true;
    if(S.filePath || S.fileErr) g2.appendChild(el("span","k"," ")), g2.appendChild(el("span","v"," "));
    var p = S.project;
    kvRow(g2, "프로젝트", p.name || p.path);
    kvRow(g2, "경로", p.path);
    if(p.exists === false) kvRow(g2, "상태", "경로 없음", "warn");
    else{
      kvRow(g2, "스캔 범위", p.coverage === "root-only"
        ? "루트만 · " + (COVER_KO[p.coverage_reason] || p.coverage_reason || "사유 미상")
        : "전체", p.coverage === "root-only" ? "warn" : null);
      if(p.truncated || p.incomplete) kvRow(g2, "완결성", "일부만 스캔", "warn");
      kvRow(g2, "git", p.git ? "예" : "아니오");
      var tc = projToggleCount(p);
      kvRow(g2, "이 프로젝트 토글", "스킬 " + tc.skills + " · 플러그인 " + tc.plugins);
    }
  }
  if(!any) ps.appendChild(el("div","hint","파일이나 프로젝트를 선택하면 속성이 표시됩니다."));
  else ps.appendChild(g2);
  /* 항목 — 열린 파일이 스킬/에이전트/커맨드일 때 */
  var item = S.filePath ? collect().filter(function(c){ return c.path === S.filePath; })[0] : null;
  if(item){
    var its = section(ins, "항목");
    var g3 = el("div","kvgrid");
    kvRow(g3, "이름", item.name);
    kvRow(g3, "종류", KIND_KO[item.kind] || item.kind);
    kvRow(g3, "출처", item.origin);
    if(item.off) kvRow(g3, "상태", item.offLabel || "OFF", "warn");
    its.appendChild(g3);
    its.appendChild(el("div","desc"+(item.desc ? "" : " none"), item.desc || "설명 없음"));
  }
  /* 토글 — 저장 대상·경고는 항목 선택과 무관하게 항상 여기 */
  var ts = section(ins, "토글");
  if(item && item.kind === "agent")
    ts.appendChild(el("div","hint","에이전트는 토글 대상이 아닙니다."));
  else if(item && item.pluginOwned){
    ts.appendChild(el("div","hint","플러그인 단위 스위치는 스킬 사이드바의 섹션 헤더에서 켜고 끕니다."));
    var opl = ((S.scan && S.scan.plugins) || []).filter(function(x){
      return ("플러그인:" + (x.name || x.key)) === item.origin; })[0];
    if(opl && opl.exists !== false) ts.appendChild(pluginSwitch(opl));
  }
  else if(!toggleReady())
    ts.appendChild(el("div","hint", S.project ? "선택 프로젝트 경로 없음 — 토글 불가"
                                              : "토글하려면 파일 사이드바에서 프로젝트를 선택하세요"));
  else if(item){
    ts.appendChild(skillCtrls(item));
    var isrc = settingSource("skillOverrides", item.key);
    var sb = el("div","ctl");
    sb.appendChild(el("span","hint","값 출처"));
    sb.appendChild(badge(isrc ? isrc.label : "기본값"));
    ts.appendChild(sb);
  }
  else ts.appendChild(el("div","hint","스킬·커맨드 파일을 열면 여기서 켜고 끕니다."));
  ts.appendChild(targetSelect());
  ts.appendChild(toggleNotes());
  /* 선택한 훅 */
  if(S.selHook){
    var hsel = section(ins, "선택한 훅");
    var g4 = el("div","kvgrid");
    kvRow(g4, "이벤트", S.selHook.event || "-");
    kvRow(g4, "매처", S.selHook.matcher || "(없음)");
    kvRow(g4, "출처", hookSource(S.selHook.source).label);
    if(S.selHook.warn === "duplicate-star") kvRow(g4, "경고", "* 매처와 중복 발화", "warn");
    hsel.appendChild(g4);
    var cl = el("div","hooklist"), cmds = hookCmds(S.selHook);
    if(!cmds.length) cl.appendChild(el("div","hint","명령 없음"));
    cmds.forEach(function(c){ cl.appendChild(el("div","cmd", "→ " + c)); });
    hsel.appendChild(cl);
    if(!hookFile(S.selHook.source)) hsel.appendChild(el("div","hint","출처 파일은 열 수 없습니다 (플러그인)"));
  }
  /* 선택한 MCP */
  if(S.selMcp){
    var ms = section(ins, "선택한 MCP");
    var g5 = el("div","kvgrid");
    kvRow(g5, "이름", S.selMcp.name || "-");
    kvRow(g5, "출처", S.selMcp.label || "-");
    ms.appendChild(g5);
    ms.appendChild(el("pre","cfg", JSON.stringify(S.selMcp.config == null ? null : S.selMcp.config, null, 2)));
  }
  /* 함께 적용됨 */
  var es = section(ins, "함께 적용됨");
  if(!S.project) es.appendChild(el("div","hint","프로젝트를 선택하세요."));
  else if(S.project.exists === false) es.appendChild(el("div","hint","경로가 존재하지 않는 프로젝트입니다."));
  else if(S.effErr){
    es.appendChild(el("div","err","불러오지 못했습니다: "+S.effErr));
    es.appendChild(retryBtn(loadEff));
  }
  else if(!S.eff) es.appendChild(el("div","hint","불러오는 중…"));
  else if(!S.eff.length) es.appendChild(el("div","hint","적용되는 규칙 파일이 없습니다."));
  else{
    var list2 = el("div","efflist");
    S.eff.forEach(function(it, i){
      var cur = it.path === S.filePath, im = S.meta[it.path] || {};
      var row = el("div","effitem"+(cur ? " cur" : "")+(it.lazy ? " lazyit" : ""));
      row.title = it.path;
      row.appendChild(el("span","n", String(i+1)));
      row.appendChild(el("span", null, (im.label || it.path) + (cur ? "  ← 현재" : "") + (it.lazy ? " · 지연" : "")));
      list2.appendChild(row);
    });
    es.appendChild(list2);
  }
  /* 충돌 — 같은 제목 섹션이 여러 파일에 (V5 warn) */
  var cs = section(ins, "충돌");
  var cflist = S.conflicts || [];
  if(!S.project || S.project.exists === false) cs.appendChild(el("div","hint","프로젝트를 선택하세요."));
  else if(!S.conflicts) cs.appendChild(el("div","hint", S.effErr ? "불러오지 못했습니다." : "불러오는 중…"));
  else if(!cflist.length) cs.appendChild(el("div","hint","같은 제목의 섹션이 겹치지 않습니다."));
  else{
    var cl2 = el("div","cflist");
    cflist.forEach(function(c){
      var open = S.conflictSel === c.title;
      var b = el("button","cfitem");
      b.setAttribute("aria-expanded", String(open));
      b.appendChild(el("span","arw", open ? "▾" : "▸"));
      b.appendChild(el("span","t", c.title));
      b.appendChild(badge(len(c.where) + "곳","warn"));
      b.onclick = function(){ S.conflictSel = open ? null : c.title; renderInspector(); };
      cl2.appendChild(b);
      if(open) cl2.appendChild(conflictBodies(c));
    });
    cs.appendChild(cl2);
  }
  /* 이 프로젝트의 훅 */
  var hs = section(ins, "이 프로젝트의 훅");
  if(!S.project || S.project.exists === false) hs.appendChild(el("div","hint","프로젝트를 선택하세요."));
  else{
    var pref = "project:" + S.project.path + ":";
    var mine = ((S.scan && S.scan.hooks) || []).filter(function(h){ return String(h.source||"").indexOf(pref) === 0; });
    if(!mine.length) hs.appendChild(el("div","hint","이 프로젝트에서 등록한 훅이 없습니다."));
    else{
      var hl = el("div","hooklist");
      mine.forEach(function(h){
        var line = (h.event||"?") + " · " + (h.matcher || "(없음)") + " → " + (hookCmds(h).join(", ") || "(명령 없음)");
        var d = el("div","hookitem", line);
        if(h.warn === "duplicate-star"){
          d.appendChild(el("span","warn", " · * 매처와 중복 발화"));
        }
        hl.appendChild(d);
      });
      hs.appendChild(hl);
    }
  }
  ins.appendChild(el("div","spacer"));
  var acts = el("div","acts");
  var re = el("button", null, S.loading ? "스캔 중…" : "재스캔");
  re.disabled = S.loading; re.onclick = loadScan; acts.appendChild(re);
  var sd = el("button", null, "종료"); sd.onclick = shutdown; acts.appendChild(sd);
  ins.appendChild(acts);
}
