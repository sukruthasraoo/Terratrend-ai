/* TerraTrend AI — frontend. One shared investigation context (S.place, S.period) drives every view. */
'use strict';

const S = {
  place: null, startYear: 1995, category: 'climate', view: 'explorer',
  layers: [], active: new Set(['MODIS_Terra_CorrectedReflectance_TrueColor']), imageryLayers: {},
  date: new Date(Date.now() - 3 * 86400e3), // GIBS NRT imagery usually lags 1–3 days
  playing: null, inv: {}, events: [], eventEntities: [], recent: [], aiLog: [],
  compare: { places: [], results: null }, reports: [], config: {},
};
const $ = (id) => document.getElementById(id);
const fmt = (x, n = 2) => (x == null || Number.isNaN(x)) ? 'n/a' : Number(x).toFixed(n);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const toast = (m, ms = 3500) => { const t = $('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), ms); };
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) { let d = ''; try { d = (await r.json()).detail; } catch { } throw new Error(d || `${r.status} ${r.statusText}`); }
  return r.json();
};
const post = (path, body) => api(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
const ymd = (d) => d.toISOString().slice(0, 10);
const PLOT = { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#8a9bb8', family: 'Sora, sans-serif', size: 11 },
  margin: { l: 48, r: 14, t: 28, b: 36 }, xaxis: { gridcolor: 'rgba(118,170,255,.12)', zeroline: false }, yaxis: { gridcolor: 'rgba(118,170,255,.12)', zeroline: false },
  legend: { orientation: 'h', y: 1.12 }, hovermode: 'x unified' };
const PCFG = { displayModeBar: false, responsive: true };
const CAT = {
  climate: ['Climate & temperature', 'Temperature, rainfall, humidity, wind, radiation — NASA POWER (MERRA-2)'],
  atmosphere: ['Atmosphere & air', 'Humidity series (POWER) + aerosol/cloud imagery (MODIS via GIBS)'],
  vegetation: ['Forests & biosphere', 'NDVI imagery (MODIS via GIBS); numeric series pending Earthdata access'],
  ocean: ['Oceans & marine', 'Sea-surface temperature imagery (MUR via GIBS); OISST series pending'],
  water: ['Water & hydrology', 'Precipitation and soil wetness — NASA POWER; SMAP/GRACE imagery'],
  cryosphere: ['Cryosphere', 'Snow cover and sea-ice imagery (MODIS/AMSR2 via GIBS)'],
  hazards: ['Natural hazards', 'EONET events, USGS earthquakes, FIRMS fires (key)'],
  land: ['Land & surface', 'Skin temperature (POWER) + land-surface temperature imagery'],
  energy: ['Solar & energy balance', 'Surface shortwave/longwave radiation — NASA POWER (CERES)'],
};
const EVCOLOR = { Wildfires: '#ff5a5f', Earthquakes: '#ffb547', 'Severe Storms': '#8b6cff', Volcanoes: '#ff8a3d', 'Sea and Lake Ice': '#2ee6ff', Floods: '#4ab3ff' };

/* ───────────────────────── globe ───────────────────────── */
let viewer, boundaryDs = null, marker = null;
function gibsProvider(layer, date) {
  // GIBS EPSG:4326 matrices are 2x1, 3x2, 5x3, then 10x5 doubling. Cesium's scheme needs
  // clean doubling, so we start at a 10x5 level-zero grid and map Cesium level k -> GIBS matrix k+3.
  const time = layer.daily ? ymd(date) : 'default';
  const labels = []; for (let k = 3; k <= layer.max; k++) labels.push(String(k));
  return new Cesium.WebMapTileServiceImageryProvider({
    url: `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi?TIME=${time}`,
    layer: layer.id, style: 'default', format: layer.fmt === 'jpg' || layer.fmt === 'jpeg' ? 'image/jpeg' : 'image/png',
    tileMatrixSetID: layer.matrix, tileMatrixLabels: labels, maximumLevel: labels.length - 1, tileWidth: 512, tileHeight: 512,
    tilingScheme: new Cesium.GeographicTilingScheme({ numberOfLevelZeroTilesX: 10, numberOfLevelZeroTilesY: 5 }),
    credit: 'NASA GIBS',
  });
}
function initGlobe() {
  if (S.config.cesium_ion_token) Cesium.Ion.defaultAccessToken = S.config.cesium_ion_token;
  const base = S.layers.find((l) => l.id === 'BlueMarble_ShadedRelief_Bathymetry');
  viewer = new Cesium.Viewer('globe', {
    baseLayer: new Cesium.ImageryLayer(gibsProvider(base, S.date)),
    terrain: S.config.cesium_ion_token ? Cesium.Terrain.fromWorldTerrain() : undefined,
    animation: false, timeline: false, geocoder: false, baseLayerPicker: false, sceneModePicker: false,
    navigationHelpButton: false, homeButton: false, infoBox: false, selectionIndicator: false, fullscreenButton: false,
    skyAtmosphere: new Cesium.SkyAtmosphere(), requestRenderMode: true, maximumRenderTimeChange: Infinity,
  });
  viewer.scene.globe.showGroundAtmosphere = true;
  viewer.scene.globe.enableLighting = false;
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#04070f');
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#04070f');
  viewer.scene.skyBox.show = true;
  viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(78, 15, 2.1e7), duration: 0 });
  const h = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  h.setInputAction(async (e) => {
    const picked = viewer.scene.pick(e.position);
    if (picked && picked.id && picked.id._ttEvent) { showEvent(picked.id._ttEvent); return; }
    const cart = viewer.camera.pickEllipsoid(e.position, viewer.scene.globe.ellipsoid);
    if (!cart) return;
    const c = Cesium.Cartographic.fromCartesian(cart);
    selectCoords(Cesium.Math.toDegrees(c.latitude), Cesium.Math.toDegrees(c.longitude));
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  for (const id of S.active) toggleLayer(id, true);
}
function toggleLayer(id, on) {
  const layer = S.layers.find((l) => l.id === id);
  if (!layer) return;
  if (S.imageryLayers[id]) { viewer.imageryLayers.remove(S.imageryLayers[id]); delete S.imageryLayers[id]; }
  if (on) {
    const il = viewer.imageryLayers.addImageryProvider(gibsProvider(layer, S.date));
    il.alpha = layer.group === 'imagery' ? 1 : 0.85;
    S.imageryLayers[id] = il; S.active.add(id);
  } else S.active.delete(id);
  viewer.scene.requestRender();
}
function refreshLayerDates() { for (const id of [...S.active]) toggleLayer(id, true); }
function flyTo(place) {
  const [w, s, e, n] = place.bbox;
  const pad = Math.max(0.05, (e - w) * 0.15);
  viewer.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(w - pad, s - pad, e + pad, n + pad), duration: 1.6 });
  if (boundaryDs) { viewer.dataSources.remove(boundaryDs); boundaryDs = null; }
  if (marker) { viewer.entities.remove(marker); marker = null; }
  if (place.geometry) {
    Cesium.GeoJsonDataSource.load({ type: 'Feature', geometry: place.geometry, properties: {} }, {
      stroke: Cesium.Color.fromCssColorString('#2ee6ff'), fill: Cesium.Color.fromCssColorString('#2ee6ff').withAlpha(0.08), strokeWidth: 2, clampToGround: true,
    }).then((ds) => { boundaryDs = ds; viewer.dataSources.add(ds); viewer.scene.requestRender(); });
  } else {
    marker = viewer.entities.add({ position: Cesium.Cartesian3.fromDegrees(place.lon, place.lat),
      point: { pixelSize: 10, color: Cesium.Color.fromCssColorString('#2ee6ff'), outlineColor: Cesium.Color.WHITE.withAlpha(0.6), outlineWidth: 2 } });
    viewer.entities.add({ rectangle: { coordinates: Cesium.Rectangle.fromDegrees(w, s, e, n), material: Cesium.Color.fromCssColorString('#2ee6ff').withAlpha(0.06), outline: true, outlineColor: Cesium.Color.fromCssColorString('#2ee6ff') }, _ttBox: true });
  }
}
function clearEventEntities() { for (const en of S.eventEntities) viewer.entities.remove(en); S.eventEntities = []; }
function drawEvents(evs) {
  clearEventEntities();
  for (const ev of evs.slice(0, 1500)) {
    const col = EVCOLOR[ev.category] || '#ffb547';
    const mag = ev.magnitude?.value;
    const size = ev.category === 'Earthquakes' ? Math.max(4, (mag || 2) * 2.2) : 7;
    const en = viewer.entities.add({ position: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat),
      point: { pixelSize: size, color: Cesium.Color.fromCssColorString(col).withAlpha(0.85), outlineColor: Cesium.Color.fromCssColorString(col).withAlpha(0.3), outlineWidth: 4, disableDepthTestDistance: Number.POSITIVE_INFINITY } });
    en._ttEvent = ev; S.eventEntities.push(en);
  }
  viewer.scene.requestRender();
}

