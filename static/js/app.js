// Start-up, tabs, language, GPS and the route panel.
import { S, actions, setPlaces, distM, fmtDist, walkMin, esc, toast } from './state.js';
import { t, lang, loadI18n, applyI18n, setLang } from './i18n.js';
import { api } from './api.js';
import { initMap, map, addMarkers, selectPlace, openSheet, closeSheet, showMe, drawRoute } from './map.js';
import { loadGraph, planRoute } from './route.js';
import { initSearch } from './search.js';
import { initLens } from './lens.js';
import { initGonaDoc } from './gonadoc.js';
import { initAdmin } from './admin.js';

const $ = (id) => document.getElementById(id);
let current = null; // { dest, from, steps, original }

// ---------------------------------------------------------------- tabs
function showView(name) {
  document.querySelectorAll('#nav button').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  for (const v of ['search', 'lens', 'gonadoc']) $('view-' + v).hidden = v !== name;
  $('view-admin').hidden = true;
  if (name === 'search') setTimeout(() => $('search-input').focus(), 50);
  if (name === 'map' && map) map.resize();
}

actions.showPlace = (id) => {
  const p = S.byId.get(id);
  if (!p) return;
  showView('map');
  selectPlace(id);
  openSheet(p);
  S.openPlace = id;
};

actions.reloadPlaces = async () => {
  setPlaces(await api('/api/places'));
  addMarkers();
};

// ---------------------------------------------------------------- GPS
function startGps() {
  if (S.demo && S.config.demo_gps) {
    S.gps = { ...S.config.demo_gps, acc: 10, fake: true };
    showMe(S.gps);
    return;
  }
  if (!navigator.geolocation) { S.gpsNote = 'no_gps'; return; }
  if (!window.isSecureContext) { S.gpsNote = 'gps_insecure'; return; }
  navigator.geolocation.watchPosition(
    (p) => {
      const first = !S.gps;
      S.gps = { lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy };
      showMe(S.gps);
      if (first && distM(S.gps, S.config.center) < 2500) map.easeTo({ center: [S.gps.lng, S.gps.lat], zoom: 17 });
    },
    () => { S.gpsNote = 'no_gps'; },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
  );
}

// ---------------------------------------------------------------- directions
function startOptions(selectedId) {
  const sel = $('route-from');
  const gates = S.places.filter((p) => p.category === 'gate');
  const rest = S.places.filter((p) => p.category !== 'gate').sort((a, b) => a.name.localeCompare(b.name));
  sel.innerHTML = (S.gps ? `<option value="gps">${esc(t('route_my_location'))}</option>` : '') +
    [...gates, ...rest].map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  sel.value = selectedId;
}

function fromChoice(choice) {
  if (choice === 'gps' && S.gps) return { lat: S.gps.lat, lng: S.gps.lng, name: t('route_my_location'), id: 'gps' };
  const p = S.byId.get(choice) || S.byId.get('main-gate');
  return { lat: p.lat, lng: p.lng, name: p.name, id: p.id };
}

function renderRoute() {
  const { dest, from } = current;
  const r = planRoute(from, dest, fmtDist);
  current.steps = r.steps;
  current.original = r.steps;
  $('route-dest').textContent = dest.name;
  $('route-dist').textContent = fmtDist(r.dist);
  $('route-time').textContent = `${walkMin(r.dist)} ${t('min')} ${t('route_walk')}`;
  const notes = [];
  if (r.straight) notes.push(t('route_straight'));
  if (current.note) notes.push(t(current.note));
  $('route-note').hidden = !notes.length;
  $('route-note').textContent = notes.join(' ');
  paintSteps(r.steps);
  // Hausa steps come from our own templates: Gemma 4's rewrites of them were garbled in testing, so the button is English only
  $('route-friendly').hidden = !S.config.ai || lang === 'ha';
  $('route').scrollTop = 0;
  drawRoute(r.coords, $('route').offsetHeight);
}

function paintSteps(steps) {
  $('route-steps').innerHTML = steps.map((s) => `<li>${esc(s)}</li>`).join('');
}

actions.startRoute = (id) => {
  const dest = S.byId.get(id);
  if (!dest) return;
  showView('map');
  closeSheet();
  selectPlace(id, false);
  let choice = 'main-gate', note = '';
  if (S.gps && distM(S.gps, S.config.center) < 2000) choice = 'gps';
  else if (S.gps) note = 'gps_far';
  else note = S.gpsNote || 'no_gps';
  if (choice === 'main-gate' && id === 'main-gate') choice = 'gate-3';
  current = { dest, from: fromChoice(choice), note };
  startOptions(choice);
  $('route').hidden = false;
  renderRoute();
};

function initRoutePanel() {
  $('route-from').addEventListener('change', (e) => {
    current.from = fromChoice(e.target.value);
    current.note = '';
    renderRoute();
  });
  $('route-close').addEventListener('click', () => {
    $('route').hidden = true;
    drawRoute(null);
    current = null;
  });
  $('route-friendly').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = t('route_friendly_busy');
    try {
      const r = await api('/api/directions/rewrite', { json: { steps: current.original, destination: current.dest.name, lang }, timeout: 40000 });
      if (r.source === 'ai') paintSteps(r.steps);
      else toast(r.error || t('error'));
    } catch (err) {
      toast(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = t('route_friendly');
    }
  });
}

// ---------------------------------------------------------------- start
async function boot() {
  await loadI18n();
  applyI18n();
  $('lang-btn').textContent = lang === 'en' ? 'HA' : 'EN';
  const [config, places, intents] = await Promise.all([api('/api/config'), api('/api/places'), api('/api/intents').catch(() => [])]);
  S.config = config;
  S.intents = intents;
  setPlaces(places);
  if (S.demo) $('demo-badge').hidden = false;

  document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => { $(b.dataset.close).hidden = true; }));
  $('nav').addEventListener('click', (e) => { const b = e.target.closest('[data-view]'); if (b) showView(b.dataset.view); });
  $('lang-btn').addEventListener('click', () => {
    setLang(lang === 'en' ? 'ha' : 'en');
    $('lang-btn').textContent = lang === 'en' ? 'HA' : 'EN';
    document.dispatchEvent(new Event('langchange'));
    if (current && !$('route').hidden) renderRoute();
    if (!$('sheet').hidden && S.byId.get(S.openPlace)) openSheet(S.byId.get(S.openPlace));
  });
  $('locate-btn').addEventListener('click', () => {
    if (S.gps) map.flyTo({ center: [S.gps.lng, S.gps.lat], zoom: 17.5 });
    else toast(t(S.gpsNote || 'locating'));
  });

  initSearch();
  initLens();
  initGonaDoc();
  initAdmin();
  initRoutePanel();
  await Promise.all([initMap(), loadGraph().catch(() => {})]);
  startGps();

  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
  window.addEventListener('offline', () => toast(t('offline')));
}

boot().catch((e) => {
  console.error(e);
  toast(t('error'), 8000);
});
