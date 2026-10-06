/* Metrobus, redrawn: an editable bus network for St. John's.
 *
 * Everything is recomputed in the browser from data/plan.json:
 *   buses       = ceil(round-trip minutes x recovery / headway)
 *   bus hours   = service hours x round-trip minutes / headway
 *   yearly cost = weekday bus hours, scaled so today's network matches Metrobus's
 *                 2025 total of revenue hours, x cost per bus hour
 *   coverage    = share of today's stops within walking distance of a stop
 *                 that has a bus every 15 minutes or better (all lines combined)
 */
(() => {
  "use strict";

  // Row-house paint colours for lines that don't bring their own.
  const PALETTE = ["#d7263d", "#1b6ca8", "#e0a100", "#2e8b57", "#7b3fa0", "#e86a1a", "#14a0a0", "#d94f93",
    "#4a6fe3", "#8a5a2b", "#5c9e2e", "#b0306a"];
  const HEADWAYS = [5, 6, 7.5, 10, 12, 15, 20, 30, 40, 60, 90, 120];
  const DATA_URL = new URLSearchParams(location.search).get("data") || "data/plan.json";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 0) => n.toLocaleString("en-CA", { maximumFractionDigits: d, minimumFractionDigits: d });
  const money = (n) => (Math.abs(n) >= 1e6 ? `$${fmt(n / 1e6, 1)}M` : `$${fmt(n / 1e3, 0)}K`);
  const hw = (h) => (h ? `every ${h % 1 ? h : fmt(h)} min` : "not running");

  let D; // data
  let placeById = new Map();
  let near = new Map(); // place id -> ids within walking distance
  const state = {
    scenario: "today",
    selected: null,
    edits: {}, // scenarioId -> lineId -> {h, a:[placeIds], r:[placeIds]}
    opts: {},
  };

  // ------------------------------------------------------------------ geometry
  const R = 6371000;
  function dist(a, b) {
    const p1 = (a.lat * Math.PI) / 180, p2 = (b.lat * Math.PI) / 180;
    const dp = p2 - p1, dl = ((b.lon - a.lon) * Math.PI) / 180;
    const x = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }

  function buildNear(walk) {
    near = new Map();
    const P = D.places;
    // Bucket into ~walk-sized cells so this stays fast for a few thousand stops.
    const cell = walk / 111000;
    const grid = new Map();
    const key = (i, j) => `${i},${j}`;
    for (const p of P) {
      const k = key(Math.floor(p.lat / cell), Math.floor(p.lon / (cell * 1.5)));
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push(p);
    }
    for (const p of P) {
      const i = Math.floor(p.lat / cell), j = Math.floor(p.lon / (cell * 1.5));
      const out = [];
      for (let di = -1; di <= 1; di++) for (let dj = -1; dj <= 1; dj++) {
        for (const q of grid.get(key(i + di, j + dj)) || []) if (dist(p, q) <= walk) out.push(q.id);
      }
      near.set(p.id, out);
    }
  }

  // ------------------------------------------------------------------ model
  const scenario = () => D.scenarios.find((s) => s.id === state.scenario);
  const editsFor = (sid) => (state.edits[sid] ||= {});
  const bothWays = (line) => line.kind === "trunk" || (line.kind === "route" && line.cycle_min > line.run_min * 1.2);

  // Apply a line's edits: headway, removed stops, added stops (inserted where they cost the least detour).
  function effective(line, sid) {
    const e = (state.edits[sid] || {})[line.id] || {};
    const o = state.opts;
    const h = e.h === undefined ? line.headway_min : e.h;
    let path = line.path.slice();
    let stopIdx = line.stop_idx.slice();
    const removed = new Set(e.r || []);
    const twice = bothWays(line) ? 2 : 1;
    const speed = Math.max((line.km * 1000) / (line.run_min * 60), 3); // m/s along this line
    let extraOneWay = 0;

    stopIdx = stopIdx.filter((i) => !removed.has(path[i]));
    extraOneWay -= (line.stop_idx.length - stopIdx.length) * o.dwell;

    for (const pid of e.a || []) {
      const p = placeById.get(pid);
      if (!p || stopIdx.some((i) => path[i] === pid)) continue;
      let best = null;
      for (let j = 0; j < path.length - 1; j++) {
        const a = placeById.get(path[j]), b = placeById.get(path[j + 1]);
        const extra = dist(a, p) + dist(p, b) - dist(a, b);
        if (!best || extra < best.extra) best = { j, extra };
      }
      if (!best) continue;
      path.splice(best.j + 1, 0, pid);
      stopIdx = stopIdx.map((i) => (i > best.j ? i + 1 : i));
      stopIdx.push(best.j + 1);
      stopIdx.sort((x, y) => x - y);
      extraOneWay += (best.extra * o.detour) / speed + o.dwell;
    }

    const run = Math.max(line.run_min + extraOneWay / 60, 1);
    const cycle = Math.max(line.cycle_min + (extraOneWay * twice) / 60, 1);
    const span = line.kind === "route" ? line.span_h : o.hours;
    return {
      line, h, path, stopIdx, run, cycle,
      buses: h ? Math.ceil((cycle * o.layover) / h) : 0,
      hours: h ? (span * cycle) / h : 0,
      stops: stopIdx.map((i) => path[i]),
      changed: e.h !== undefined || (e.a || []).length > 0 || (e.r || []).length > 0,
    };
  }

  function totals(sid, withEdits = true) {
    const s = D.scenarios.find((x) => x.id === sid);
    const saved = state.edits[sid];
    if (!withEdits) state.edits[sid] = {};
    const lines = s.lines.map((l) => effective(l, sid));
    if (!withEdits) { if (saved === undefined) delete state.edits[sid]; else state.edits[sid] = saved; }

    // Buses per hour at each stop place, all lines combined.
    const bph = new Map();
    for (const L of lines) {
      if (!L.h) continue;
      for (const pid of new Set(L.stops)) bph.set(pid, (bph.get(pid) || 0) + 60 / L.h);
    }
    const target = 60 / D.defaults.frequent_min - 1e-9;
    let frequent = 0, served = 0, total = 0;
    for (const p of D.places) {
      if (!p.deps) continue;
      total++;
      let best = 0;
      for (const q of near.get(p.id) || []) best = Math.max(best, bph.get(q) || 0);
      if (best > 0) served++;
      if (best >= target) frequent++;
    }
    return {
      lines,
      buses: lines.reduce((a, L) => a + L.buses, 0),
      hours: lines.reduce((a, L) => a + L.hours, 0),
      frequentPct: total ? (100 * frequent) / total : 0,
      unserved: total - served,
    };
  }

  let baseline; // today's network, unedited
  function annualCost(hours) {
    const factor = D.constants.annual_revenue_hours_2025 / baseline.hours;
    return hours * factor * state.opts.cost;
  }

  // ------------------------------------------------------------------ colours
  function colorOf(line, i) {
    if (line.color && line.kind === "route") return line.color;
    return PALETTE[i % PALETTE.length];
  }
  function badge(line, color, big = false) {
    const cls = `badge${line.kind === "feeder" ? " feeder" : ""}${big ? " big" : ""}`;
    return `<span class="${cls}" style="--c:${color}">${esc(line.name)}</span>`;
  }
  // White text on light route colours from the feed is unreadable; darken those.
  function readable(hex) {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    if (lum < 0.6) return hex;
    const k = 0.55;
    return `#${[r, g, b].map((v) => Math.round(v * k).toString(16).padStart(2, "0")).join("")}`;
  }

  // ------------------------------------------------------------------ map
  let map, bgLayer, lineLayer, stopLayer, placeLayer, hubLayer, gapLayer;
  const renderer = L.canvas({ padding: 0.5, tolerance: 6 });

  function initMap() {
    map = L.map("map", { zoomControl: true, preferCanvas: true, renderer });
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16,
      attribution: "Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
    }).addTo(map);
    const pts = D.places.map((p) => [p.lat, p.lon]);
    map.fitBounds(L.latLngBounds(pts), { padding: [20, 20] });

    bgLayer = L.layerGroup().addTo(map);
    for (const [u, v] of D.edges) {
      const a = placeById.get(u), b = placeById.get(v);
      L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { color: "#9aa4aa", weight: 1, opacity: 0.55, interactive: false, renderer }).addTo(bgLayer);
    }
    gapLayer = L.layerGroup().addTo(map);
    lineLayer = L.layerGroup().addTo(map);
    placeLayer = L.layerGroup().addTo(map);
    stopLayer = L.layerGroup().addTo(map);
    hubLayer = L.layerGroup().addTo(map);

    for (const p of D.places) {
      L.circleMarker([p.lat, p.lon], { radius: 3, color: "#7d878d", weight: 1, fillColor: "#fff", fillOpacity: 1, renderer })
        .on("click", () => openPlace(p))
        .addTo(placeLayer);
    }
    map.on("zoomend", updateZoomStyles);
    updateZoomStyles();
  }

  function updateZoomStyles() {
    const z = map.getZoom();
    // All stops are tappable when zoomed in, or while a line is picked for editing.
    if (z >= 13 || state.selected) map.addLayer(placeLayer); else map.removeLayer(placeLayer);
  }

  let current; // totals for the visible scenario
  let colors = new Map();

  function drawLines() {
    lineLayer.clearLayers();
    stopLayer.clearLayers();
    hubLayer.clearLayers();
    gapLayer.clearLayers();
    const s = scenario();
    const sel = state.selected;
    // Draw least frequent first so frequent lines sit on top.
    const order = current.lines.slice().sort((a, b) => (b.h || 999) - (a.h || 999));
    for (const L2 of order) {
      if (!L2.h) continue;
      const c = colors.get(L2.line.id);
      const ll = L2.path.map((id) => { const p = placeById.get(id); return [p.lat, p.lon]; });
      const w = Math.max(2.5, Math.min(9, 2 + 50 / L2.h));
      const dim = sel && sel !== L2.line.id;
      const poly = L.polyline(ll, {
        color: c, weight: sel === L2.line.id ? w + 3 : w, opacity: dim ? 0.18 : 0.9, renderer, interactive: !dim,
        dashArray: L2.line.kind === "feeder" ? "7 6" : null, lineJoin: "round",
      });
      poly.on("click", (ev) => { L.DomEvent.stop(ev); selectLine(L2.line.id); });
      poly.bindTooltip(`${L2.line.name}: ${hw(L2.h)}`, { sticky: true });
      poly.addTo(lineLayer);
    }
    // Stops of the selected line, or of every line when zoomed in.
    for (const L2 of current.lines) {
      if (!L2.h) continue;
      if (sel && sel !== L2.line.id) continue;
      const c = colors.get(L2.line.id);
      for (const pid of L2.stops) {
        const p = placeById.get(pid);
        L.circleMarker([p.lat, p.lon], { radius: sel ? 6 : 4, color: c, weight: sel ? 3 : 2, fillColor: "#fff", fillOpacity: 1, renderer })
          .on("click", (ev) => { L.DomEvent.stop(ev); openPlace(p); })
          .addTo(stopLayer);
      }
    }
    if (!sel && map.getZoom() < 13) map.removeLayer(stopLayer); else map.addLayer(stopLayer);
    updateZoomStyles();
    // Canvas draws (and hit-tests) in insertion order: keep stops above lines.
    placeLayer.eachLayer((m) => m.bringToFront());
    stopLayer.eachLayer((m) => m.bringToFront());

    for (const h of s.hubs || []) {
      const p = placeById.get(h);
      L.circleMarker([p.lat, p.lon], { radius: 8, color: "#1c2a33", weight: 3, fillColor: "#1c2a33", fillOpacity: 1, renderer })
        .bindTooltip(esc(p.name), { permanent: map.getZoom() >= 12, direction: "right", offset: [8, 0], className: "hub-label" })
        .on("click", (ev) => { L.DomEvent.stop(ev); openPlace(p); })
        .addTo(hubLayer);
    }

    // Stops that lost all service nearby.
    const bph = new Set();
    for (const L2 of current.lines) if (L2.h) for (const pid of L2.stops) bph.add(pid);
    for (const p of D.places) {
      if (!p.deps) continue;
      const ok = (near.get(p.id) || []).some((q) => bph.has(q));
      if (!ok) L.circleMarker([p.lat, p.lon], { radius: 5, color: "#b3261e", weight: 2, fillColor: "#b3261e", fillOpacity: 0.25, renderer, interactive: false }).addTo(gapLayer);
    }
  }

  function openPlace(p) {
    const sel = state.selected ? current.lines.find((x) => x.line.id === state.selected) : null;
    const serving = current.lines.filter((x) => x.h && x.stops.includes(p.id));
    let html = `<div class="pop"><h4>${esc(p.name)}</h4>`;
    html += `<p>${p.deps ? `${fmt(p.deps)} buses stop here on a weekday today` : "No buses stop here today"}${p.routes.length ? ` (routes ${p.routes.map(esc).join(", ")})` : ""}.</p>`;
    if (serving.length) {
      html += `<div class="served">${serving.map((x) => badge(x.line, colors.get(x.line.id))).join("")}</div>`;
    }
    if (sel) {
      const on = sel.stops.includes(p.id);
      const isEnd = on && (sel.stops[0] === p.id || sel.stops[sel.stops.length - 1] === p.id) && sel.line.kind !== "feeder";
      if (on && !isEnd) html += `<button data-act="remove" data-line="${sel.line.id}">Remove from ${esc(sel.line.name)}</button>`;
      else if (!on) html += `<button data-act="add" data-line="${sel.line.id}">Add to ${esc(sel.line.name)}</button>`;
      else html += `<p>This is where ${esc(sel.line.name)} starts or ends.</p>`;
    } else {
      const opts = current.lines.filter((x) => x.h && !x.stops.includes(p.id))
        .map((x) => ({ x, d: Math.min(...x.path.map((id) => dist(placeById.get(id), p))) }))
        .sort((a, b) => a.d - b.d).slice(0, 8);
      if (opts.length) {
        html += `<select aria-label="Line to add this stop to">${opts.map((o) => `<option value="${o.x.line.id}">${esc(o.x.line.name)} – ${esc(o.x.line.long_name || "")}</option>`).join("")}</select>`;
        html += `<button data-act="add-picked">Add stop to this line</button>`;
      }
    }
    html += "</div>";
    const pop = L.popup({ maxWidth: 260 }).setLatLng([p.lat, p.lon]).setContent(html).openOn(map);
    const el = pop.getElement();
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      const act = b.dataset.act;
      if (act === "add") addStop(b.dataset.line, p.id);
      if (act === "remove") removeStop(b.dataset.line, p.id);
      if (act === "add-picked") addStop(el.querySelector("select").value, p.id);
      map.closePopup();
    }));
  }

  // ------------------------------------------------------------------ edits
  function lineEdit(lineId) {
    const e = editsFor(state.scenario);
    return (e[lineId] ||= {});
  }
  function cleanup(lineId) {
    const e = editsFor(state.scenario);
    const x = e[lineId];
    if (!x) return;
    if (x.a && !x.a.length) delete x.a;
    if (x.r && !x.r.length) delete x.r;
    const base = scenario().lines.find((l) => l.id === lineId);
    if (x.h !== undefined && x.h === base.headway_min) delete x.h;
    if (!Object.keys(x).length) delete e[lineId];
  }
  function setHeadway(lineId, h) {
    lineEdit(lineId).h = h;
    cleanup(lineId);
    update();
  }
  function addStop(lineId, pid) {
    const x = lineEdit(lineId);
    if (x.r && x.r.includes(pid)) x.r = x.r.filter((q) => q !== pid);
    else (x.a ||= []).push(pid);
    cleanup(lineId);
    const name = scenario().lines.find((l) => l.id === lineId).name;
    toast(`Added ${placeById.get(pid).name} to ${name}`);
    update();
  }
  function removeStop(lineId, pid) {
    const x = lineEdit(lineId);
    if (x.a && x.a.includes(pid)) x.a = x.a.filter((q) => q !== pid);
    else (x.r ||= []).push(pid);
    cleanup(lineId);
    const name = scenario().lines.find((l) => l.id === lineId).name;
    toast(`Removed ${placeById.get(pid).name} from ${name}`);
    update();
  }
  function step(h, dir) {
    // dir +1 = more often (shorter wait), -1 = less often
    if (!h) return dir > 0 ? 60 : 0;
    let i = HEADWAYS.findIndex((x) => x >= h - 1e-9);
    if (i < 0) i = HEADWAYS.length - 1;
    if (HEADWAYS[i] !== h) return dir > 0 ? HEADWAYS[Math.max(i - 1, 0)] : HEADWAYS[i];
    if (dir > 0) return HEADWAYS[Math.max(i - 1, 0)];
    return i === HEADWAYS.length - 1 ? 0 : HEADWAYS[i + 1];
  }

  // ------------------------------------------------------------------ panel
  function stepperHtml(L2) {
    const changed = L2.h !== L2.line.headway_min;
    return `<div class="stepper${changed ? " changed" : ""}" data-line="${L2.line.id}">
      <button data-dir="-1" aria-label="Run ${esc(L2.line.name)} less often" ${L2.h === 0 ? "disabled" : ""}>−</button>
      <output>${L2.h ? `${L2.h} min` : "off"}${changed ? `<small>was ${L2.line.headway_min} min</small>` : ""}</output>
      <button data-dir="1" aria-label="Run ${esc(L2.line.name)} more often" ${L2.h === HEADWAYS[0] ? "disabled" : ""}>+</button>
    </div>`;
  }
  function wireSteppers(root) {
    root.querySelectorAll(".stepper").forEach((st) => st.querySelectorAll("button").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const L2 = current.lines.find((x) => x.line.id === st.dataset.line);
      setHeadway(L2.line.id, step(L2.h, +b.dataset.dir));
    })));
  }

  function renderScenarios() {
    $("scenarios").innerHTML = D.scenarios.map((s) =>
      `<button role="radio" aria-checked="${s.id === state.scenario}" data-id="${s.id}">${esc(s.label)}</button>`).join("");
    $("scenarios").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      state.scenario = b.dataset.id;
      state.selected = null;
      assignColors();
      update(true);
    }));
    $("scenario-note").textContent = scenario().description;
  }

  function delta(el, now, base, kind) {
    const d = now - base;
    const node = $(el);
    if (Math.abs(d) < (kind === "pct" ? 0.05 : 0.5)) {
      node.textContent = state.scenario === "today" && !Object.keys(editsFor("today")).length ? "Metrobus today" : "same as today";
      node.className = "d same";
      return;
    }
    // More buses, hours or cost is "down" (red); more coverage is "up" (green).
    const good = kind === "pct" ? d > 0 : d < 0;
    const sign = d > 0 ? "+" : "−";
    const v = Math.abs(d);
    const txt = kind === "money" ? money(v) : kind === "pct" ? `${fmt(v, 1)} pts` : fmt(v);
    node.textContent = `${sign}${txt} vs today`;
    node.className = `d ${good ? "up" : "down"}`;
  }

  function renderScore() {
    $("s-buses").textContent = fmt(current.buses);
    $("s-hours").textContent = fmt(current.hours);
    $("s-cost").textContent = money(annualCost(current.hours));
    $("s-freq").textContent = `${fmt(current.frequentPct, 0)}%`;
    delta("d-buses", current.buses, baseline.buses);
    delta("d-hours", current.hours, baseline.hours);
    delta("d-cost", annualCost(current.hours), annualCost(baseline.hours), "money");
    delta("d-freq", current.frequentPct, baseline.frequentPct, "pct");
    $("s-gap").textContent = current.unserved
      ? `${fmt(current.unserved)} of today's stops have no bus within ${state.opts.walk} m. They show as red circles on the map.`
      : "";
  }

  function renderList() {
    const s = scenario();
    const anyEdits = Object.keys(editsFor(state.scenario)).length > 0;
    $("reset").disabled = !anyEdits;
    $("lines-title").textContent = s.id === "today" ? "Today's routes" : "Lines";
    const groups = s.id === "today"
      ? [["", current.lines]]
      : [["Trunk lines between hubs", current.lines.filter((x) => x.line.kind === "trunk")],
        ["Feeder loops", current.lines.filter((x) => x.line.kind === "feeder")]];
    let html = "";
    for (const [label, ls] of groups) {
      if (label) html += `<li class="group-label" role="presentation">${label}</li>`;
      for (const L2 of ls) {
        const c = colors.get(L2.line.id);
        html += `<li class="${L2.h ? "" : "off"}">
          <button class="ln-open" data-line="${L2.line.id}">
            ${badge(L2.line, c)}
            <span class="ln-text"><span class="ln-name">${esc(L2.line.long_name || `Route ${L2.line.name}`)}</span>
            <span class="ln-sub"><b>${fmt(L2.buses)}</b> bus${L2.buses === 1 ? "" : "es"}, ${fmt(L2.run, 0)} min ${L2.line.kind === "feeder" ? "loop" : "end to end"}${L2.changed ? ", edited" : ""}</span></span>
          </button>
          ${stepperHtml(L2)}
        </li>`;
      }
    }
    $("line-list").innerHTML = html;
    $("line-list").querySelectorAll(".ln-open").forEach((b) => b.addEventListener("click", () => selectLine(b.dataset.line)));
    wireSteppers($("line-list"));
  }

  function renderDetail() {
    const L2 = current.lines.find((x) => x.line.id === state.selected);
    $("lines-view").hidden = !!L2;
    $("detail").hidden = !L2;
    if (!L2) return;
    const line = L2.line;
    const c = colors.get(line.id);
    $("d-badge").outerHTML = `<span class="badge big${line.kind === "feeder" ? " feeder" : ""}" id="d-badge" style="--c:${c}">${esc(line.name)}</span>`;
    $("d-name").textContent = line.long_name || `Route ${line.name}`;
    $("d-via").textContent = line.via && line.via.length ? `via ${line.via.join(", ")}`
      : line.kind === "feeder" ? "Starts and ends at the hub, so every trip meets the trunk lines there." : "";
    $("d-stepper").outerHTML = stepperHtml(L2).replace('class="stepper', 'id="d-stepper" class="stepper');
    wireSteppers($("detail"));
    const roundTrip = line.kind === "feeder" ? "Loop time" : "Round trip";
    $("d-facts").innerHTML = [
      [fmt(L2.buses), "buses needed"],
      [fmt(L2.hours, 0), "bus hours a weekday"],
      [`${fmt(L2.run, 0)} min`, line.kind === "feeder" ? "around the loop" : "end to end"],
      [`${fmt(L2.cycle, 0)} min`, roundTrip.toLowerCase() + (line.kind === "feeder" ? "" : " before recovery")],
    ].map(([v, k]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

    const e = (state.edits[state.scenario] || {})[line.id] || {};
    const added = new Set(e.a || []);
    const hubs = new Set(scenario().hubs || []);
    const first = L2.stops[0], last = L2.stops[L2.stops.length - 1];
    // Show removed stops in place (struck through) so they're easy to put back.
    const removed = new Set(e.r || []);
    const rows = L2.stopIdx.map((i) => ({ i, pid: L2.path[i], gone: false }));
    L2.path.forEach((pid, i) => { if (removed.has(pid) && !rows.some((r) => r.pid === pid)) { rows.push({ i, pid, gone: true }); removed.delete(pid); } });
    rows.sort((a, b) => a.i - b.i);
    let html = "";
    for (const { pid, gone } of rows) {
      const p = placeById.get(pid);
      if (gone) {
        html += `<li class="gone" style="--c:${c}"><span class="dot"></span><span class="nm">${esc(p.name)}</span><button class="x" data-put="${pid}">put back</button></li>`;
        continue;
      }
      const locked = line.kind !== "feeder" ? (pid === first || pid === last) : pid === first;
      html += `<li class="${hubs.has(pid) ? "hub" : ""}" style="--c:${c}"><span class="dot"></span><span class="nm">${esc(p.name)}</span>
        ${added.has(pid) ? '<span class="tag">added</span>' : ""}
        ${locked ? "" : `<button class="x" data-pid="${pid}">remove</button>`}</li>`;
    }
    $("d-stops").innerHTML = html;
    $("d-stops").querySelectorAll("button[data-pid]").forEach((b) => b.addEventListener("click", () => removeStop(line.id, +b.dataset.pid)));
    $("d-stops").querySelectorAll("button[data-put]").forEach((b) => b.addEventListener("click", () => addStop(line.id, +b.dataset.put)));
  }

  function selectLine(id) {
    state.selected = id;
    update();
    const L2 = current.lines.find((x) => x.line.id === id);
    if (L2) {
      const ll = L2.path.map((pid) => { const p = placeById.get(pid); return [p.lat, p.lon]; });
      map.fitBounds(L.latLngBounds(ll), { padding: [40, 40], maxZoom: 15 });
      $("panel").scrollTop = 0;
    }
  }

  function assignColors() {
    colors = new Map();
    scenario().lines.forEach((l, i) => colors.set(l.id, readable(colorOf(l, i))));
  }

  // ------------------------------------------------------------------ share link
  function encodeState() {
    const edits = {};
    for (const [sid, e] of Object.entries(state.edits)) if (e && Object.keys(e).length) edits[sid] = e;
    const o = {};
    for (const k of Object.keys(DEFAULT_OPTS)) if (state.opts[k] !== DEFAULT_OPTS[k]) o[k] = state.opts[k];
    const payload = { s: state.scenario, e: edits, o };
    return btoa(unescape(encodeURIComponent(JSON.stringify(payload)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function decodeState(str) {
    try {
      const b = str.replace(/-/g, "+").replace(/_/g, "/");
      const p = JSON.parse(decodeURIComponent(escape(atob(b))));
      if (p.s && D.scenarios.some((s) => s.id === p.s)) state.scenario = p.s;
      if (p.e && typeof p.e === "object") state.edits = p.e;
      if (p.o) Object.assign(state.opts, p.o);
    } catch (err) {
      toast("That link's changes couldn't be read, so this is the starting version.");
    }
  }

  let toastTimer;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
  }

  // ------------------------------------------------------------------ settings
  let DEFAULT_OPTS;
  function initSettings() {
    const bind = (id, key, toModel, fromModel) => {
      const el = $(id);
      el.value = fromModel(state.opts[key]);
      el.addEventListener("change", () => {
        const v = parseFloat(el.value);
        if (Number.isFinite(v)) {
          state.opts[key] = toModel(v);
          if (key === "walk") buildNear(state.opts.walk);
          baseline = totals("today", false);
          update();
        }
      });
    };
    bind("o-hours", "hours", (v) => v, (v) => v);
    bind("o-layover", "layover", (v) => 1 + v / 100, (v) => Math.round((v - 1) * 100));
    bind("o-dwell", "dwell", (v) => v, (v) => v);
    bind("o-cost", "cost", (v) => v, (v) => v);
    bind("o-walk", "walk", (v) => v, (v) => v);
  }

  // ------------------------------------------------------------------ main loop
  function update(refit = false) {
    current = totals(state.scenario);
    renderScenarios();
    renderScore();
    renderList();
    renderDetail();
    drawLines();
    history.replaceState(null, "", `#${encodeState()}`);
    if (refit) {
      const pts = [];
      for (const L2 of current.lines) for (const id of L2.path) { const p = placeById.get(id); pts.push([p.lat, p.lon]); }
      if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [20, 20] });
    }
  }

  function fine() {
    const a = D.today_actual;
    $("fine").innerHTML =
      `Built from the Metrobus GTFS schedule for ${esc(D.service_date)}: ${fmt(a.routes)} routes, ${fmt(a.weekday_trips)} weekday trips, ` +
      `${fmt(a.stops)} stops. Today's routes use their midday frequency all day, so their totals are a model, not the timetable ` +
      `(the timetable has ${fmt(a.weekday_revenue_hours)} bus hours on a weekday). Yearly cost scales weekday hours so today's routes ` +
      `match Metrobus's 156,004 revenue hours in 2025, at $${fmt(D.constants.cost_per_revenue_hour_2025, 2)} per hour. ` +
      `Ridership isn't modelled. <a href="https://github.com/ammar-15/metrobus-efficiency">Code and method</a>.`;
  }

  async function main() {
    let res;
    try {
      res = await fetch(DATA_URL, { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      D = await res.json();
    } catch (err) {
      document.body.innerHTML = `<p style="padding:24px;font-family:var(--font)">The network data didn't load (${esc(err.message)}). ` +
        `Run <code>python -m metrobus_efficiency --web</code> to create <code>docs/data/plan.json</code>, then reload.</p>`;
      return;
    }
    placeById = new Map(D.places.map((p) => [p.id, p]));
    DEFAULT_OPTS = {
      hours: D.defaults.service_hours,
      layover: D.defaults.layover_factor,
      dwell: D.defaults.dwell_s,
      detour: D.defaults.detour_factor,
      cost: D.constants.cost_per_revenue_hour_2025,
      walk: D.defaults.walk_m,
    };
    state.opts = { ...DEFAULT_OPTS };
    if (location.hash.length > 1) decodeState(location.hash.slice(1));
    buildNear(state.opts.walk);
    baseline = totals("today", false);
    initMap();
    initSettings();
    assignColors();
    fine();

    $("back").addEventListener("click", () => { state.selected = null; update(); });
    $("reset").addEventListener("click", () => { state.edits[state.scenario] = {}; update(); toast("Changes undone"); });
    $("share").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.href); toast("Link copied"); }
      catch { toast("Copy the address bar to share this version"); }
    });
    $("grip").addEventListener("click", () => {
      const big = document.querySelector(".app").classList.toggle("map-big");
      $("grip").setAttribute("aria-expanded", String(!big));
      setTimeout(() => map.invalidateSize(), 260);
    });
    update(false);
    window.metrobusMap = map; // handy for debugging in the browser console
  }

  main();
})();