/* ───────────────────────── location ───────────────────────── */
async function setPlace(place) {
  S.place = place; S.inv = {};
  $('ctx').textContent = place.short_name || place.name;
  $('loc-type').textContent = place.type;
  $('welcome').classList.add('hidden');
  if (!S.recent.find((r) => r.name === place.name)) { S.recent.unshift(place); S.recent = S.recent.slice(0, 6); }
  flyTo(place);
  renderLocationPanel();
  render();
}
async function selectCoords(lat, lon) {
  try { const r = await api(`/api/locations/resolve?lat=${lat}&lon=${lon}`); setPlace(r.place); }
  catch (e) { toast('Could not resolve location: ' + e.message); }
}
function renderLocationPanel() {
  const p = S.place;
  const body = $('loc-body');
  const recent = S.recent.map((r) => `<button class="btn small" style="margin:2px 4px 2px 0" data-recent="${esc(r.name)}">${esc(r.short_name || r.name)}</button>`).join('') || '<span class="muted">None yet</span>';
  body.innerHTML = (p ? `<div class="card"><h3>${esc(p.name)}</h3><dl class="kv">
      <dt>Type</dt><dd>${esc(p.type)}</dd><dt>Centroid</dt><dd>${fmt(p.lat, 4)}, ${fmt(p.lon, 4)}</dd>
      <dt>Bounding box</dt><dd>${p.bbox.map((v) => fmt(v, 2)).join(', ')}</dd>
      <dt>Boundary</dt><dd>${p.geometry ? 'administrative polygon (OSM)' : 'bbox / point only'}</dd>
      <dt>Aggregation</dt><dd>${(p.bbox[2] - p.bbox[0]) * (p.bbox[3] - p.bbox[1]) > 1 ? 'area mean over POWER grid cells' : 'POWER grid cell at centroid'}</dd></dl>
      <div class="row" style="margin-top:8px"><button class="btn primary" id="open-inv">Open investigation</button></div></div>
      <div id="avail" class="muted">Checking dataset coverage…</div>` : '<p class="muted">Search above, or click anywhere on the globe to select a point.</p>')
    + `<div class="field" style="margin-top:12px"><label>Coordinates</label><div class="row"><input id="lat" placeholder="lat" inputmode="decimal" value="${p ? fmt(p.lat, 4) : ''}"><input id="lon" placeholder="lon" inputmode="decimal" value="${p ? fmt(p.lon, 4) : ''}"><button class="btn small" id="go-coords">Go</button></div></div>
       <div class="field"><label>Recent investigations</label><div id="recent">${recent}</div></div>`;
  body.querySelector('#go-coords').onclick = () => { const la = parseFloat($('lat').value), lo = parseFloat($('lon').value); if (Number.isFinite(la) && Number.isFinite(lo)) selectCoords(la, lo); };
  body.querySelectorAll('[data-recent]').forEach((b) => b.onclick = () => setPlace(S.recent.find((r) => r.name === b.dataset.recent)));
  const oi = body.querySelector('#open-inv'); if (oi) oi.onclick = () => switchView('intel');
  if (p) loadAvailability();
}
async function loadAvailability() {
  const p = S.place;
  try {
    const a = await api(`/api/datasets/availability?bbox=${p.bbox.join(',')}&place_type=${p.type}`);
    S.availability = a.categories;
    const el = $('avail'); if (!el) return;
    el.innerHTML = '<div class="card"><h3>Dataset coverage</h3>' + Object.entries(a.categories).map(([k, v]) =>
      `<div style="display:flex;justify-content:space-between;padding:3px 0"><span>${CAT[k][0]}</span><span class="tag ${v.status === 'available' ? 'ok' : v.status === 'not applicable' ? '' : 'warn'}">${v.status}${v.cmr_hits != null ? ` · ${v.cmr_hits} CMR` : ''}</span></div>`).join('') + '</div>';
  } catch (e) { const el = $('avail'); if (el) el.textContent = 'Coverage check failed: ' + e.message; }
}

/* ───────────────────────── search ───────────────────────── */
let searchTimer;
$('q').addEventListener('input', (e) => {
  clearTimeout(searchTimer); const q = e.target.value.trim();
  if (q.length < 2) { $('results').classList.remove('open'); return; }
  const m = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (m) { $('results').innerHTML = `<button data-coords="${m[1]},${m[2]}">Go to ${m[1]}, ${m[2]}<small>coordinates</small></button>`; $('results').classList.add('open'); return; }
  searchTimer = setTimeout(async () => {
    try {
      const r = await api(`/api/locations/search?q=${encodeURIComponent(q)}`);
      $('results').innerHTML = r.results.length ? r.results.map((p, i) => `<button data-i="${i}">${esc(p.short_name)} <small>${esc(p.type)} · ${esc(p.name)}</small></button>`).join('') : '<button disabled>No places found. Try a different spelling.</button>';
      $('results')._items = r.results; $('results').classList.add('open');
    } catch (err) { $('results').innerHTML = `<button disabled>Search failed: ${esc(err.message)}</button>`; $('results').classList.add('open'); }
  }, 350);
});
$('results').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  $('results').classList.remove('open'); $('q').value = '';
  if (b.dataset.coords) { const [la, lo] = b.dataset.coords.split(',').map(Number); selectCoords(la, lo); return; }
  const p = $('results')._items[+b.dataset.i]; if (p) setPlace(p);
});
document.addEventListener('click', (e) => { if (!e.target.closest('.search')) $('results').classList.remove('open'); });

