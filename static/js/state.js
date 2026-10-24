// Shared state and small helpers used by every tab.
import { t } from './i18n.js';

export const S = {
  places: [],
  byId: new Map(),
  config: {},
  intents: [],
  demo: location.pathname.startsWith('/demo'),
  gps: null, // { lat, lng, acc, fake }
  gpsNote: '',
};

// filled in by app.js so modules can call each other without importing in circles
export const actions = {};

export const CATS = {
  faculty: { color: '#6a1b9a', icon: '🎓' },
  lecture_hall: { color: '#1565c0', icon: '📚' },
  hostel: { color: '#ef6c00', icon: '🛏' },
  admin: { color: '#0b5d2a', icon: '🏛' },
  bank: { color: '#00897b', icon: '🏧' },
  clinic: { color: '#c62828', icon: '✚' },
  cafeteria: { color: '#c77c02', icon: '🍲' },
  worship: { color: '#5d4037', icon: '🕌' },
  sports: { color: '#2e7d32', icon: '⚽' },
  gate: { color: '#455a64', icon: '🚪' },
  landmark: { color: '#8d6e63', icon: '📍' },
};

export function iconFor(p) {
  if (p.category === 'worship' && /chapel|church|catholic/i.test(p.name)) return '⛪';
  return (CATS[p.category] || CATS.landmark).icon;
}

export const colorFor = (p) => (CATS[p.category] || CATS.landmark).color;

export function setPlaces(list) {
  S.places = list;
  S.byId = new Map(list.map((p) => [p.id, p]));
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function distM(a, b) {
  const R = 6371000, r = Math.PI / 180;
  const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function fmtDist(m) {
  if (m < 1000) return `${Math.max(10, Math.round(m / 10) * 10)} ${t('m')}`;
  return `${(m / 1000).toFixed(1)} ${t('km')}`;
}

export const walkMin = (m) => Math.max(1, Math.ceil(m / 1.3 / 60));

let toastTimer;
export function toast(msg, ms = 3200) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

export function status(el, msg, kind = '') {
  el.className = 'status' + (kind === 'err' ? ' err' : '');
  el.innerHTML = msg ? (kind === 'busy' ? '<span class="spin"></span>' : '') + `<span>${esc(msg)}</span>` : '';
}

export function placeRow(p, extra = '') {
  const ph = p.reference_photos?.[0];
  const img = ph ? `<img src="/${esc(ph)}" alt="" loading="lazy">` : `<span class="ph" style="background:${colorFor(p)}">${iconFor(p)}</span>`;
  return `<button class="place-row" data-place="${esc(p.id)}">${img}<span><b>${esc(p.name)}</b><span class="small muted">${esc(t('cat_' + p.category))}${extra}</span></span></button>`;
}
