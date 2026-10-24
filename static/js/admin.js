// Admin mode: stand at a building, take its position and 1 to 3 photos, save it to places.json. Behind the PIN in .env.
import { S, CATS, actions, esc, toast } from './state.js';
import { t } from './i18n.js';
import { api } from './api.js';
import { compress } from './img.js';
import { pickOnMap } from './map.js';

const $ = (id) => document.getElementById(id);
let pin = '';
try { pin = sessionStorage.getItem('pin') || ''; } catch {}
let photos = [];

function unlocked() {
  $('admin-pin-form').hidden = true;
  $('admin-form').hidden = false;
  $('admin-existing').innerHTML = `<option value="">${esc(t('admin_new'))}</option>` +
    [...S.places].sort((a, b) => a.name.localeCompare(b.name)).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('admin-category').innerHTML = Object.keys(CATS).map((c) => `<option value="${c}">${esc(t('cat_' + c))}</option>`).join('');
}

function setPoint(lat, lng, acc) {
  $('admin-lat').value = lat.toFixed(6);
  $('admin-lng').value = lng.toFixed(6);
  $('admin-acc').textContent = acc ? `± ${Math.round(acc)} m ${t('admin_accuracy')}` : '';
}

export function openAdmin() {
  $('view-admin').hidden = false;
  if (pin) unlocked();
}

export function initAdmin() {
  if (!S.config.admin) return;
  $('admin-btn').hidden = false;
  $('admin-btn').addEventListener('click', openAdmin);
  $('admin-pin-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const val = $('admin-pin').value.trim();
    try {
      await api('/api/admin/verify', { json: { pin: val } });
      pin = val;
      try { sessionStorage.setItem('pin', val); } catch {}
      unlocked();
    } catch {
      toast(t('admin_bad_pin'));
    }
  });
  $('admin-existing').addEventListener('change', (e) => {
    const p = S.byId.get(e.target.value);
    if (!p) return;
    setPoint(p.lat, p.lng);
    $('admin-name').value = p.name;
    $('admin-aliases').value = (p.aliases || []).join(', ');
    $('admin-category').value = p.category;
    $('admin-desc').value = p.description || '';
    $('admin-hours').value = p.opening_hours || '';
  });
  $('admin-loc').addEventListener('click', () => {
    if (!navigator.geolocation || !window.isSecureContext) {
      if (S.gps) setPoint(S.gps.lat, S.gps.lng, S.gps.acc);
      else toast(t('gps_insecure'));
      return;
    }
    toast(t('locating'));
    navigator.geolocation.getCurrentPosition(
      (p) => setPoint(p.coords.latitude, p.coords.longitude, p.coords.accuracy),
      () => toast(t('no_gps')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
  // "Or tap the map": hide the form, take the next tap on the map, bring the form back
  const tap = document.querySelector('#view-admin [data-i18n="admin_tap_map"]');
  tap.style.textDecoration = 'underline';
  tap.style.cursor = 'pointer';
  tap.addEventListener('click', () => {
    $('view-admin').hidden = true;
    toast(t('admin_tap_map'));
    pickOnMap((ll) => { setPoint(ll.lat, ll.lng); $('view-admin').hidden = false; });
  });
  $('admin-photos').addEventListener('change', async (e) => {
    photos = [];
    $('admin-preview').innerHTML = '';
    for (const f of [...e.target.files].slice(0, 3)) {
      const b = await compress(f);
      photos.push(b);
      const img = document.createElement('img');
      img.src = URL.createObjectURL(b);
      $('admin-preview').appendChild(img);
    }
  });
  $('admin-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    form.append('pin', pin);
    photos.forEach((b, i) => form.append('photos', b, `photo${i}.jpg`));
    const btn = e.target.querySelector('button.big');
    btn.disabled = true;
    try {
      const saved = await api('/api/admin/place', { form, timeout: 60000 });
      toast(t('admin_saved'));
      await actions.reloadPlaces();
      e.target.reset();
      photos = [];
      $('admin-preview').innerHTML = '';
      $('admin-acc').textContent = '';
      $('view-admin').hidden = true;
      actions.showPlace(saved.id);
    } catch (err) {
      if (/PIN/i.test(err.message)) { pin = ''; try { sessionStorage.removeItem('pin'); } catch {} }
      toast(err.message);
    } finally {
      btn.disabled = false;
    }
  });
}