/* ───────────────────────── layers & timeline ───────────────────────── */
const GROUPCOL = { imagery: '#dfe8f6', temperature: '#ff5a5f', ocean: '#4ab3ff', precipitation: '#2ee6ff', vegetation: '#4ade80', wildfires: '#ff8a3d', air: '#c9b8ff', snowice: '#bfefff', soil: '#c8a27a', solar: '#ffb547', base: '#8a9bb8' };
function renderLayers() {
  $('layers').innerHTML = `<label class="layer"><input type="checkbox" id="lighting" ${viewer.scene.globe.enableLighting ? 'checked' : ''}><span class="sw" style="background:#ffb547"></span><span>Day/night shading<small>sun position for the current UTC time</small></span></label>` + S.layers.filter((l) => l.group !== 'base').map((l) => `<label class="layer"><input type="checkbox" data-layer="${l.id}" ${S.active.has(l.id) ? 'checked' : ''}><span class="sw" style="background:${GROUPCOL[l.group]}"></span><span>${esc(l.name)}<small>${l.daily ? 'daily since ' + l.since : 'static'} · ${l.matrix}</small></span></label>`).join('');
  $('layers').querySelectorAll('input[data-layer]').forEach((i) => i.onchange = () => toggleLayer(i.dataset.layer, i.checked));
  $('lighting').onchange = (e) => { viewer.scene.globe.enableLighting = e.target.checked; viewer.scene.requestRender(); };
}
const T0 = new Date('2000-03-01'), T1 = new Date(Date.now() - 1 * 86400e3);
function dateFromSlider(v) { return new Date(T0.getTime() + (T1 - T0) * (v / 1000)); }
function sliderFromDate(d) { return Math.round(1000 * (d - T0) / (T1 - T0)); }
function setDate(d) { S.date = new Date(Math.min(T1, Math.max(T0, d))); $('tdate').textContent = ymd(S.date); $('tslider').value = sliderFromDate(S.date); refreshLayerDates(); }
$('tslider').max = 1000; $('tslider').addEventListener('input', (e) => { S.date = dateFromSlider(+e.target.value); $('tdate').textContent = ymd(S.date); });
$('tslider').addEventListener('change', (e) => setDate(dateFromSlider(+e.target.value)));
const step = (dir) => setDate(new Date(S.date.getTime() + dir * (+$('tspeed').value) * 86400e3));
$('tprev').onclick = () => step(-1); $('tnext').onclick = () => step(1);
$('tplay').onclick = () => { if (S.playing) { clearInterval(S.playing); S.playing = null; $('tplay').textContent = 'Play'; } else { $('tplay').textContent = 'Pause'; S.playing = setInterval(() => { if (S.date >= T1) { clearInterval(S.playing); S.playing = null; $('tplay').textContent = 'Play'; } else step(1); }, 1500); } };

/* ───────────────────────── views ───────────────────────── */
const VIEWS = { explorer: 'Earth Explorer', live: 'Live Earth Monitor', intel: 'Environmental Intelligence', trends: 'Historical Trends & Anomalies', ai: 'TerraTrend Intelligence', compare: 'Regional Comparison', datasets: 'Dataset Explorer', reports: 'Reports & Evidence' };
$('nav').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) switchView(b.dataset.view); });
function switchView(v) {
  S.view = v;
  $('nav').querySelectorAll('button').forEach((b) => b.removeAttribute('aria-current'));
  $('nav').querySelector(`[data-view="${v}"]`).setAttribute('aria-current', 'page');
  const explorer = v === 'explorer', live = v === 'live';
  $('p-left').classList.toggle('hidden', !(explorer || live));
  $('p-right').classList.toggle('hidden', !explorer);
  $('p-bottom').classList.toggle('hidden', !explorer);
  $('legend').classList.toggle('hidden', !explorer);
  $('p-center').classList.toggle('hidden', explorer);
  $('p-center').classList.toggle('full', !explorer && !live);
  $('p-center').classList.toggle('center', live);
  if (live) $('p-center').style.left = '336px'; else $('p-center').style.left = '';
  $('center-title').textContent = VIEWS[v];
  if (!live) clearEventEntities();
  render();
}
function needPlace() { if (!S.place) { $('center-body').innerHTML = '<div class="empty">Select a location first — search above or click the globe in Earth Explorer.</div>'; return true; } return false; }
async function render() {
  const v = S.view;
  if (v === 'explorer') return;
  if (v === 'live') return renderLive();
  if (v === 'intel') return renderIntel();
  if (v === 'trends') return renderTrends();
  if (v === 'ai') return renderAI();
  if (v === 'compare') return renderCompare();
  if (v === 'datasets') return renderDatasets();
  if (v === 'reports') return renderReports();
}
function invKey(category, vars, start) { return `${S.place.name}|${category}|${(vars || []).join(',')}|${start}`; }
async function getInvestigation(category = S.category, vars = null, start = S.startYear) {
  const k = invKey(category, vars, start);
  if (!S.inv[k]) S.inv[k] = post('/api/investigation', { place: S.place, category, variables: vars, start_year: start });
  return S.inv[k];
}
function trendTag(o, unit) {
  if (!o || !o.available) return '<span class="tag">trend n/a</span>';
  const cls = o.significant_05 ? (o.slope_per_decade > 0 ? 'up' : 'down') : 'flat';
  return `<span class="${cls}">${o.slope_per_decade > 0 ? '+' : ''}${fmt(o.slope_per_decade, 3)} ${unit}/decade</span> <span class="tag ${o.significant_05 ? 'ok' : ''}">p=${fmt(o.p_value, 3)}${o.significant_05 ? ' significant' : ' not significant'}</span>`;
}

