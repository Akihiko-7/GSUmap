// Lens: photograph a building, the server compares it with reference photos of places within ~250 m.
import { S, actions, esc, placeRow, status } from './state.js';
import { t, lang } from './i18n.js';
import { api } from './api.js';
import { compress, showPreview } from './img.js';

const $ = (id) => document.getElementById(id);

async function identify(blob, pos) {
  const st = $('lens-status'), out = $('lens-result');
  out.innerHTML = '';
  showPreview($('lens-preview'), blob);
  status(st, t('lens_busy'), 'busy');
  const form = new FormData();
  form.append('photo', blob, 'photo.jpg');
  if (pos) { form.append('lat', pos.lat); form.append('lng', pos.lng); }
  form.append('lang', lang);
  try {
    render(await api('/api/identify', { form, timeout: 60000 }));
    st.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    status(st, e.message, 'err');
  }
}

function render(r) {
  const st = $('lens-status'), out = $('lens-result');
  const p = S.byId.get(r.place_id);
  if (p && r.confidence >= 0.6) {
    status(st, '');
    const pct = Math.round(r.confidence * 100);
    const photo = p.reference_photos?.[0] ? `<img src="/${esc(p.reference_photos[0])}" alt="" style="width:100%;max-height:180px;object-fit:cover;border-radius:10px">` : '';
    out.innerHTML = `<div class="card hit">${photo}<h3>${esc(p.name)}</h3>
      <p>${esc(r.explanation)}</p>
      <div class="small muted">${esc(t('confidence'))}: ${pct}%</div><div class="meter"><i style="width:${pct}%"></i></div>
      <div class="actions"><button class="btn primary" data-go="${esc(p.id)}">${esc(t('take_me_there'))}</button><button class="btn ghost" data-place="${esc(p.id)}">${esc(t('learn_more'))}</button></div></div>`;
    return;
  }
  const guesses = (r.top3 || []).map((g) => ({ g, p: S.byId.get(g.place_id) })).filter((x) => x.p);
  if (!guesses.length) { status(st, t('lens_none'), 'err'); return; }
  status(st, r.source === 'nearby' ? t('lens_ai_off') : t('lens_low'), r.source === 'nearby' ? 'err' : '');
  out.innerHTML = (r.explanation ? `<p class="small muted">${esc(r.explanation)}</p>` : '') +
    guesses.map(({ g, p: q }) => placeRow(q, g.confidence ? ` · ${Math.round(g.confidence * 100)}%` : '')).join('');
}

async function onFile(input) {
  const f = input.files?.[0];
  input.value = '';
  if (!f) return;
  try {
    identify(await compress(f), S.gps);
  } catch {
    status($('lens-status'), t('error'), 'err');
  }
}

export function initLens() {
  $('lens-camera').addEventListener('change', (e) => onFile(e.target));
  $('lens-file').addEventListener('change', (e) => onFile(e.target));
  $('view-lens').addEventListener('click', (e) => {
    const go = e.target.closest('[data-go]');
    if (go) return actions.startRoute(go.dataset.go);
    const row = e.target.closest('[data-place]');
    if (row) actions.showPlace(row.dataset.place);
  });
}
