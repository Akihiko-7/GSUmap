// Search: fuzzy matching on names and aliases in the browser; questions it cannot match go to Gemma, then to local rules.
import { S, actions, esc, placeRow, status } from './state.js';
import { t, lang } from './i18n.js';
import { api } from './api.js';

const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[ƙ]/g, 'k').replace(/[ɗ]/g, 'd').replace(/[ɓ]/g, 'b').replace(/[^a-z0-9' ]+/g, ' ').replace(/\s+/g, ' ').trim();

function lev(a, b) {
  if (Math.abs(a.length - b.length) > 3) return 99;
  const d = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0];
    d[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = d[j];
      d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = tmp;
    }
  }
  return d[b.length];
}

const STOP = new Set(['the', 'a', 'an', 'of', 'to', 'in', 'at', 'is', 'where', 'i', 'my', 'me', 'want', 'go', 'do', 'can', 'how', 'find', 'ina', 'zan', 'ne', 'ce', 'da', 'na', 'ta']);

function scoreText(q, qTokens, text) {
  const s = norm(text);
  if (!s) return 0;
  if (s === q) return 100;
  if (s.startsWith(q)) return 92;
  if (new RegExp(`\\b${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(s)) return 85;
  if (q.length >= 3 && s.includes(q)) return 75;
  const words = s.split(' ');
  if (!qTokens.length) return 0;
  let total = 0;
  for (const qt of qTokens) {
    let best = 0;
    for (const w of words) {
      if (w === qt) best = 1;
      else if (w.startsWith(qt) && qt.length >= 3) best = Math.max(best, 0.9);
      else if (qt.length >= 4) { const e = lev(qt, w); if (e <= (qt.length > 6 ? 2 : 1)) best = Math.max(best, 0.8); }
    }
    total += best;
  }
  return Math.round((total / qTokens.length) * 78);
}

export function fuzzy(query) {
  const q = norm(query);
  if (!q) return [];
  const qTokens = q.split(' ').filter((w) => w.length > 1 && !STOP.has(w));
  return S.places
    .map((p) => ({ p, score: Math.max(scoreText(q, qTokens, p.name), ...(p.aliases || []).map((a) => scoreText(q, qTokens, a) - 2)) }))
    .filter((r) => r.score >= 55)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);
}

// the same keyword rules the server uses, for when the server or the AI cannot be reached
function byRules(query) {
  const words = new Set(norm(query).split(' '));
  let best = null, score = 0;
  for (const it of S.intents) {
    const s = it.words.filter((w) => (w.includes(' ') ? norm(query).includes(w) : words.has(w))).length;
    if (s > score) { best = it; score = s; }
  }
  return best && { place_id: best.places[0], reason: lang === 'ha' ? best.reason_ha : best.reason, alternatives: best.places.slice(1, 3), source: 'rules' };
}

const $ = (id) => document.getElementById(id);

function listHtml(results) {
  return results.map((r) => placeRow(r.p)).join('');
}

function answerCard(ans) {
  const p = S.byId.get(ans.place_id);
  if (!p) return '';
  const alts = (ans.alternatives || []).map((id) => S.byId.get(id)).filter(Boolean);
  const photo = p.reference_photos?.[0] ? `<img src="/${esc(p.reference_photos[0])}" alt="" style="width:100%;max-height:160px;object-fit:cover;border-radius:10px">` : '';
  return `<div class="card hit">${photo}
    <span class="small muted">${esc(t(ans.source === 'ai' ? 'by_ai' : 'by_rules'))}</span>
    <h3>${esc(p.name)}</h3>
    ${ans.reason ? `<p><b>${esc(t('why'))}</b> ${esc(ans.reason)}</p>` : ''}
    <div class="actions"><button class="btn primary" data-go="${esc(p.id)}">${esc(t('take_me_there'))}</button><button class="btn ghost" data-place="${esc(p.id)}">${esc(t('learn_more'))}</button></div>
    ${alts.length ? `<p class="small muted">${esc(t('also'))}</p>${alts.map((a) => placeRow(a)).join('')}` : ''}
  </div>`;
}

let seq = 0;
export async function runSearch(query) {
  const out = $('search-results'), st = $('search-status');
  const mine = ++seq;
  const hits = fuzzy(query);
  if (hits.length && hits[0].score >= 80) {
    status(st, '');
    out.innerHTML = listHtml(hits);
    return;
  }
  status(st, t('search_ai'), 'busy');
  out.innerHTML = listHtml(hits);
  let ans;
  try {
    ans = await api('/api/resolve', { json: { query, lang }, timeout: 25000 });
  } catch {
    ans = null;
  }
  if (mine !== seq) return;
  if (!ans || !ans.place_id) ans = byRules(query) || ans;
  status(st, ans && ans.place_id ? '' : hits.length ? '' : t('search_none'));
  out.innerHTML = (ans && ans.place_id ? answerCard(ans) : '') + listHtml(hits.filter((h) => h.p.id !== ans?.place_id));
}

export function initSearch() {
  const input = $('search-input');
  $('search-form').addEventListener('submit', (e) => {
    e.preventDefault();
    input.blur();
    if (input.value.trim()) runSearch(input.value.trim());
  });
  input.addEventListener('input', () => {
    seq++;
    status($('search-status'), '');
    $('search-results').innerHTML = listHtml(fuzzy(input.value));
  });
  document.querySelector('#view-search .examples').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ex]');
    if (!b) return;
    input.value = b.textContent;
    runSearch(b.textContent);
  });
  $('view-search').addEventListener('click', (e) => {
    const go = e.target.closest('[data-go]');
    if (go) return actions.startRoute(go.dataset.go);
    const row = e.target.closest('[data-place]');
    if (row) actions.showPlace(row.dataset.place);
  });
}
