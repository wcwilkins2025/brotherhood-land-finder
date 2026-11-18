/* Land Finder: reads its own stored copy of the USDA soil survey and the USGS well list
   (built monthly by data/store/, hosted on Cloudflare R2). The soil map is one Cloud-Optimized
   GeoTIFF per state in lat/lon at 1 arc-second; a spot or a drawn border reads only the few
   kilobytes it needs with HTTP range requests. Unit facts come in small gzip JSON shards.
   Everything here is read-only and asks for nothing about the visitor. */
(function () {
  'use strict';
  const BASE = (window.LF_DATA || 'https://data.thelandfinder.org').replace(/\/$/, '');
  const GEOTIFF = { src: 'https://cdn.jsdelivr.net/npm/geotiff@2.1.3/dist-browser/geotiff.js', sri: 'sha384-m5adk5PRgt3JjiYbYoG8oXxc3EgRFKc1aCBgKzyxqxnbYpdiAMlHkR0gVDp03Q/H' };
  const RES = 1 / 3600;
  const S = { base: BASE };
  let idxP = null, wellIdxP = null, aqP = null, libP = null;
  const images = new Map(), shards = new Map(), cells = new Map();

  const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u.replace(BASE, 'stored data')}: ${r.status}`); return r.json(); });
  S.index = () => (idxP = idxP || getJSON(`${BASE}/soil/index.json`).catch((e) => { idxP = null; throw e; }));

  function lib() {
    if (window.GeoTIFF) return Promise.resolve(window.GeoTIFF);
    return (libP = libP || new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = GEOTIFF.src; s.integrity = GEOTIFF.sri; s.crossOrigin = 'anonymous';
      s.onload = () => res(window.GeoTIFF); s.onerror = () => { libP = null; rej(new Error('the map reader did not load')); };
      document.head.appendChild(s);
    }));
  }
  function image(st) {
    if (!images.has(st)) images.set(st, lib().then((G) => G.fromUrl(`${BASE}/soil/grid/${st}.tif`, { allowFullFile: false })).then((t) => t.getImage()).catch((e) => { images.delete(st); throw e; }));
    return images.get(st);
  }
  async function gridsFor(w, s, e, n) {
    const ix = await S.index();
    return Object.entries(ix.grids).filter(([, g]) => !(e < g.w || w > g.e || n < g.s || s > g.n)).map(([st, g]) => ({ st, g }));
  }
  // one rectangular window of a state grid, in lat/lon
  async function readWin(st, g, w, s, e, n) {
    let x0 = Math.floor((w - g.w) / RES), x1 = Math.ceil((e - g.w) / RES), y0 = Math.floor((g.n - n) / RES), y1 = Math.ceil((g.n - s) / RES);
    if (x1 === x0) x1++; if (y1 === y0) y1++;
    x0 = Math.max(0, x0); y0 = Math.max(0, y0); x1 = Math.min(g.width, x1); y1 = Math.min(g.height, y1);
    if (x1 <= x0 || y1 <= y0) return null;
    const im = await image(st);
    const [data] = await im.readRasters({ window: [x0, y0, x1, y1] });
    return { data, width: x1 - x0, height: y1 - y0, lon0: g.w + x0 * RES, lat0: g.n - y0 * RES };
  }

  S.mukeyAt = async function (lat, lon) {
    for (const { st, g } of await gridsFor(lon, lat, lon, lat)) {
      const win = await readWin(st, g, lon, lat, lon, lat);
      if (win && win.data[0] > 0) return String(win.data[0]);
    }
    return null;
  };

  // map units inside a drawn border: area per unit from the grid cells whose centers fall inside
  S.unitsIn = async function (verts) {
    const lats = verts.map((v) => v[0]), lons = verts.map((v) => v[1]);
    const w = Math.min(...lons), e = Math.max(...lons), s = Math.min(...lats), n = Math.max(...lats);
    const inside = (lat, lon) => { let c = false; for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) { const [yi, xi] = verts[i], [yj, xj] = verts[j]; if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) c = !c; } return c; };
    const area = new Map(), wins = [], seen = new Set();
    for (const { st, g } of await gridsFor(w, s, e, n)) {
      const win = await readWin(st, g, w, s, e, n); if (!win) continue;
      const mask = new Int32Array(win.width * win.height);
      for (let y = 0; y < win.height; y++) {
        const lat = win.lat0 - (y + 0.5) * RES; const cell = (RES * 111320 * Math.cos(lat * Math.PI / 180)) * (RES * 110540);
        for (let x = 0; x < win.width; x++) {
          const v = win.data[y * win.width + x]; if (!(v > 0)) continue;
          const lon = win.lon0 + (x + 0.5) * RES; const key = `${y + Math.round((g.n - win.lat0) / RES)}:${x}:${st}`;
          if (!inside(lat, lon)) continue;
          const id = `${Math.round(lat / RES)}_${Math.round(lon / RES)}`; if (seen.has(id)) continue; seen.add(id);   // border overlap between state grids
          mask[y * win.width + x] = v; area.set(String(v), (area.get(String(v)) || 0) + cell);
        }
      }
      wins.push({ mask, width: win.width, height: win.height, lon0: win.lon0, lat0: win.lat0 });
    }
    const tot = [...area.values()].reduce((a, b) => a + b, 0);
    const units = [...area.entries()].map(([mukey, m2]) => ({ mukey, m2, share: tot ? m2 / tot : 0, polys: [] })).sort((a, b) => b.share - a.share);
    return { units, tot, wins };
  };

  // paint the units inside the border as an image over the map
  S.overlays = function (wins, colorOf, L) {
    return wins.map((wn) => {
      const c = document.createElement('canvas'); c.width = wn.width; c.height = wn.height;
      const ctx = c.getContext('2d'); const img = ctx.createImageData(wn.width, wn.height);
      for (let i = 0; i < wn.mask.length; i++) {
        const v = wn.mask[i]; if (!v) continue; const col = colorOf(String(v)); if (!col) continue;
        img.data[i * 4] = parseInt(col.slice(1, 3), 16); img.data[i * 4 + 1] = parseInt(col.slice(3, 5), 16); img.data[i * 4 + 2] = parseInt(col.slice(5, 7), 16); img.data[i * 4 + 3] = 120;
      }
      ctx.putImageData(img, 0, 0);
      return L.imageOverlay(c.toDataURL(), [[wn.lat0 - wn.height * RES, wn.lon0], [wn.lat0, wn.lon0 + wn.width * RES]], { interactive: false, className: 'pixelated' });
    });
  };

  // unit facts for these map unit keys, as the same rows Soil Data Access returns
  S.units = async function (mukeys) {
    const ix = await S.index();
    const need = [...new Set(mukeys.map((k) => +k % ix.shards))];
    await Promise.all(need.map((i) => { if (!shards.has(i)) shards.set(i, getJSON(`${BASE}/soil/mu/${i}.json`).catch((e) => { shards.delete(i); throw e; })); return shards.get(i); }));
    const C = ix.cols, mu = [], comps = [], ratings = [], layersBy = new Map();
    for (const k of mukeys) {
      const rec = (await shards.get(+k % ix.shards))[k]; if (!rec) continue;
      const m = { mukey: k }; C.m.forEach((c, j) => { m[c] = rec.m[j]; }); mu.push(m);
      rec.c.forEach((row) => { const o = { mukey: k }; C.c.forEach((c, j) => { o[c] = row[j]; }); o.cokey = String(o.cokey); comps.push(o); });
      rec.r.forEach((r) => ratings.push({ mukey: k, cokey: String(r[0]), mrulename: ix.interps[r[1]], ruledepth: r[2], interphr: r[3], interphrc: r[4] }));
      if (rec.c[0]) layersBy.set(String(rec.c[0][0]), rec.h.map((h) => { const o = {}; C.h.forEach((c, j) => { o[c] = h[j]; }); return o; }));
    }
    ratings.sort((a, b) => a.ruledepth - b.ruledepth);
    return { mu, comps, ratings, layersBy };
  };
  S.release = async function (lat, lon) {
    const gs = await gridsFor(lon, lat, lon, lat); return gs[0] ? gs[0].g.release : null;
  };

  // soil map unit lines drawn from the stored grid, for zoom 13 and closer
  S.lineLayer = function (L, opts) {
    const Layer = L.GridLayer.extend({
      createTile(coords, done) {
        const tile = document.createElement('canvas'); tile.width = tile.height = 256;
        const map = this._map, z = coords.z;
        const nw = map.unproject([coords.x * 256, coords.y * 256], z), se = map.unproject([(coords.x + 1) * 256, (coords.y + 1) * 256], z);
        gridsFor(nw.lng, se.lat, se.lng, nw.lat).then(async (gs) => {
          const ctx = tile.getContext('2d'); ctx.strokeStyle = (opts && opts.color) || '#ffb84d'; ctx.lineWidth = 1.5; ctx.beginPath();
          for (const { st, g } of gs) {
            const win = await readWin(st, g, nw.lng, se.lat, se.lng, nw.lat); if (!win) continue;
            const px = (lon, lat) => { const p = map.project([lat, lon], z); return [p.x - coords.x * 256, p.y - coords.y * 256]; };
            for (let y = 0; y < win.height; y++) for (let x = 0; x < win.width; x++) {
              const v = win.data[y * win.width + x]; if (!(v > 0)) continue;
              const lon = win.lon0 + x * RES, lat = win.lat0 - y * RES;
              if (x + 1 < win.width && win.data[y * win.width + x + 1] !== v) { const a = px(lon + RES, lat), b = px(lon + RES, lat - RES); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
              if (y + 1 < win.height && win.data[(y + 1) * win.width + x] !== v) { const a = px(lon, lat - RES), b = px(lon + RES, lat - RES); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
            }
          }
          ctx.stroke(); done(null, tile);
        }).catch((e) => done(e, tile));
        return tile;
      },
    });
    return new Layer(Object.assign({ minZoom: 13, maxZoom: 19, attribution: 'USDA NRCS Soil Survey (stored copy)' }, opts || {}));
  };

  // wells near a spot, from the stored USGS list
  S.wells = async function (lat, lon, d) {
    const ix = await (wellIdxP = wellIdxP || getJSON(`${BASE}/wells/index.json`).catch((e) => { wellIdxP = null; throw e; }));
    const have = new Set(ix.cells), out = [];
    for (let a = Math.floor(lat - d); a <= Math.floor(lat + d); a++) for (let b = Math.floor(lon - d); b <= Math.floor(lon + d); b++) {
      const k = `${a}_${b}`; if (!have.has(k)) continue;
      if (!cells.has(k)) cells.set(k, getJSON(`${BASE}/wells/${k}.json`).catch((e) => { cells.delete(k); throw e; }));
      for (const w of await cells.get(k)) if (Math.abs(w[2] - lat) <= d && Math.abs(w[3] - lon) <= d) out.push(w);
    }
    return { built: ix.built, wells: out.map((w) => ({ id: w[0], name: w[1], lat: w[2], lon: w[3], depth: w[4], hole: w[5], aq: w[6], county: w[7], st: w[8], lev: w[9] == null ? null : { v: w[9], time: w[10] || '' } })) };
  };
  S.aquiferNames = () => (aqP = aqP || getJSON(`${BASE}/wells/aquifers.json`).catch((e) => { aqP = null; throw e; }));

  window.SoilStore = S;
})();
