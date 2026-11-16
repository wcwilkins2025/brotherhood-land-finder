/* Land Finder: parcel lookup shared by the main map and the parcel check.
   Asks a state's own public parcel service (listed in data/parcels.json, each one tested)
   for the tax parcel at a point or the parcels in a box. Runs in the browser; nothing is stored,
   and there is no search by owner name on purpose. */
(function () {
  'use strict';
  let cfg = null;
  const P = {};

  P.load = function () {
    if (cfg) return Promise.resolve(cfg);
    return fetch('data/parcels.json').then((r) => { if (!r.ok) throw new Error('parcel list did not load'); return r.json(); }).then((j) => (cfg = j));
  };
  P.state = function (st) { return cfg && cfg.states && cfg.states[st] && cfg.states[st].available ? cfg.states[st] : null; };
  P.info = function (st) { return cfg && cfg.states ? cfg.states[st] || null : null; };

  // rings as [lat, lon] for Leaflet
  function fromGeoJSON(g) {
    if (!g) return [];
    if (g.type === 'Polygon') return [g.coordinates.map((r) => r.map((p) => [p[1], p[0]]))];
    if (g.type === 'MultiPolygon') return g.coordinates.map((poly) => poly.map((r) => r.map((p) => [p[1], p[0]])));
    return [];
  }
  function fromEsri(g) {
    if (!g || !g.rings) return [];
    return [g.rings.map((r) => r.map((p) => [p[1], p[0]]))];
  }
  function pick(props, name) {
    if (!name) return null;
    if (props[name] != null) return props[name];
    const k = Object.keys(props).find((x) => x.toLowerCase() === String(name).toLowerCase());
    return k ? props[k] : null;
  }
  function norm(s, props, polys) {
    const f = s.fields || {};
    let acres = pick(props, f.acres); acres = acres == null || acres === '' || String(acres).toLowerCase() === 'null' ? null : +acres;
    if ((acres == null || !(acres > 0)) && f.area_sqft) { const a = +pick(props, f.area_sqft); if (a > 0) acres = a / 43560; }
    if ((acres == null || !(acres > 0)) && polys.length) acres = areaAcres(polys);
    const clean = (v) => { if (v == null) return null; const t = String(v).trim(); return t && t.toLowerCase() !== 'null' ? t : null; };
    return { polys, owner: s.owner_included === false ? null : clean(pick(props, f.owner)), id: clean(pick(props, f.id)), acres, address: (clean(pick(props, f.address)) || '').replace(/(\s*,\s*)+/g, ', ').replace(/^[ ,]+|[ ,]+$/g, '') || null, county: clean(pick(props, f.county)) };
  }
  function areaAcres(polys) {
    let m2 = 0;
    polys.forEach((rings) => rings.forEach((ring, i) => {
      const lat0 = ring[0][0] * Math.PI / 180, kx = 111320 * Math.cos(lat0), ky = 110540; let a = 0;
      for (let j = 0; j < ring.length; j++) { const [y1, x1] = ring[j], [y2, x2] = ring[(j + 1) % ring.length]; a += x1 * kx * y2 * ky - x2 * kx * y1 * ky; }
      m2 += (i === 0 ? 1 : -1) * Math.abs(a) / 2;
    }));
    return m2 / 4046.86;
  }
  // some services (Texas) only answer the MapServer identify operation
  function identify(s, geometry, geometryType, ext) {
    const svc = s.layer.replace(/\/\d+$/, ''); const lyr = (s.layer.match(/\/(\d+)$/) || [, '0'])[1];
    const q = new URLSearchParams({ geometry, geometryType, sr: '4326', layers: `all:${lyr}`, tolerance: '0', mapExtent: ext, imageDisplay: '800,800,96', returnGeometry: 'true', f: 'json' });
    return fetch(`${svc}/identify?${q}`).then((r) => { if (!r.ok) throw new Error(`${s.name}: ${r.status}`); return r.json(); }).then((j) => {
      if (j.error) throw new Error(`${s.name}: ${j.error.message || 'error'}`);
      return (j.results || []).map((ft) => norm(s, ft.attributes || {}, fromEsri(ft.geometry)));
    });
  }
  function query(s, params) {
    const fmt = s.format === 'json' ? 'json' : 'geojson';
    const q = new URLSearchParams(Object.assign({ inSR: '4326', outSR: '4326', spatialRel: 'esriSpatialRelIntersects', outFields: Object.values(s.fields || {}).filter(Boolean).join(',') || '*', returnGeometry: 'true', f: fmt }, params));
    return fetch(`${s.layer}/query?${q}`).then((r) => { if (!r.ok) throw new Error(`${s.name}: ${r.status}`); return r.json(); }).then((j) => {
      if (j.error) throw new Error(`${s.name}: ${j.error.message || 'error'}`);
      const feats = j.features || [];
      return feats.map((ft) => fmt === 'json' ? norm(s, ft.attributes || {}, fromEsri(ft.geometry)) : norm(s, ft.properties || {}, fromGeoJSON(ft.geometry)));
    });
  }
  P.at = function (st, lat, lon) {
    const s = P.state(st); if (!s) return Promise.resolve(null);
    if (s.format === 'identify') return identify(s, `${lon},${lat}`, 'esriGeometryPoint', `${lon - 0.01},${lat - 0.01},${lon + 0.01},${lat + 0.01}`).then((fs) => fs.find((f) => f.polys.length) || null);
    return query(s, { geometry: `${lon},${lat}`, geometryType: 'esriGeometryPoint' }).then((fs) => fs.find((f) => f.polys.length) || null);
  };
  P.inBox = function (st, south, west, north, east, max) {
    const s = P.state(st); if (!s) return Promise.resolve([]);
    if (s.format === 'identify') return identify(s, `${west},${south},${east},${north}`, 'esriGeometryEnvelope', `${west},${south},${east},${north}`).then((fs) => fs.filter((f) => f.polys.length).slice(0, max || 400));
    return query(s, { geometry: `${west},${south},${east},${north}`, geometryType: 'esriGeometryEnvelope', resultRecordCount: String(max || 400) }).then((fs) => fs.filter((f) => f.polys.length));
  };
  // the outer ring of the largest polygon, for handing a parcel to the soil and water check
  P.outer = function (f) {
    let best = null, bestA = -1;
    f.polys.forEach((rings) => { const a = areaAcres([[rings[0]]]); if (a > bestA) { bestA = a; best = rings[0]; } });
    return best || [];
  };
  P.esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  P.card = function (f, st) {
    const s = P.info(st) || {};
    const e = P.esc;
    return `<div class="pcard"><div class="pk">Tax parcel</div>
      <div class="pv">${f.owner ? e(f.owner) : '<span class="muted">Owner not published by this state</span>'}</div>
      <div class="pm">${f.acres ? `${f.acres >= 10 ? Math.round(f.acres) : f.acres.toFixed(2)} acres` : ''}${f.id ? ` · Parcel ${e(f.id)}` : ''}${f.address ? `<br>${e(f.address)}` : ''}${f.county && !/^\d+$/.test(f.county) ? `<br>${e(/county|parish|borough|town/i.test(f.county) ? f.county : f.county + ' County')}` : ''}</div>
      <div class="ps">${e(s.name || 'State parcel service')}${s.updated ? `, ${e(s.updated)}` : ''}.${s.stale ? ' <b>Old data: the owner may have changed.</b>' : ''} Tax maps are not surveys; lines can be off by many feet. Confirm the owner at the county.</div></div>`;
  };
  // which state a point is in, from the Census county shapes (loaded once, shared with the main map)
  const FIPS2ST = { '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND', '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI', '56': 'WY' };
  let boxes = null, geoP = null;
  P.setCounties = function (geo) {
    boxes = geo.features.map((f) => { let a = 180, b = 90, c = -180, d = -90; const walk = (x) => { if (typeof x[0] === 'number') { a = Math.min(a, x[0]); c = Math.max(c, x[0]); b = Math.min(b, x[1]); d = Math.max(d, x[1]); } else x.forEach(walk); }; walk(f.geometry.coordinates); return { f, a, b, c, d }; });
  };
  P.countyAt = function (lat, lon) {
    const get = boxes ? Promise.resolve() : (geoP = geoP || fetch('data/counties.geojson').then((r) => r.json()).then(P.setCounties));
    return get.then(() => {
      const inRing = (ring) => { let inside = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside; } return inside; };
      const inPoly = (poly) => inRing(poly[0]) && !poly.slice(1).some(inRing);
      for (const b of boxes) { if (lon < b.a || lon > b.c || lat < b.b || lat > b.d) continue; const g = b.f.geometry; const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates; if (polys.some(inPoly)) return { fips: b.f.id, st: FIPS2ST[String(b.f.id).slice(0, 2)] || null }; }
      return null;
    });
  };
  window.Parcels = P;
})();
