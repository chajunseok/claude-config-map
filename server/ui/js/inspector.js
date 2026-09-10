// inspector — 선택한 것에 관한 섹션만. 스캔 정보·재스캔·종료는 하단 상태바로 갔다
"use strict";
// 토글 섹션의 경고·오류 줄 — 토글 컨트롤과 따로 갱신한다
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
    box.appendChild(el("div","sharewarn", t("git 추적 파일 — 커밋하면 팀 전체에 적용됨")));
  var c = cmpVer(S.scan && S.scan.claude_version);
  if(c === null) box.appendChild(el("div","sharewarn", t("Claude Code 버전 미확인 — 스킬 토글 지원 여부 확인 불가")));
  else if(c < 0) box.appendChild(el("div","sharewarn", t("Claude Code 스킬 토글 미지원 버전 — 토글해도 적용되지 않을 수 있음")));
  if(S.toggleErr) box.appendChild(el("div","togglemsg", S.toggleErr));
}
// 저장 대상 select
function targetSelect(){
  var wrap = el("div","ctl");
  var tgt = el("select","tgt");
  [["settings.local.json","settings.local.json (개인, 기본)"],
   ["settings.json","settings.json (팀 공유)"]].forEach(function(o){
    var op = el("option", null, t(o[1]));
    op.value = o[0];
    tgt.appendChild(op);
  });
  tgt.value = S.toggleTarget;
  tgt.disabled = !toggleReady();
  tgt.setAttribute("aria-label", t("토글 저장 대상 파일"));
  tgt.onchange = function(){ S.toggleTarget = tgt.value; renderToggleNotes(); renderSide(); };
  wrap.appendChild(el("span","hint", t("저장 대상")));
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
  S.toggleErr = t("토글하지 못했습니다: {e}", {e: err ? tMsg(err)
    : ("HTTP " + res.status + " — "
       + ((res.body && res.body.error) ? tMsg(res.body.error) : t("요청 실패")))});
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
// 인스펙터 토글 줄 — 스위치 + "이 프로젝트에서 사용" 라벨 + 4단계 select
function skillCtrls(c){
  var row = el("div","ctl"), cur = skillOverrides()[c.key] || "on", on = cur !== "off";
  var sel = el("select","lvl");
  LEVELS.forEach(function(o){
    var op = el("option", null, t(o[1]));
    op.value = o[0];
    sel.appendChild(op);
  });
  sel.value = cur;
  sel.setAttribute("aria-label", t("{n} 사용 범위", {n:c.name}));
  var sw = switchEl({on:on, label: t("{n} — 이 프로젝트에서 사용 (인스펙터)", {n:c.name}),
    title: t("이 프로젝트에서 사용"), disabled: !toggleReady(),
    onToggle: function(){ doToggle("skillOverrides", c.key, on ? "off" : "on", [sw, sel]); }});
  sel.disabled = !toggleReady();
  sel.onchange = function(){ doToggle("skillOverrides", c.key, sel.value, [sw, sel]); };
  row.appendChild(sw);
  row.appendChild(el("span", null, t("이 프로젝트에서 사용")));
  row.appendChild(sel);
  return row;
}

/* 충돌 두 섹션을 세로로 나란히 — 본문은 /api/file 응답 캐시에서 잘라 쓴다 */
function conflictBodies(c){
  var box = el("div","cfbodies");
  (c.where || []).forEach(function(w){
    var card = el("div","cfcard");
    var h = el("button","cfhd");
    h.appendChild(badge(t(SCOPE_KO[w.scope] || w.scope)));
    h.appendChild(el("span","p", w.path + " · L" + (w.start+1) + "–L" + w.end));
    h.title = t("{p} — 이 줄로 이동", {p:w.path});
    h.onclick = function(){ openFile(w.path, {line:w.start}); };
    card.appendChild(h);
    var f = S.fileCache[w.path];
    if(!f){
      card.appendChild(el("div","hint", t("불러오는 중…")));
      ensureCache(w.path);
    }else if(f.error){
      card.appendChild(el("div","err", t("읽지 못했습니다: {e}", {e:tMsg(f.error)})));
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
function section(parent, title, count){
  var s = el("section");
  var hd = el("div","sec-t");
  hd.appendChild(el("span", null, title));
  if(count != null) hd.appendChild(el("span","n", String(count)));
  s.appendChild(hd);
  parent.appendChild(s);
  return s;
}
function kvRow(grid, k, v, cls){
  grid.appendChild(el("span","k", k));
  grid.appendChild(el("span","v"+(cls?" "+cls:""), v));
}
function openItem(){
  return S.filePath ? collect().filter(function(c){ return c.path === S.filePath; })[0] : null;
}
// 헤더 제목 = 선택 대상 이름
function insTitle(){
  if(S.selHook) return (S.selHook.event || t("훅")) + " · " + (S.selHook.matcher || t("(전체)"));
  if(S.selMcp) return S.selMcp.name || "MCP";
  var item = openItem();
  if(item) return item.name;
  if(S.filePath){
    if(isCompare(S.filePath)) return t("비교: {t}", {t:cmpTitle(S.filePath)});
    var m = S.meta[S.filePath] || {};
    return m.label || baseName(S.filePath);
  }
  if(S.project) return S.project.name || S.project.path;
  return t("인스펙터");
}
/* 스캔 오류 — 상태바의 "오류 N건" 을 눌렀을 때만 */
function errSection(ins){
  var errs = (S.scan && S.scan.errors) || [];
  if(!S.errOpen || !errs.length) return;
  var s = section(ins, t("스캔 오류"), errs.length);
  var list = el("div");
  list.id = "errlist";
  errs.forEach(function(e){ list.appendChild(el("div", null, (e.path||"")+" — "+tMsg(e.error||""))); });
  s.appendChild(list);
}
/* 파일 속성 */
function fileProps(ins){
  var s = section(ins, t("속성"));
  var g = el("div","kvgrid"), m = S.meta[S.filePath] || {};
  kvRow(g, t("범위"), m.scope ? t(m.scope) : "-");
  kvRow(g, t("출처"), m.origin ? originLabel(m.origin) : "-");
  kvRow(g, t("공유"), m.shared ? t("팀 공유 (git 추적)") : t("개인"), m.shared ? "shared" : null);
  if(m.lazy) kvRow(g, t("적재"), t("지연 로드 (해당 폴더 작업 시)"), "warn");
  if(S.file && isCompare(S.filePath)){
    kvRow(g, t("비교 제목"), cmpTitle(S.filePath));
    kvRow(g, t("매치"), t("{n}곳", {n:len(S.file.matches)}));
  }else if(S.file){
    kvRow(g, t("크기"), kb(S.file.size));
    kvRow(g, t("수정"), ymd(S.file.mtime));
    kvRow(g, t("줄바꿈"), (S.file.crlf ? "CRLF" : "LF") + " · BOM " + (S.file.bom ? t("있음") : t("없음")));
    if(S.file.sections) kvRow(g, t("섹션"), t("{n}개", {n:S.file.sections.length}));
  }else if(S.fileErr){
    kvRow(g, t("본문"), t("불러오지 못함"), "warn");
  }else{
    kvRow(g, t("본문"), t("불러오는 중…"));
  }
  s.appendChild(g);
}
/* 항목(스킬·에이전트·커맨드) */
function itemSections(ins, item){
  var s = section(ins, t("항목"));
  var g = el("div","kvgrid");
  kvRow(g, t("종류"), t(KIND_KO[item.kind] || item.kind));
  kvRow(g, t("출처"), cardSrc(item).label);
  if(item.off) kvRow(g, t("상태"), item.offLabel ? t(item.offLabel) : "OFF", "warn");
  var isrc = settingSource("skillOverrides", item.key);
  kvRow(g, t("값 출처"), isrc ? t(isrc.label) : t("기본값"));
  s.appendChild(g);
  s.appendChild(el("div","desc"+(item.desc ? "" : " none"), item.desc || t("설명 없음")));

  var ts = section(ins, t("이 프로젝트에서"));
  if(item.kind === "agent")
    ts.appendChild(el("div","hint", t("에이전트는 토글 대상이 아닙니다.")));
  else if(item.pluginOwned){
    ts.appendChild(el("div","hint", t("플러그인 단위 스위치는 스킬 사이드바의 그룹 헤더에서 켜고 끕니다.")));
    var opl = ((S.scan && S.scan.plugins) || []).filter(function(x){
      return ("플러그인:" + (x.name || x.key)) === item.origin; })[0];
    if(opl && opl.exists !== false){
      var row = el("div","ctl");
      row.appendChild(pluginSwitch(opl));
      row.appendChild(el("span", null, t("이 프로젝트에서 플러그인 사용")));
      var psrc = settingSource("enabledPlugins", opl.key);
      if(psrc) row.appendChild(badge(t(psrc.label)));
      ts.appendChild(row);
    }
  }
  else if(!toggleReady())
    ts.appendChild(el("div","hint", S.project ? t("선택 프로젝트 경로 없음 — 토글 불가")
                                              : t("토글하려면 파일 사이드바에서 프로젝트를 선택하세요")));
  else ts.appendChild(skillCtrls(item));
  ts.appendChild(targetSelect());
  ts.appendChild(toggleNotes());

  var ps = section(ins, t("속성"));
  var g2 = el("div","kvgrid"), m = S.meta[S.filePath] || {};
  kvRow(g2, t("공유"), m.shared ? t("팀 공유 (git 추적)") : t("개인"), m.shared ? "shared" : null);
  if(S.file){
    kvRow(g2, t("크기"), kb(S.file.size));
    kvRow(g2, t("수정"), ymd(S.file.mtime));
  }else kvRow(g2, t("본문"), S.fileErr ? t("불러오지 못함") : t("불러오는 중…"), S.fileErr ? "warn" : null);
  ps.appendChild(g2);
}
/* 훅 */
function hookSections(ins){
  var h = S.selHook, cmds = hookCmds(h);
  var s = section(ins, t("훅"));
  var g = el("div","kvgrid");
  kvRow(g, t("이벤트"), h.event || "-");
  kvRow(g, t("매처"), h.matcher || t("(전체)"));
  kvRow(g, t("출처"), hookSource(h.source).label);
  kvRow(g, t("명령"), t("{n}개", {n:cmds.length}));
  if(h.warn === "duplicate-star") kvRow(g, t("경고"), t("* 매처와 중복 발화"), "warn");
  s.appendChild(g);
  if(!hookFile(h.source)) s.appendChild(el("div","hint", t("출처 파일은 열 수 없습니다 (플러그인)")));

  var cs = section(ins, t("명령"), cmds.length);
  if(!cmds.length) cs.appendChild(el("div","hint", t("명령 없음")));
  cmds.forEach(function(c){ cs.appendChild(el("pre","cfg", String(c))); });

  var others = ((S.scan && S.scan.hooks) || []).filter(function(x){
    return x.event === h.event && hookKey(x) !== hookKey(h); });
  var os = section(ins, t("같은 이벤트의 다른 훅"), others.length);
  if(!others.length){ os.appendChild(el("div","hint", t("없습니다."))); return; }
  var list = el("div","hooklist");
  others.forEach(function(x){
    var d = el("div","hookitem", (x.matcher || t("(전체)")) + " → " + (hookCmds(x).join(", ") || t("(명령 없음)")));
    var src = hookSource(x.source);
    d.appendChild(el("span","hsrc "+(src.cls || ""), " · " + src.label));
    list.appendChild(d);
  });
  os.appendChild(list);
}
/* MCP */
function mcpSections(ins){
  var m = S.selMcp, cfg = (m.config && typeof m.config === "object") ? m.config : {};
  var s = section(ins, t("서버"));
  var g = el("div","kvgrid");
  kvRow(g, t("출처"), m.label || "-");
  kvRow(g, t("전송"), cfg.command ? "command" : (cfg.url ? "url" : t("설정 없음")));
  kvRow(g, t("환경변수"), t("{n}개", {n:keys(cfg.env).length}));
  s.appendChild(g);
  var cs = section(ins, t("설정"));
  cs.appendChild(el("pre","cfg", JSON.stringify(m.config == null ? null : m.config, null, 2)));
}
/* 프로젝트 */
function projSection(ins){
  var p = S.project;
  var s = section(ins, t("프로젝트"));
  var g = el("div","kvgrid");
  kvRow(g, t("이름"), p.name || p.path);
  kvRow(g, t("경로"), p.path);
  if(p.exists === false) kvRow(g, t("상태"), t("경로 없음"), "warn");
  else{
    kvRow(g, t("스캔 범위"), p.coverage === "root-only"
      ? t("루트만 · {n}", {n: p.coverage_reason
            ? t(COVER_KO[p.coverage_reason] || p.coverage_reason) : t("사유 미상")})
      : t("전체"), p.coverage === "root-only" ? "warn" : null);
    if(p.truncated || p.incomplete) kvRow(g, t("완결성"), t("일부만 스캔"), "warn");
    kvRow(g, "git", p.git ? t("예") : t("아니오"));
    var tc = projToggleCount(p);
    kvRow(g, t("이 프로젝트 토글"), t("스킬 {s} · 플러그인 {p}", {s:tc.skills, p:tc.plugins}));
  }
  s.appendChild(g);
}
/* 함께 적용됨 */
function effSection(ins){
  var es = section(ins, t("함께 적용됨"), S.eff ? S.eff.length : null);
  if(!S.project) return es.appendChild(el("div","hint", t("프로젝트를 선택하세요.")));
  if(S.project.exists === false) return es.appendChild(el("div","hint", t("경로가 존재하지 않는 프로젝트입니다.")));
  if(S.effErr){
    es.appendChild(el("div","err", t("불러오지 못했습니다: {e}", {e:tMsg(S.effErr)})));
    es.appendChild(retryBtn(loadEff));
    return;
  }
  if(!S.eff) return es.appendChild(el("div","hint", t("불러오는 중…")));
  if(!S.eff.length) return es.appendChild(el("div","hint", t("적용되는 규칙 파일이 없습니다.")));
  var list = el("div","efflist");
  S.eff.forEach(function(it, i){
    var cur = it.path === S.filePath, im = S.meta[it.path] || {};
    var row = el("div","effitem"+(cur ? " cur" : "")+(it.lazy ? " lazyit" : ""));
    row.title = it.path;
    row.appendChild(el("span","n", String(i+1)));
    row.appendChild(el("span", null, (im.label || it.path) + (cur ? t("  ← 현재") : "") + (it.lazy ? t(" · 지연") : "")));
    list.appendChild(row);
  });
  es.appendChild(list);
}
/* 충돌 — 같은 제목 섹션이 여러 파일에 (V5 warn) */
function confSection(ins){
  var cflist = S.conflicts || [];
  var cs = section(ins, t("충돌"), S.conflicts ? cflist.length : null);
  if(!S.project || S.project.exists === false) return cs.appendChild(el("div","hint", t("프로젝트를 선택하세요.")));
  if(!S.conflicts) return cs.appendChild(el("div","hint", S.effErr ? t("불러오지 못했습니다.") : t("불러오는 중…")));
  if(!cflist.length) return cs.appendChild(el("div","hint", t("같은 제목의 섹션이 겹치지 않습니다.")));
  var cl = el("div","cflist");
  cflist.forEach(function(c){
    var open = S.conflictSel === c.title;
    var b = el("button","cfitem");
    b.setAttribute("aria-expanded", String(open));
    b.appendChild(el("span","arw", open ? "▾" : "▸"));
    b.appendChild(el("span","t", c.title));
    b.appendChild(badge(t("{n}곳", {n:len(c.where)}),"warn"));
    b.onclick = function(){ S.conflictSel = open ? null : c.title; renderInspector(); };
    cl.appendChild(b);
    if(open) cl.appendChild(conflictBodies(c));
  });
  cs.appendChild(cl);
}
/* 이 프로젝트의 훅 */
function projHookSection(ins){
  var pref = "project:" + S.project.path + ":";
  var mine = ((S.scan && S.scan.hooks) || []).filter(function(h){
    return String(h.source||"").indexOf(pref) === 0; });
  var hs = section(ins, t("이 프로젝트의 훅"), mine.length);
  if(!mine.length) return hs.appendChild(el("div","hint", t("이 프로젝트에서 등록한 훅이 없습니다.")));
  var hl = el("div","hooklist");
  mine.forEach(function(h){
    var line = (h.event||"?") + " · " + (h.matcher || t("(전체)")) + " → " + (hookCmds(h).join(", ") || t("(명령 없음)"));
    var d = el("div","hookitem", line);
    if(h.warn === "duplicate-star") d.appendChild(el("span","warn", " · " + t("* 매처와 중복 발화")));
    hl.appendChild(d);
  });
  hs.appendChild(hl);
}
function renderInspector(){
  var ins = clear(document.getElementById("insbody"));
  document.getElementById("ins-title").textContent = insTitle();
  errSection(ins);
  if(S.selHook) return hookSections(ins);
  if(S.selMcp) return mcpSections(ins);
  var item = openItem();
  if(item) return itemSections(ins, item);
  if(S.filePath){
    fileProps(ins);
    effSection(ins);
    confSection(ins);
    return;
  }
  if(S.fileErr){
    var fs = section(ins, t("파일"));
    fs.appendChild(el("div","warn", S.fileErr));
  }
  if(S.project){
    projSection(ins);
    effSection(ins);
    confSection(ins);
    if(S.project.exists !== false) projHookSection(ins);
    return;
  }
  if(!S.fileErr) section(ins, t("안내")).appendChild(el("div","hint", t("사이드바에서 항목을 선택하세요.")));
}
