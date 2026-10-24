// fetch with a timeout and one kind of error the UI can show.
import { t } from './i18n.js';

export class ApiError extends Error {}

export async function api(url, { method = 'GET', json, form, timeout = 30000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const opts = { method, signal: ctl.signal, headers: {} };
  if (json !== undefined) { opts.method = 'POST'; opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(json); }
  if (form) { opts.method = 'POST'; opts.body = form; }
  try {
    const res = await fetch(url, opts);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(body.error || body.detail || t('error'));
    return body;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(navigator.onLine === false ? t('offline') : t('error'));
  } finally {
    clearTimeout(timer);
  }
}
