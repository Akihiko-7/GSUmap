// Walking directions: Dijkstra over the campus path graph (data/paths.geojson), then turn-by-turn text with landmarks.
import { S, distM } from './state.js';
import { t } from './i18n.js';

let G = null; // { pts: [{x,y,lng,lat}], adj: [[ [to, w], ... ]], main: Set of node ids in the largest connected part }
let origin = null;

// flat metres around the campus centre: accurate enough over 2 km
function xy(lng, lat) {
  const k = Math.PI / 180;
  return { x: (lng - origin.lng) * 111320 * Math.cos(origin.lat * k), y: (lat - origin.lat) * 110574 };
}

export async function loadGraph() {
  origin = S.config.center;
  const gj = await (await fetch('/api/geo/paths')).json();
  const index = new Map(), pts = [], adj = [];
  const node = (c) => {
    const key = c[0].toFixed(6) + ',' + c[1].toFixed(6);
    let id = index.get(key);
    if (id === undefined) {
      id = pts.length;
      index.set(key, id);
      pts.push({ ...xy(c[0], c[1]), lng: c[0], lat: c[1] });
      adj.push([]);
    }
    return id;
  };
  for (const f of gj.features) {
    const cs = f.geometry.coordinates;
    for (let i = 1; i < cs.length; i++) {
      const a = node(cs[i - 1]), b = node(cs[i]);
      if (a === b) continue;
      const w = Math.hypot(pts[a].x - pts[b].x, pts[a].y - pts[b].y);
      adj[a].push([b, w]);
      adj[b].push([a, w]);
    }
  }
  // keep the largest connected part, so a start and an end never land on two islands
  const comp = new Int32Array(pts.length).fill(-1);
  let best = -1, bestSize = 0;
  for (let s = 0, c = 0; s < pts.length; s++) {
    if (comp[s] !== -1) continue;
    let size = 0;
    const stack = [s];
    comp[s] = c;
    while (stack.length) {
      const u = stack.pop();
      size++;
      for (const [v] of adj[u]) if (comp[v] === -1) { comp[v] = c; stack.push(v); }
    }
    if (size > bestSize) { bestSize = size; best = c; }
    c++;
  }
  const main = new Set();
  comp.forEach((c, i) => { if (c === best) main.add(i); });
  G = { pts, adj, main };
}

function nearestNode(p) {
  const q = xy(p.lng, p.lat);
  let best = -1, bd = Infinity;
  for (const i of G.main) {
    const d = (G.pts[i].x - q.x) ** 2 + (G.pts[i].y - q.y) ** 2;
    if (d < bd) { bd = d; best = i; }
  }
  return { id: best, d: Math.sqrt(bd) };
}

function dijkstra(s, goal) {
  const n = G.pts.length, dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1);
  const heap = [[0, s]];
  dist[s] = 0;
  const push = (item) => {
    heap.push(item);
    let i = heap.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; }
  };
  const pop = () => {
    const top = heap[0], last = heap.pop();
    if (heap.length) {
      heap[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
        if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
        if (m === i) break;
        [heap[m], heap[i]] = [heap[i], heap[m]];
        i = m;
      }
    }
    return top;
  };
  while (heap.length) {
    const [d, u] = pop();
    if (u === goal) break;
    if (d > dist[u]) continue;
    for (const [v, w] of G.adj[u]) {
      if (d + w < dist[v]) { dist[v] = d + w; prev[v] = u; push([d + w, v]); }
    }
  }
  if (!isFinite(dist[goal])) return null;
  const path = [];
  for (let u = goal; u !== -1; u = prev[u]) path.push(u);
  return path.reverse();
}

const bearing = (a, b) => (Math.atan2(b.x - a.x, b.y - a.y) * 180) / Math.PI; // 0 = north, clockwise
const turnOf = (b1, b2) => ((b2 - b1 + 540) % 360) - 180; // + right, - left
const DIRS = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'];
const compass = (b) => t('dir_' + DIRS[Math.round(((b + 360) % 360) / 45) % 8]);

// Douglas-Peucker, so little wiggles in the paths do not become "turns"
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const [a, b] = [pts[0], pts[pts.length - 1]];
  let idx = -1, md = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i], dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1;
    const d = Math.abs(dy * p.x - dx * p.y + b.x * a.y - b.y * a.x) / L;
    if (d > md) { md = d; idx = i; }
  }
  if (md <= tol) return [a, b];
  return [...simplify(pts.slice(0, idx + 1), tol).slice(0, -1), ...simplify(pts.slice(idx), tol)];
}

