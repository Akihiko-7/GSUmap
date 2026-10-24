// The map tab: MapLibre with OpenFreeMap tiles (or an offline campus map), place markers, the details sheet, GPS dot and route line.
import { S, CATS, actions, colorFor, iconFor, esc, toast } from './state.js';
import { t } from './i18n.js';

export let map;
const markers = new Map(); // id -> { marker, el }
let filter = 'all';
let selected = null;
let meMarker = null;
let pickHandler = null;

const ONLINE_STYLE = 'https://tiles.openfreemap.org/styles/liberty';
const OFFLINE_STYLE = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef1ea' } }] };

async function pickStyle() {
  // OpenFreeMap when the network is there; otherwise our own campus map, so the map is never blank
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 4000);
    const res = await fetch(ONLINE_STYLE, { signal: ctl.signal });
    clearTimeout(timer);
    if (res.ok) {
      const style = await res.json();
      // our markers carry the corrected campus names; the tiles' own place labels would contradict them
      style.layers = style.layers.filter((l) => !l.id.startsWith('poi'));
      return { style, online: true };
    }
  } catch {}
  return { style: OFFLINE_STYLE, online: false };
}

export async function initMap() {
  const { style, online } = await pickStyle();
  const c = S.config.center;
  map = new maplibregl.Map({
    container: 'map', style, center: [c.lng, c.lat], zoom: 15.6, minZoom: 12, maxZoom: 19.5,
    attributionControl: { compact: true, customAttribution: '© OpenStreetMap contributors' },
  });
  window.gsuMap = map; // handy in the browser console and for the smoke test
  map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: false }), 'bottom-left');
  await new Promise((r) => map.on('load', r));
  await addCampusLayers(online);
  addMarkers();
  map.on('zoom', labels);
  labels();
  map.on('click', (e) => {
    if (pickHandler) { const h = pickHandler; pickHandler = null; h(e.lngLat); }
  });
  buildChips();
  if (!online) toast(t('offline'));
}

async function addCampusLayers(online) {
  const [boundary, paths, buildings] = await Promise.all(['boundary', 'paths', 'buildings'].map((n) => fetch(`/api/geo/${n}`).then((r) => r.json()).catch(() => null)));
  if (boundary) {
    map.addSource('campus', { type: 'geojson', data: boundary });
    if (!online) map.addLayer({ id: 'campus-fill', type: 'fill', source: 'campus', paint: { 'fill-color': '#dcefd8' } });
    map.addLayer({ id: 'campus-line', type: 'line', source: 'campus', paint: { 'line-color': '#0b5d2a', 'line-width': 2.5, 'line-dasharray': [3, 2] } });
  }
  if (!online && buildings) {
    map.addSource('buildings', { type: 'geojson', data: buildings });
    map.addLayer({ id: 'buildings', type: 'fill', source: 'buildings', paint: { 'fill-color': '#c9a27e', 'fill-outline-color': '#9c7856' } });
  }
  if (!online && paths) {
    map.addSource('paths', { type: 'geojson', data: paths });
    map.addLayer({ id: 'paths', type: 'line', source: 'paths', paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1.5, 18, 6] } }, 'buildings');
  }
  map.addSource('route', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 10 } });
  map.addLayer({ id: 'route', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#1a73e8', 'line-width': 6 } });
}

function labels() {
  document.getElementById('map').classList.toggle('show-labels', map.getZoom() >= 17.2);
}

export function addMarkers() {
  markers.forEach(({ marker }) => marker.remove());
  markers.clear();
  for (const p of S.places) {
    const el = document.createElement('div');
    el.className = 'mk-wrap';
    el.innerHTML = `<div class="mk" style="background:${colorFor(p)}"><i>${iconFor(p)}</i></div><span class="mk-label">${esc(p.name)}</span>`;
    el.addEventListener('click', (e) => { e.stopPropagation(); actions.showPlace(p.id); });
    const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lng, p.lat]).addTo(map);
    markers.set(p.id, { marker, el });
  }
  applyFilter();
}

function buildChips() {
  const box = document.getElementById('chips');
  const cats = ['all', ...Object.keys(CATS).filter((c) => S.places.some((p) => p.category === c))];
  box.innerHTML = cats.map((c) => `<button class="chip${c === filter ? ' on' : ''}" data-cat="${c}">${c === 'all' ? '' : `<span class="dot" style="background:${CATS[c].color}"></span>`}<span data-i18n="cat_${c}">${esc(t('cat_' + c))}</span></button>`).join('');
  box.onclick = (e) => {
    const b = e.target.closest('[data-cat]');
    if (!b) return;
    filter = b.dataset.cat;
    box.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === b));
    applyFilter();
  };
}

function applyFilter() {
  for (const [id, { el }] of markers) {
    const p = S.byId.get(id);
    el.style.display = filter === 'all' || p.category === filter || id === selected ? '' : 'none';
  }
}

export function selectPlace(id, fly = true) {
  if (selected) markers.get(selected)?.el.classList.remove('sel');
  selected = id;
  const m = markers.get(id);
  if (m) m.el.classList.add('sel');
  applyFilter();
  const p = S.byId.get(id);
  if (p && fly) map.flyTo({ center: [p.lng, p.lat], zoom: Math.max(map.getZoom(), 17), offset: [0, -120], duration: 700 });
}

export function openSheet(p) {
  const photos = document.getElementById('sheet-photo');
  photos.innerHTML = (p.reference_photos || []).map((ph) => `<img src="/${esc(ph)}" alt="" loading="lazy">`).join('');
  const cat = document.getElementById('sheet-cat');
  cat.textContent = t('cat_' + p.category);
  cat.style.background = colorFor(p);
  document.getElementById('sheet-name').textContent = p.name;
  document.getElementById('sheet-aliases').textContent = (p.aliases || []).slice(0, 5).join(' · ');
  document.getElementById('sheet-desc').textContent = p.description || '';
  document.getElementById('sheet-hours').textContent = p.opening_hours || '-';
  document.getElementById('sheet-approx').hidden = !p.approximate;
  document.getElementById('sheet-go').onclick = () => actions.startRoute(p.id);
  document.getElementById('route').hidden = true;
  document.getElementById('sheet').hidden = false;
  document.getElementById('sheet').scrollTop = 0;
}

export function closeSheet() {
  document.getElementById('sheet').hidden = true;
}

export function showMe(pos) {
  if (!map) return;
  if (!meMarker) {
    const el = document.createElement('div');
    el.className = 'me';
    el.title = t('you_are_here');
    meMarker = new maplibregl.Marker({ element: el }).setLngLat([pos.lng, pos.lat]).addTo(map);
  } else meMarker.setLngLat([pos.lng, pos.lat]);
}

export function drawRoute(coords, bottom = 0) {
  const src = map.getSource('route');
  src.setData(coords ? { type: 'Feature', geometry: { type: 'LineString', coordinates: coords } } : { type: 'FeatureCollection', features: [] });
  if (coords && coords.length > 1) {
    const b = coords.reduce((bb, c) => bb.extend(c), new maplibregl.LngLatBounds(coords[0], coords[0]));
    // cameraForBounds, not fitBounds: padding passed to fitBounds stays on the map and leaves tiles at the top unloaded
    const cam = map.cameraForBounds(b, { padding: { top: 64, left: 36, right: 36, bottom: bottom + 24 }, maxZoom: 18 });
    if (cam) map.easeTo({ center: cam.center, zoom: cam.zoom, bearing: 0, duration: 700 });
  }
}

export function pickOnMap(handler) {
  pickHandler = handler;
}
