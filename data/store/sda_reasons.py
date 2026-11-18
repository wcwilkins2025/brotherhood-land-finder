"""The reasons behind each NRCS rating ("Depth to saturated zone", "Slow water movement", ...).
USDA's gSSURGO download keeps only the rating itself (rule depth 0); the reasons (rule depth 1)
are only in Soil Data Access. This fetches them per survey area for the 12 ratings Land Finder
shows and saves downloads/store/reasons/<ST>.json  {cokey: [[interp_index, seqnum, interphr, interphrc], ...]}.

If Soil Data Access is down, the previous file is kept and the monthly run tries again.
"""
import json, os, time, urllib.request

SDA = 'https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest'


def sda(query, tries=3):
    body = json.dumps({'query': query, 'format': 'JSON+COLUMNNAME'}).encode()
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(SDA, data=body, headers={'Content-Type': 'application/json', 'User-Agent': 'land-finder-data'})
            with urllib.request.urlopen(req, timeout=300) as r:
                t = r.read().decode('utf-8', 'ignore')
            if t.startswith('<'):
                raise RuntimeError(t[:200])
            rows = json.loads(t).get('Table') or []
            if not rows:
                return []
            cols = rows[0]
            return [dict(zip(cols, r)) for r in rows[1:]]
        except Exception as e:
            last = e
            time.sleep(20 * (k + 1))
    raise RuntimeError(f'Soil Data Access unavailable: {last}')


def fetch(st, areas, interps, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    idx = {n: i for i, n in enumerate(interps)}
    names = ','.join("'" + n.replace("'", "''") + "'" for n in interps)
    reasons = {}
    for a in areas:
        rows = sda(f"""SELECT c.cokey, i.mrulename, i.seqnum, i.interphr, i.interphrc
            FROM legend l JOIN mapunit m ON m.lkey = l.lkey JOIN component c ON c.mukey = m.mukey
            JOIN cointerp i ON i.cokey = c.cokey
            WHERE l.areasymbol = '{a}' AND c.majcompflag = 'Yes' AND i.ruledepth = 1 AND i.mrulename IN ({names})""")
        for r in rows:
            hr = r['interphr']
            reasons.setdefault(str(r['cokey']), []).append([idx[r['mrulename']], int(r['seqnum'] or 0), None if hr is None else round(float(hr), 3), r['interphrc']])
        time.sleep(1)
    for v in reasons.values():
        v.sort(key=lambda x: (x[0], x[1]))
    json.dump(reasons, open(os.path.join(out_dir, f'{st}.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    return len(reasons)