function segDist(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy || 1;
  const k = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L2));
  return Math.hypot(p.x - a.x - dx * k, p.y - a.y - dy * k);
}

function placesXY(excludeIds) {
  return S.places.filter((p) => !excludeIds.includes(p.id) && (p.category !== 'landmark' || p.id === 'fountain')).map((p) => ({ p, ...xy(p.lng, p.lat) }));
}

/**
 * from: { lat, lng, name } ; to: place. Returns { coords, dist, steps, straight }.
 */
export function planRoute(from, to, fmt) {
  const A = { lat: from.lat, lng: from.lng }, B = { lat: to.lat, lng: to.lng };
  let nodes = null;
  if (G && G.main.size) {
    const s = nearestNode(A), g = nearestNode(B);
    if (s.d < 600 && g.d < 600) nodes = s.id === g.id ? [s.id] : dijkstra(s.id, g.id);
  }
  if (!nodes) {
    const d = distM(A, B), a = xy(A.lng, A.lat), b = xy(B.lng, B.lat);
    return { coords: [[A.lng, A.lat], [B.lng, B.lat]], dist: d, straight: true,
      steps: [t('step_straight', { d: fmt(d), dir: compass(bearing(a, b)), dest: to.name })] };
  }
  const line = [{ ...xy(A.lng, A.lat), lng: A.lng, lat: A.lat }, ...nodes.map((i) => G.pts[i]), { ...xy(B.lng, B.lat), lng: B.lng, lat: B.lat }];
  let dist = 0;
  for (let i = 1; i < line.length; i++) dist += Math.hypot(line[i].x - line[i - 1].x, line[i].y - line[i - 1].y);
  return { coords: line.map((p) => [p.lng, p.lat]), dist, straight: false, steps: describe(line, from, to, fmt) };
}

function describe(line, from, to, fmt) {
  const walk = simplify(line.slice(0, -1), 7); // the path, without the last few metres to the door
  const start = line[0];
  const marks = placesXY([to.id, from.id]).filter((m) => Math.hypot(m.x - start.x, m.y - start.y) > 40);
  const used = new Set();
  const steps = [];
  if (walk.length < 2) {
    steps.push(t('step_arrive', { dest: to.name, side: t('side_ahead') }));
    return steps;
  }
  steps.push(t('step_start', { from: from.name, dir: compass(bearing(walk[0], walk[1])) }));
  let run = 0;
  for (let i = 1; i < walk.length; i++) {
    const a = walk[i - 1], b = walk[i];
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    run += len;
    // a landmark along this stretch
    const past = marks.find((m) => !used.has(m.p.id) && segDist(m, a, b) < 30 && Math.hypot(m.x - b.x, m.y - b.y) > 25);
    if (past && len > 40) { used.add(past.p.id); steps.push(t('step_past', { place: past.p.name })); }
    if (i === walk.length - 1) break;
    const turn = turnOf(bearing(a, b), bearing(b, walk[i + 1]));
    const at = Math.abs(turn);
    if (at < 30) continue;
    const word = at > 150 ? 'step_back' : at < 60 ? (turn > 0 ? 'step_slight_right' : 'step_slight_left') : turn > 0 ? 'step_right' : 'step_left';
    const near = marks.filter((m) => !used.has(m.p.id)).map((m) => ({ m, d: Math.hypot(m.x - b.x, m.y - b.y) })).sort((u, v) => u.d - v.d)[0];
    const where = near && near.d < 45 ? (used.add(near.m.p.id), t('step_at', { place: near.m.p.name })) : t('step_after', { d: fmt(run) });
    steps.push(`${t(word)} ${where}.`);
    run = 0;
  }
  // which side the destination is on, from the last direction of travel
  const last = walk[walk.length - 1], prev = walk[walk.length - 2], dest = line[line.length - 1];
  const side = Math.hypot(dest.x - last.x, dest.y - last.y) < 8 ? 0 : turnOf(bearing(prev, last), bearing(last, dest));
  steps.push(t('step_arrive', { dest: to.name, side: t(Math.abs(side) < 35 ? 'side_ahead' : side > 0 ? 'side_right' : 'side_left') }));
  return steps;
}