/* ── Live monitor ── */
async function renderLive() {
  const body = $('center-body');
  body.innerHTML = `<div class="row" style="margin-bottom:10px"><select id="ev-cat"><option value="">All categories</option></select>
    <select id="ev-days"><option value="7">last 7 days</option><option value="30" selected>last 30 days</option><option value="90">last 90 days</option><option value="365">last year</option></select>
    <label class="layer" style="border:0;flex:none"><input type="checkbox" id="ev-here" ${S.place ? 'checked' : ''} ${S.place ? '' : 'disabled'}> near selected location</label>
    <button class="btn primary" id="ev-go" style="flex:none">Refresh</button></div><div id="ev-src" class="muted" style="margin-bottom:8px"></div><div class="sidebyside"><div id="ev-list"></div><div id="ev-detail"><div class="empty">Click an event in the list or on the globe.</div></div></div>`;
  try { const c = await api('/api/events/categories'); body.querySelector('#ev-cat').innerHTML += c.categories.map((x) => `<option value="${x.id}">${esc(x.title)}</option>`).join(''); } catch { }
  const load = async () => {
    const cat = body.querySelector('#ev-cat').value, days = body.querySelector('#ev-days').value, here = body.querySelector('#ev-here').checked && S.place;
    body.querySelector('#ev-list').innerHTML = '<div class="empty"><span class="spinner"></span>Loading observations…</div>';
    try {
      const q = new URLSearchParams({ days, status: days > 30 ? 'all' : 'open' }); if (cat && cat !== 'earthquakes') q.set('category', cat); if (here) q.set('bbox', S.place.bbox.join(','));
      const r = await api('/api/events?' + q);
      let evs = r.events; if (cat === 'earthquakes') evs = evs.filter((e) => e.category_id === 'earthquakes'); else if (cat) evs = evs.filter((e) => e.category_id !== 'earthquakes');
      S.events = evs; drawEvents(evs);
      body.querySelector('#ev-src').innerHTML = r.sources.map((s) => `<span class="tag ${s.ok ? 'ok' : s.pending ? 'warn' : 'bad'}" title="${esc(s.error || '')}">${s.id}${s.ok ? ' · ' + s.count : s.pending ? ' · pending' : ' · unavailable'}</span>`).join('') + ` <span class="muted">generated ${r.generated.slice(0, 16).replace('T', ' ')} UTC · observation times are the source's own, not real time</span>`;
      body.querySelector('#ev-list').innerHTML = evs.length ? evs.slice(0, 300).map((e, i) => `<div class="event" data-i="${i}"><b style="color:${EVCOLOR[e.category] || '#ffb547'}">●</b> <b>${esc(e.title)}</b><small>${esc(e.category)} · ${esc((e.observed || '').slice(0, 16).replace('T', ' '))} UTC · ${fmt(e.lat, 2)}, ${fmt(e.lon, 2)}${e.magnitude?.value != null ? ' · ' + e.magnitude.value + ' ' + esc(e.magnitude.unit || '') : ''}</small></div>`).join('') + (evs.length > 300 ? `<p class="muted">Showing 300 of ${evs.length}.</p>` : '') : '<div class="empty">No documented events for this filter.</div>';
      body.querySelectorAll('.event').forEach((el) => el.onclick = () => showEvent(evs[+el.dataset.i]));
    } catch (e) { body.querySelector('#ev-list').innerHTML = `<div class="empty">Event feeds unavailable: ${esc(e.message)}</div>`; }
  };
  body.querySelector('#ev-go').onclick = load; load();
}
function showEvent(ev) {
  if (S.view !== 'live') switchView('live');
  setTimeout(() => {
    const d = $('ev-detail'); if (!d) return;
    d.innerHTML = `<div class="card"><h3>${esc(ev.title)}</h3><dl class="kv">
      <dt>Category</dt><dd>${esc(ev.category)}</dd><dt>Coordinates</dt><dd>${fmt(ev.lat, 4)}, ${fmt(ev.lon, 4)}${ev.depth_km != null ? ` · depth ${fmt(ev.depth_km, 1)} km` : ''}</dd>
      <dt>Observed</dt><dd>${esc(ev.observed || 'n/a')}</dd>${ev.published ? `<dt>Published</dt><dd>${esc(ev.published)}</dd>` : ''}
      <dt>Measurement</dt><dd>${ev.magnitude?.value != null ? `${ev.magnitude.value} ${esc(ev.magnitude.unit || '')}` : 'none supplied by source'}</dd>
      ${ev.sensor ? `<dt>Sensor</dt><dd>${esc(ev.sensor)}</dd>` : ''}${ev.quality ? `<dt>Quality</dt><dd>${esc(JSON.stringify(ev.quality))}</dd>` : ''}
      ${ev.n_observations ? `<dt>Observations</dt><dd>${ev.n_observations} geometry records</dd>` : ''}
      <dt>Provider</dt><dd>${esc(ev.provider)}</dd><dt>Source links</dt><dd>${(ev.sources || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.id)}</a>`).join(', ')}${ev.link ? ` · <a href="${esc(ev.link)}" target="_blank" rel="noopener">record</a>` : ''}</dd></dl>
      <div class="row" style="margin-top:8px"><button class="btn small" id="ev-fly">Fly to event</button><button class="btn small" id="ev-inv">Investigate this area</button></div></div>`;
    d.querySelector('#ev-fly').onclick = () => viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat, 600000) });
    d.querySelector('#ev-inv').onclick = () => selectCoords(ev.lat, ev.lon);
  }, 50);
}

/* ── Environmental intelligence ── */
async function renderIntel() {
  if (needPlace()) return;
  const body = $('center-body');
  body.innerHTML = `<div class="cat-grid">${Object.entries(CAT).map(([k, [t, d]]) => `<div class="cat ${k === S.category ? 'active' : ''}" data-cat="${k}" role="button" tabindex="0"><h3>${t}</h3><p>${d}</p>${S.availability?.[k] ? `<span class="tag ${S.availability[k].status === 'available' ? 'ok' : S.availability[k].status === 'not applicable' ? '' : 'warn'}">${S.availability[k].status}</span>` : ''}</div>`).join('')}</div>
    <div class="row" style="margin:12px 0"><label class="muted" style="flex:none">Period from</label><select id="start" style="flex:none">${[1981, 1991, 2000, 2010, 2015].map((y) => `<option ${y === S.startYear ? 'selected' : ''}>${y}</option>`).join('')}</select><span></span></div><div id="intel-out"></div>`;
  body.querySelectorAll('.cat').forEach((c) => c.onclick = () => { S.category = c.dataset.cat; renderIntel(); });
  body.querySelector('#start').onchange = (e) => { S.startYear = +e.target.value; S.inv = {}; renderIntel(); };
  const out = body.querySelector('#intel-out');
  const cat = S.category;
  if (cat === 'hazards') { out.innerHTML = '<div class="card">Hazard observations for this location are shown in <b>Live Monitor</b> with “near selected location” enabled (EONET events + USGS earthquakes for the last year; FIRMS fires when a key is set). <button class="btn small" id="go-live">Open Live Monitor</button></div>'; out.querySelector('#go-live').onclick = () => switchView('live'); return; }
  if (['vegetation', 'ocean', 'cryosphere'].includes(cat)) {
    const av = S.availability?.[cat];
    out.innerHTML = `<div class="card"><h3>${CAT[cat][0]} — ${av?.status || 'checking'}</h3><p>${esc(av?.connector || '')}</p><p class="muted">A numeric time-series connector for this category is pending: the underlying products (MODIS NDVI/LST via LP DAAC, OISST, NSIDC, ICESat-2) need an Earthdata login or large-file access, which is documented in README. Nothing is fabricated here; use the imagery layers on the globe and the CMR collections below.</p>
      ${(av?.cmr_examples || []).map((x) => `<div>· ${esc(x.title)} <span class="muted">${esc(x.id)}</span></div>`).join('')}<div class="row" style="margin-top:8px"><button class="btn small" id="go-ds">Open Dataset Explorer</button><button class="btn small" id="go-globe">View imagery on globe</button></div></div>`;
    out.querySelector('#go-ds').onclick = () => switchView('datasets'); out.querySelector('#go-globe').onclick = () => { const map = { vegetation: 'MODIS_Terra_NDVI_8Day', ocean: 'GHRSST_L4_MUR_Sea_Surface_Temperature', cryosphere: 'MODIS_Terra_Snow_Cover' }; switchView('explorer'); toggleLayer(map[cat], true); renderLayers(); };
    return;
  }
  out.innerHTML = '<div class="empty"><span class="spinner"></span>Retrieving NASA POWER monthly series and running the analysis engine…</div>';
  try {
    const r = await getInvestigation(cat);
    out.innerHTML = `<div class="muted" style="margin-bottom:8px">${esc(r.aggregation)} · ${esc(r.provenance.upstream)} · retrieved ${r.retrieved.slice(0, 16).replace('T', ' ')} UTC</div><div id="vars"></div>`;
    const vars = out.querySelector('#vars');
    for (const [v, x] of Object.entries(r.variables)) {
      const id = 'c_' + v;
      if (!x.available) { vars.insertAdjacentHTML('beforeend', `<div class="card"><h3>${esc(x.label)}</h3><p class="muted">Unavailable: ${esc(x.reason)}</p></div>`); continue; }
      const d = x.descriptive, cov = x.coverage, mk = x.trend_mk_seasonal, cp = x.change_point;
      vars.insertAdjacentHTML('beforeend', `<div class="card"><h3>${esc(x.label)} <span class="muted">${esc(x.unit)} · ${esc(x.product_id)} · ${esc(x.product_kind)}</span></h3>
        <div class="grid3"><dl class="kv"><dt>Period</dt><dd>${cov.start} – ${cov.end}</dd><dt>Missing</dt><dd>${cov.pct_missing}% (${cov.n_missing}/${cov.n_expected} months)</dd><dt>Mean</dt><dd>${fmt(d.mean)} ${esc(x.unit)}</dd><dt>Range</dt><dd>${fmt(d.min)} (${d.min_at}) – ${fmt(d.max)} (${d.max_at})</dd></dl>
        <dl class="kv"><dt>OLS trend</dt><dd>${trendTag(x.trend_ols, x.unit)}</dd><dt>95% CI</dt><dd>${x.trend_ols.available ? x.trend_ols.ci95_per_decade.map((c) => fmt(c, 3)).join(' to ') + ' /decade' : 'n/a'}</dd><dt>Mann-Kendall (seasonal)</dt><dd>${mk.available ? `${mk.trend} · p=${fmt(mk.p_value, 3)} · Sen ${fmt(mk.sen_slope_per_decade, 3)} /decade` : 'n/a'}</dd><dt>Change-point</dt><dd>${cp.available ? `${cp.change_point} (Pettitt p=${fmt(cp.p_value, 3)}${cp.significant_05 ? ', significant' : ''})` : 'n/a'}</dd></dl>
        <dl class="kv"><dt>Anomalies |z|≥2</dt><dd>${x.anomalies.n_flagged}</dd><dt>Largest</dt><dd>${x.anomalies.flagged.slice(0, 3).map((a) => `${a.t} ${a.anomaly > 0 ? '+' : ''}${fmt(a.anomaly)} (z ${fmt(a.z, 1)})`).join('<br>') || 'none'}</dd></dl></div>
        <div class="chart" id="${id}"></div></div>`);
      const s = x.series, a = x.anomalies.series, ann = x.annual.series;
      Plotly.newPlot(id, [
        { x: s.map((p) => p.t), y: s.map((p) => p.v), name: 'monthly', type: 'scatter', mode: 'lines', line: { color: 'rgba(46,230,255,.55)', width: 1 } },
        { x: ann.map((p) => p.t + '-07'), y: ann.map((p) => p.v), name: 'annual mean', mode: 'lines+markers', line: { color: '#ffb547', width: 2 } },
        { x: a.map((p) => p.t), y: a.map((p) => p.v), name: 'anomaly', type: 'bar', marker: { color: a.map((p) => (p.v ?? 0) > 0 ? 'rgba(255,90,95,.5)' : 'rgba(74,179,255,.5)') }, yaxis: 'y2' },
      ], { ...PLOT, yaxis: { ...PLOT.yaxis, title: x.unit }, yaxis2: { overlaying: 'y', side: 'right', showgrid: false, title: 'anomaly', zeroline: true, zerolinecolor: 'rgba(118,170,255,.3)' } }, PCFG);
    }
    vars.insertAdjacentHTML('beforeend', `<div class="card muted"><b>Provenance.</b> ${esc(r.sources.join('; '))}. Grid ${esc(r.provenance.grid)}, ${esc(r.provenance.temporal)}. ${esc(r.context.notes)}<br><b>Caveats.</b> ${Object.values(r.variables)[0]?.caveats?.map(esc).join(' ')}</div>`);
  } catch (e) { out.innerHTML = `<div class="empty">Could not retrieve data: ${esc(e.message)}</div>`; }
}

/* ── Trends & anomalies ── */
async function renderTrends() {
  if (needPlace()) return;
  const body = $('center-body');
  const vars = ['T2M', 'T2M_MAX', 'T2M_MIN', 'PRECTOTCORR', 'RH2M', 'WS2M', 'ALLSKY_SFC_SW_DWN', 'GWETROOT', 'TS'];
  body.innerHTML = `<div class="row" style="margin-bottom:10px"><select id="tv">${vars.map((v) => `<option value="${v}" ${v === (S.trendVar || 'T2M') ? 'selected' : ''}>${v}</option>`).join('')}</select><select id="ts">${[1981, 1991, 2000].map((y) => `<option ${y === (S.trendStart || 1981) ? 'selected' : ''}>${y}</option>`).join('')}</select><button class="btn primary" id="tgo" style="flex:none">Analyse</button></div><div id="tout"></div>`;
  const run = async () => {
    S.trendVar = body.querySelector('#tv').value; S.trendStart = +body.querySelector('#ts').value;
    const out = body.querySelector('#tout'); out.innerHTML = '<div class="empty"><span class="spinner"></span>Computing trends, anomalies, seasonal profile…</div>';
    try {
      const r = await getInvestigation('climate', [S.trendVar], S.trendStart); const x = r.variables[S.trendVar];
      if (!x.available) { out.innerHTML = `<div class="empty">${esc(x.reason)}</div>`; return; }
      const o = x.trend_ols, mk = x.trend_mk_seasonal, mka = x.trend_mk_annual, cp = x.change_point;
      out.innerHTML = `<div class="grid2"><div class="card"><h3>Trend — ${esc(x.label)}</h3><dl class="kv">
        <dt>OLS slope</dt><dd>${trendTag(o, x.unit)}</dd><dt>95% CI</dt><dd>${o.available ? o.ci95_per_decade.map((c) => fmt(c, 3)).join(' to ') : 'n/a'} ${esc(x.unit)}/decade</dd>
        <dt>Total change</dt><dd>${o.available ? fmt(o.total_change_over_record) + ' ' + esc(x.unit) + ' over ' + fmt(o.span_years, 0) + ' yr' : 'n/a'}${x.percent_change_over_record != null ? ` (${fmt(x.percent_change_over_record, 1)}%)` : ''}</dd>
        <dt>Lag-1 autocorr.</dt><dd>${o.available ? fmt(o.lag1_autocorrelation) + ' · n_eff ' + o.n_effective + ' of ' + o.n : 'n/a'}</dd>
        <dt>Seasonal MK</dt><dd>${mk.available ? `${mk.trend} (z ${fmt(mk.z)}, p ${fmt(mk.p_value, 3)}), Sen ${fmt(mk.sen_slope_per_decade, 3)}/decade` : 'n/a'}</dd>
        <dt>Annual MK</dt><dd>${mka.available ? `${mka.trend} (p ${fmt(mka.p_value, 3)})` : 'n/a'}</dd>
        <dt>Change-point</dt><dd>${cp.available ? `${cp.change_point}: ${fmt(cp.mean_before)} → ${fmt(cp.mean_after)} (p ${fmt(cp.p_value, 3)})` : esc(cp.reason)}</dd></dl>
        <p class="muted">${esc(o.method || '')}. ${esc(mk.method || '')}.</p></div>
        <div class="card"><h3>Coverage & baseline</h3><dl class="kv"><dt>Record</dt><dd>${x.coverage.start} – ${x.coverage.end}</dd><dt>Valid months</dt><dd>${x.coverage.n_valid} / ${x.coverage.n_expected}</dd><dt>Baseline</dt><dd>${x.climatology.baseline.join('–')} (record climatology)</dd><dt>Anomaly method</dt><dd>${esc(x.anomalies.method)}</dd><dt>Flagged |z|≥2</dt><dd>${x.anomalies.n_flagged} months</dd></dl></div></div>
        <div class="card"><h3>Annual means with OLS fit</h3><div class="chart" id="t-ann"></div></div>
        <div class="grid2"><div class="card"><h3>Monthly anomalies (z-score)</h3><div class="chart" id="t-an"></div></div><div class="card"><h3>Seasonal cycle: early vs last 10 years</h3><div class="chart" id="t-seas"></div></div></div>
        <div class="card"><h3>Anomaly heatmap (year × month)</h3><div class="chart" id="t-heat" style="height:320px"></div></div>`;
      const ann = x.annual.series, xs = ann.map((p) => +p.t);
      const fit = o.available ? xs.map((yr) => (o.slope_per_year * (yr + 0.5) + (ann.reduce((s, p) => s + p.v, 0) / ann.length - o.slope_per_year * (xs.reduce((s, v) => s + v + 0.5, 0) / xs.length)))) : [];
      Plotly.newPlot('t-ann', [{ x: xs, y: ann.map((p) => p.v), mode: 'lines+markers', name: 'annual mean', line: { color: '#2ee6ff' } }, { x: xs, y: fit, mode: 'lines', name: 'OLS fit', line: { color: '#ffb547', dash: 'dot' } }], { ...PLOT, yaxis: { ...PLOT.yaxis, title: x.unit } }, PCFG);
      const z = x.anomalies.series.map((p) => { const m = +p.t.slice(5, 7); const sd = x.climatology.monthly_std[m]; return p.v != null && sd ? p.v / sd : null; });
      Plotly.newPlot('t-an', [{ x: x.anomalies.series.map((p) => p.t), y: z, type: 'bar', marker: { color: z.map((v) => (v ?? 0) > 0 ? '#ff5a5f' : '#4ab3ff') } }], { ...PLOT, shapes: [2, -2].map((y) => ({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: y, y1: y, line: { color: 'rgba(255,181,71,.6)', dash: 'dot' } })) }, PCFG);
      const M = x.seasonal.months, mn = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
      Plotly.newPlot('t-seas', [{ x: mn, y: Object.values(M).map((m) => m.early_mean), name: `before ${x.seasonal.split_year}`, line: { color: '#8b6cff' } }, { x: mn, y: Object.values(M).map((m) => m.recent_mean), name: `since ${x.seasonal.split_year}`, line: { color: '#ff5a5f' } }], { ...PLOT, yaxis: { ...PLOT.yaxis, title: x.unit } }, PCFG);
      const years = [...new Set(x.series.map((p) => p.t.slice(0, 4)))], grid = years.map(() => Array(12).fill(null));
      x.anomalies.series.forEach((p) => { grid[years.indexOf(p.t.slice(0, 4))][+p.t.slice(5, 7) - 1] = p.v; });
      Plotly.newPlot('t-heat', [{ z: grid, x: mn, y: years, type: 'heatmap', colorscale: [[0, '#4ab3ff'], [0.5, '#0b1a2e'], [1, '#ff5a5f']], zmid: 0, colorbar: { title: x.unit } }], { ...PLOT, margin: { ...PLOT.margin, l: 48 } }, PCFG);
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };
  body.querySelector('#tgo').onclick = run; run();
}

/* ── AI investigation ── */
function mdToHtml(t) { return esc(t).replace(/^## (.*)$/gm, '<h2>$1</h2>').replace(/^### (.*)$/gm, '<h3>$1</h3>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/_(.+?)_/g, '<i>$1</i>').replace(/^- /gm, '• '); }
async function renderAI() {
  if (needPlace()) return;
  const body = $('center-body');
  body.innerHTML = `<div class="chat"><div class="muted" style="margin-bottom:8px">TerraTrend Intelligence answers only from statistics computed for <b>${esc(S.place.short_name || S.place.name)}</b> (NASA POWER, ${S.startYear}–now). Engine: ${S.config.ai_enabled ? 'Claude model' : 'rule-based (set ANTHROPIC_API_KEY for the model)'}.</div>
    <div class="log" id="ai-log">${S.aiLog.map((m) => `<div class="msg ${m.role}">${m.role === 'ai' ? mdToHtml(m.text) : esc(m.text)}</div>`).join('') || '<div class="empty">Ask: “Has temperature changed over the last 20 years?”, “How has rainfall varied?”, “Which variables show the strongest changes?”, “What datasets support this?”</div>'}</div>
    <div class="row" style="margin-top:8px"><select id="ai-cat" style="flex:none">${Object.keys(CAT).filter((k) => ['climate', 'water', 'energy', 'land', 'atmosphere'].includes(k)).map((k) => `<option value="${k}" ${k === S.category ? 'selected' : ''}>${CAT[k][0]}</option>`).join('')}</select><input id="ai-q" placeholder="Ask a question about this location…"><button class="btn primary" id="ai-go" style="flex:none">Ask</button></div></div>`;
  const ask = async () => {
    const q = body.querySelector('#ai-q').value.trim(); if (!q) return;
    const cat = body.querySelector('#ai-cat').value; body.querySelector('#ai-q').value = '';
    S.aiLog.push({ role: 'user', text: q }); const log = body.querySelector('#ai-log');
    log.innerHTML += `<div class="msg user">${esc(q)}</div><div class="msg ai" id="ai-wait"><span class="spinner"></span>Retrieving observations and computing evidence…</div>`; log.scrollTop = log.scrollHeight;
    try {
      const r = await post('/api/ai/interpret', { question: q, investigation: { place: S.place, category: cat, start_year: S.startYear } });
      const text = r.answer + `\n\n_Engine: ${r.engine} · evidence: ${Object.keys(r.evidence).length} variables, period ${r.period.join('–')}_`;
      S.aiLog.push({ role: 'ai', text }); body.querySelector('#ai-wait').innerHTML = mdToHtml(text);
    } catch (e) { body.querySelector('#ai-wait').innerHTML = 'Could not answer: ' + esc(e.message); }
    log.scrollTop = log.scrollHeight;
  };
  body.querySelector('#ai-go').onclick = ask; body.querySelector('#ai-q').onkeydown = (e) => { if (e.key === 'Enter') ask(); };
}

/* ── Regional comparison ── */
async function renderCompare() {
  const body = $('center-body');
  if (S.place && !S.compare.places.find((p) => p.name === S.place.name) && S.compare.places.length < 4) S.compare.places.push(S.place);
  body.innerHTML = `<div class="card"><h3>Regions</h3><div id="cmp-list">${S.compare.places.map((p, i) => `<span class="tag info">${esc(p.short_name || p.name)} <a href="#" data-rm="${i}">×</a></span>`).join('') || '<span class="muted">Add at least two regions.</span>'}</div>
    <div class="row" style="margin-top:8px"><div class="search" style="max-width:none"><input id="cmp-q" placeholder="Add a region by name…"><div id="cmp-res" class="results"></div></div>
    <select id="cmp-vars" multiple size="3" style="flex:none;width:240px"><option value="T2M" selected>T2M mean temperature</option><option value="PRECTOTCORR" selected>PRECTOTCORR precipitation</option><option value="T2M_MAX">T2M_MAX</option><option value="RH2M">RH2M humidity</option><option value="ALLSKY_SFC_SW_DWN">Solar radiation</option><option value="GWETROOT">Root-zone soil wetness</option></select>
    <button class="btn primary" id="cmp-go" style="flex:none" ${S.compare.places.length < 2 ? 'disabled' : ''}>Compare</button></div></div><div id="cmp-out"></div>`;
  body.querySelectorAll('[data-rm]').forEach((a) => a.onclick = (e) => { e.preventDefault(); S.compare.places.splice(+a.dataset.rm, 1); renderCompare(); });
  let t; body.querySelector('#cmp-q').oninput = (e) => { clearTimeout(t); const q = e.target.value.trim(); if (q.length < 2) return; t = setTimeout(async () => { const r = await api(`/api/locations/search?q=${encodeURIComponent(q)}`); const res = body.querySelector('#cmp-res'); res.innerHTML = r.results.map((p, i) => `<button data-i="${i}">${esc(p.short_name)} <small>${esc(p.name)}</small></button>`).join(''); res._items = r.results; res.classList.add('open'); }, 350); };
  body.querySelector('#cmp-res').onclick = (e) => { const b = e.target.closest('button'); if (!b) return; S.compare.places.push(body.querySelector('#cmp-res')._items[+b.dataset.i]); renderCompare(); };
  body.querySelector('#cmp-go').onclick = async () => {
    const vars = [...body.querySelector('#cmp-vars').selectedOptions].map((o) => o.value); const out = body.querySelector('#cmp-out');
    out.innerHTML = '<div class="empty"><span class="spinner"></span>Retrieving all regions and comparing…</div>';
    try {
      const r = await post('/api/comparison', { places: S.compare.places, variables: vars, start_year: S.startYear }); S.compare.results = r;
      out.innerHTML = (r.opposite_trends.length ? `<div class="card" style="border-color:var(--amber)"><h3>Opposite trends detected</h3>${r.opposite_trends.map((p) => `<div>${esc(p.variable)}: <b>${esc(p.a)}</b> ${fmt(p.trend_A_per_decade, 3)}/decade vs <b>${esc(p.b)}</b> ${fmt(p.trend_B_per_decade, 3)}/decade (both p&lt;0.05). ${esc(p.note)}</div>`).join('')}</div>` : '<div class="muted" style="margin-bottom:8px">No statistically significant opposite trends between these regions.</div>')
        + `<table><tr><th>Region</th>${vars.map((v) => `<th>${v} mean</th><th>${v} trend/decade</th>`).join('')}</tr>${r.regions.map((g) => `<tr><td>${esc(g.context.short_name || g.context.name)}<br><small class="muted">${esc(g.aggregation)}</small></td>${vars.map((v) => { const x = g.variables[v]; return x?.available ? `<td>${fmt(x.descriptive.mean)} ${esc(x.unit)}</td><td>${trendTag(x.trend_ols, x.unit)}</td>` : '<td colspan=2>n/a</td>'; }).join('')}</tr>`).join('')}</table>
        <table style="margin-top:10px"><tr><th>Pair</th><th>Variable</th><th>Mean diff (A−B)</th><th>Paired test</th><th>Common months</th></tr>${r.pairs.map((p) => `<tr><td>${esc(p.a)} vs ${esc(p.b)}</td><td>${p.variable}</td><td>${fmt(p.mean_difference_A_minus_B)}</td><td>${p.difference_test ? `t=${fmt(p.difference_test.t, 1)}, p=${fmt(p.difference_test.p_value, 4)}` : 'n/a'}</td><td>${p.difference_test?.n_common_months ?? 'n/a'}</td></tr>`).join('')}</table>
        <p class="muted">${esc(r.note)} Paired-test p-values are inflated by autocorrelation; treat them as indicative.</p>${vars.map((v) => `<div class="card"><h3>${v} annual means</h3><div class="chart" id="cmp-${v}"></div></div>`).join('')}`;
      const cols = ['#2ee6ff', '#ffb547', '#8b6cff', '#4ade80'];
      vars.forEach((v) => Plotly.newPlot('cmp-' + v, r.regions.map((g, i) => ({ x: g.variables[v]?.annual.series.map((p) => +p.t) || [], y: g.variables[v]?.annual.series.map((p) => p.v) || [], name: g.context.short_name || g.context.name, mode: 'lines+markers', line: { color: cols[i] } })), { ...PLOT, yaxis: { ...PLOT.yaxis, title: r.regions[0].variables[v]?.unit } }, PCFG));
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };
}

/* ── Dataset explorer ── */
async function renderDatasets() {
  if (needPlace()) return;
  const body = $('center-body');
  body.innerHTML = `<div class="row" style="margin-bottom:10px"><input id="ds-q" placeholder="Keyword (e.g. NDVI, soil moisture, sea surface temperature)"><select id="ds-cat" style="flex:none"><option value="">Any category</option>${Object.keys(CAT).map((k) => `<option value="${k}">${CAT[k][0]}</option>`).join('')}</select><input id="ds-prov" placeholder="Provider (e.g. LPDAAC_ECS, GES_DISC, POCLOUD)" style="flex:none;width:200px"><button class="btn primary" id="ds-go" style="flex:none">Search CMR</button></div><div class="muted" style="margin-bottom:8px">NASA CMR collections intersecting ${esc(S.place.short_name || S.place.name)} that have granules. Click a row for full metadata and a granule check.</div><div id="ds-out"></div>`;
  const run = async (page = 1) => {
    const out = body.querySelector('#ds-out'); out.innerHTML = '<div class="empty"><span class="spinner"></span>Searching NASA CMR…</div>';
    try {
      const q = new URLSearchParams({ bbox: S.place.bbox.join(','), q: body.querySelector('#ds-q').value, category: body.querySelector('#ds-cat').value, page, page_size: 15 });
      const prov = body.querySelector('#ds-prov').value.trim(); if (prov) q.set('provider', prov);
      const r = await api('/api/datasets/search?' + q);
      out.innerHTML = `<div class="muted">${r.hits} collections · page ${r.page}</div><table><tr><th>Short name</th><th>Title</th><th>Provider</th><th>Platforms / instruments</th><th>Coverage</th></tr>${r.items.map((c, i) => `<tr class="event" data-i="${i}"><td>${esc(c.short_name)} v${esc(c.version)}</td><td>${esc(c.title)}</td><td>${esc(c.provider)}</td><td>${esc([...new Set(c.platforms)].join(', '))}<br><small class="muted">${esc([...new Set(c.instruments)].join(', '))}</small></td><td>${esc((c.time_start || '').slice(0, 10))} → ${esc((c.time_end || 'present').slice(0, 10))}</td></tr>`).join('')}</table>
        <div class="row" style="margin-top:8px"><button class="btn small" id="ds-prev" ${page <= 1 ? 'disabled' : ''}>Previous</button><button class="btn small" id="ds-next" ${page * 15 >= r.hits ? 'disabled' : ''}>Next</button></div><div id="ds-detail"></div>`;
      out.querySelector('#ds-prev').onclick = () => run(page - 1); out.querySelector('#ds-next').onclick = () => run(page + 1);
      out.querySelectorAll('tr.event').forEach((tr) => tr.onclick = async () => {
        const c = r.items[+tr.dataset.i]; const d = out.querySelector('#ds-detail'); d.innerHTML = '<div class="card"><span class="spinner"></span>Loading collection metadata…</div>';
        try {
          const m = await api(`/api/datasets/${c.id}?bbox=${S.place.bbox.join(',')}`); const col = m.collection;
          d.innerHTML = `<div class="card"><h3>${esc(col.title)}</h3><dl class="kv"><dt>Concept ID</dt><dd>${esc(col.id)}</dd><dt>Short name / version</dt><dd>${esc(col.short_name)} / ${esc(col.version_id)}</dd><dt>Provider</dt><dd>${esc(col.data_center)}</dd><dt>Processing level</dt><dd>${esc(col.processing_level_id || 'n/a')}</dd><dt>Temporal</dt><dd>${esc(col.time_start)} → ${esc(col.time_end || 'ongoing')}</dd><dt>Spatial boxes</dt><dd>${esc((col.boxes || []).join(' | ') || 'n/a')}</dd><dt>Updated</dt><dd>${esc(col.updated)}</dd><dt>Granules here (sample)</dt><dd>${m.granules_in_bbox_sample == null ? 'check failed' : m.granules_in_bbox_sample > 0 ? 'yes — granules intersect this bbox' : 'none found'}</dd><dt>Access</dt><dd>${col.online_access_flag ? 'online' : 'offline/ordered'}${col.cloud_hosted ? ' · cloud-hosted' : ''} · Earthdata login usually required for download</dd></dl>
            <p>${esc(col.summary || '')}</p><div>${(col.links || []).filter((l) => l.href?.startsWith('http')).slice(0, 8).map((l) => `<a href="${esc(l.href)}" target="_blank" rel="noopener" class="tag info">${esc((l.rel || '').split('/').pop() || 'link')}</a>`).join(' ')}</div></div>`;
        } catch (e) { d.innerHTML = `<div class="card">Metadata unavailable: ${esc(e.message)}</div>`; }
        d.scrollIntoView({ behavior: 'smooth' });
      });
    } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };
  body.querySelector('#ds-go').onclick = () => run(1); body.querySelector('#ds-q').onkeydown = (e) => { if (e.key === 'Enter') run(1); }; run(1);
}

/* ── Reports ── */
async function renderReports() {
  if (needPlace()) return;
  const body = $('center-body');
  body.innerHTML = `<div class="card"><h3>Generate an investigation report for ${esc(S.place.short_name || S.place.name)}</h3><div class="row"><select id="rp-cat" style="flex:none">${['climate', 'water', 'energy', 'land', 'atmosphere'].map((k) => `<option value="${k}" ${k === S.category ? 'selected' : ''}>${CAT[k][0]}</option>`).join('')}</select><input id="rp-title" placeholder="Report title (optional)"><label class="layer" style="border:0;flex:none"><input type="checkbox" id="rp-ai" checked> include interpretation</label><button class="btn primary" id="rp-go" style="flex:none">Generate PDF, CSV, JSON, GeoJSON</button></div><p class="muted">Reports contain location geometry, variables, period, datasets, coverage, statistics, anomalies, interpretation, limitations, methodology and references — enough to reproduce the numbers.</p></div>
    <div id="rp-list">${S.reports.map(reportCard).join('') || '<div class="empty">No reports generated yet in this session.</div>'}</div>
    <div class="card" id="rp-fresh"><h3>Data freshness</h3><span class="spinner"></span></div>`;
  body.querySelector('#rp-go').onclick = async () => {
    const b = body.querySelector('#rp-go'); b.disabled = true; b.textContent = 'Generating…';
    try {
      const r = await post('/api/reports/generate', { investigation: { place: S.place, category: body.querySelector('#rp-cat').value, start_year: S.startYear }, title: body.querySelector('#rp-title').value || null, include_ai: body.querySelector('#rp-ai').checked });
      S.reports.unshift(r); body.querySelector('#rp-list').innerHTML = S.reports.map(reportCard).join(''); toast('Report generated');
    } catch (e) { toast('Report failed: ' + e.message, 6000); }
    b.disabled = false; b.textContent = 'Generate PDF, CSV, JSON, GeoJSON';
  };
  try {
    const f = await api('/api/system/data-freshness');
    body.querySelector('#rp-fresh').innerHTML = `<h3>Data freshness <span class="muted">${f.generated.slice(0, 16).replace('T', ' ')} UTC</span></h3><table><tr><th>Source</th><th>Product</th><th>Cadence</th><th>Auth</th><th>Status</th><th>Latest observation</th><th>Last success</th></tr>${f.sources.map((s) => `<tr><td>${esc(s.name)}</td><td>${esc(s.product)}</td><td>${esc(s.cadence)}</td><td>${esc(s.auth)}</td><td><span class="tag ${/recently/.test(s.status) ? 'ok' : /pending|unavailable/.test(s.status) ? 'warn' : ''}">${esc(s.status)}</span>${s.error ? `<br><small class="muted">${esc(s.error)}</small>` : ''}</td><td>${esc((s.latest_observation || '').slice(0, 16))}</td><td>${esc((s.last_success || '').slice(0, 16).replace('T', ' '))}</td></tr>`).join('')}</table>`;
  } catch { body.querySelector('#rp-fresh').innerHTML = '<h3>Data freshness</h3><span class="muted">unavailable</span>'; }
}
const reportCard = (r) => `<div class="card"><h3>${esc(r.title)}</h3><div class="muted">${esc(r.report_id)} · ${esc(r.created.slice(0, 16).replace('T', ' '))} UTC</div><div style="margin-top:6px">${Object.entries(r.files).map(([k, u]) => `<a class="btn small" href="${u}" target="_blank" rel="noopener" style="display:inline-block;margin-right:6px;line-height:26px">${k.toUpperCase()}</a>`).join('')}</div></div>`;

/* ───────────────────────── boot ───────────────────────── */
(async function boot() {
  try {
    const [cfg, layers, health] = await Promise.all([api('/api/system/config'), api('/api/layers'), api('/api/health')]);
    S.config = cfg; S.layers = layers.gibs;
    $('aiflag').innerHTML = `<span class="dot ${cfg.ai_enabled ? '' : 'warn'}"></span>${cfg.ai_enabled ? 'AI: Claude' : 'AI: rule-based'}`;
    $('fresh').innerHTML = `<span class="dot"></span>backend ${health.version}`;
    $('tdate').textContent = ymd(S.date); $('tslider').value = sliderFromDate(S.date);
    initGlobe(); renderLayers(); renderLocationPanel();
    setInterval(async () => { try { const f = await api('/api/system/data-freshness'); const bad = f.sources.filter((s) => /unavailable/.test(s.status)).length; $('fresh').innerHTML = `<span class="dot ${bad ? 'warn' : ''}"></span>${bad ? bad + ' source(s) unavailable' : 'sources healthy'}`; } catch { $('fresh').innerHTML = '<span class="dot off"></span>backend offline'; } }, 60000);
  } catch (e) { document.body.insertAdjacentHTML('beforeend', `<div class="empty" style="position:fixed;inset:0;z-index:99;display:grid;place-items:center">Backend not reachable: ${esc(e.message)}. Start it with run.sh / run.bat.</div>`); }
})();