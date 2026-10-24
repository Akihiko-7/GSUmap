// UI strings in English and Hausa, from /i18n.json. The chosen language is remembered on this phone.
let dict = { en: {}, ha: {} };
export let lang = 'en';
try { lang = localStorage.getItem('lang') === 'ha' ? 'ha' : 'en'; } catch {}

export async function loadI18n() {
  dict = await (await fetch('/i18n.json')).json();
}

export function t(key, vars = {}) {
  let s = dict[lang]?.[key] ?? dict.en?.[key] ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

export function applyI18n(root = document) {
  document.documentElement.lang = lang;
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  root.querySelectorAll('[data-ex]').forEach((el) => { el.textContent = t(el.dataset.ex); });
}

export function setLang(l) {
  lang = l;
  try { localStorage.setItem('lang', l); } catch {}
  applyI18n();
}
