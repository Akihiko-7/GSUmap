// GonaDoc: photograph a crop leaf, Gemma names the likely disease or pest and suggests cheap treatment first.
import { S, esc, status } from './state.js';
import { t, lang } from './i18n.js';
import { api } from './api.js';
import { compress, showPreview } from './img.js';

const $ = (id) => document.getElementById(id);
let answerLang = null; // follows the app language until the farmer picks one here

const gdLang = () => answerLang || lang;

function paintLang() {
  $('gd-lang').querySelectorAll('[data-lang]').forEach((b) => b.classList.toggle('on', b.dataset.lang === gdLang()));
}

async function diagnose(blob, sampleId = '') {
  const st = $('gd-status'), out = $('gd-result');
  out.innerHTML = '';
  showPreview($('gd-preview'), blob);
  status(st, t('gd_busy'), 'busy');
  const form = new FormData();
  form.append('photo', blob, 'leaf.jpg');
  form.append('crop', $('gd-crop').value);
  form.append('lang', gdLang());
  form.append('sample_id', sampleId);
  try {
    render(await api('/api/gonadoc', { form, timeout: 60000 }));
    st.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    status(st, e.message, 'err');
  }
}

const list = (items) => (items?.length ? `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '');

function render(r) {
  const st = $('gd-status'), out = $('gd-result');
  status(st, '');
  if (!r.is_crop_leaf) { status(st, t('gd_not_leaf'), 'err'); return; }
  const pct = Math.round((r.confidence || 0) * 100);
  const title = r.healthy ? t('gd_healthy') : r.problem;
  out.innerHTML = `<div class="card hit">
    <span class="small muted">${esc(r.crop)}</span>
    <h3>${esc(title)}</h3>
    ${r.local_name ? `<p class="small">${esc(r.local_name)}</p>` : ''}
    <div class="small muted">${esc(t('confidence'))}: ${pct}%</div><div class="meter"><i style="width:${pct}%"></i></div>
    ${r.symptoms_seen?.length ? `<h4>${esc(t('gd_symptoms'))}</h4>${list(r.symptoms_seen)}` : ''}
    ${r.treatment?.length ? `<h4>${esc(t('gd_treatment'))}</h4>${list(r.treatment)}` : ''}
    ${r.prevention?.length ? `<h4>${esc(t('gd_prevention'))}</h4>${list(r.prevention)}` : ''}
    ${r.see_extension_officer ? `<h4>${esc(t('gd_officer'))}</h4><p>${esc(r.see_extension_officer)}</p>` : ''}
    <p class="disclaimer">${esc(t('gd_disclaimer'))}</p>
  </div>`;
}

async function onFile(input) {
  const f = input.files?.[0];
  input.value = '';
  if (!f) return;
  try {
    diagnose(await compress(f));
  } catch {
    status($('gd-status'), t('error'), 'err');
  }
}

export function initGonaDoc() {
  $('gd-camera').addEventListener('change', (e) => onFile(e.target));
  $('gd-file').addEventListener('change', (e) => onFile(e.target));
  $('gd-lang').addEventListener('click', (e) => {
    const b = e.target.closest('[data-lang]');
    if (b) { answerLang = b.dataset.lang; paintLang(); }
  });
  paintLang();
  document.addEventListener('langchange', paintLang);
  const samples = S.config.demo_samples?.gonadoc || [];
  if (S.demo && samples.length) {
    $('gd-samples').hidden = false;
    $('gd-samples').querySelector('.sample-row').innerHTML = samples.map((s) => `<button data-sample="${esc(s.id)}"><img src="/${esc(s.image)}" alt=""><span>${esc(s.label)}</span></button>`).join('');
    $('gd-samples').addEventListener('click', (e) => {
      const b = e.target.closest('[data-sample]');
      if (!b) return;
      const s = samples.find((x) => x.id === b.dataset.sample);
      fetch('/' + s.image).then((r) => r.blob()).then((blob) => diagnose(blob, s.id));
    });
  }
}
