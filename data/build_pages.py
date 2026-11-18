"""Static pages for search engines: one per state (/tx/) and one per county (/tx/fannin-county/),
built from data/counties.json, plus sitemap.xml. The map page stays the tool; these pages carry the
facts as plain HTML so a search for "homestead land Fannin County Texas" can find them, and each one
opens its county on the map.

Run after data/build.py:  python -I data/build_pages.py
"""
import html, io, json, math, os, re, shutil

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SITE = 'https://thelandfinder.org'
D = json.load(io.open(os.path.join(ROOT, 'data', 'counties.json'), encoding='utf-8'))
F = D['fields']
ROWS = [dict(zip(F, r)) for r in D['rows']]
STATES = D['states']
BUILT = D['built']
e = lambda s: html.escape('' if s is None else str(s), quote=True)

FAMILY = ('<p class="hr-family">Part of <a href="https://homesteadready.org/">Homestead Ready</a>, free tools for land, '
          'homesteading, health, readiness and radio. <a href="https://www.facebook.com/groups/homesteadready" rel="noopener">Join the Facebook group</a>.</p>')


def slug(s):
    s = re.sub(r"['’.]", '', s.lower())
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def fmt(v, d=0, unit=''):
    if v is None or v == '':
        return 'no data'
    return f'{v:,.{d}f}{unit}'


def money(v):
    return 'no data' if v is None else f'${v:,.0f}'


def hav(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2); y = math.sin((d - b) * r / 2)
    return 2 * 3958.8 * math.asin(math.sqrt(x * x + math.cos(a * r) * math.cos(c * r) * y * y))


ZWORD = {'none': 'No county zoning', 'partial': 'Partial zoning', 'county': 'County-wide zoning',
         'municipal': 'Zoning is done by towns, not the county', 'verify': 'Unknown, verify with the county'}


def zflag(r):
    if r['zoning_level'] == 'county_site':
        return 'confirmed on the county site'
    if r['zoning_level'] == 'state_list':
        return 'from an official state list'
    if r['zoning_level'] == 'third_party_list':
        return 'from a third-party list, verify'
    if r['zoning'] in ('none', 'county') and r['zoning_level'] == 'state_pattern':
        return 'settled by state law'
    return 'verify with the county'


# county page paths; check they are unique inside each state
paths = {}
for r in ROWS:
    p = f"{r['st'].lower()}/{slug(r['name'])}/"
    assert p not in paths.values(), ('duplicate path', p)
    paths[r['fips']] = p

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{site}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="/pages.css">
<script>try {{ var t = localStorage.getItem('theme'); if (t) document.documentElement.setAttribute('data-theme', t); }} catch (e) {{}}</script>
</head>
<body>
'''

FOOT = '''<footer>
  <div class="wrap">
    {family}
    <p>Free, no login, no tracking. Every number comes from a public dataset; the sources and dates are listed in <a href="https://github.com/wcwilkins2025/land-finder/blob/main/data/sources.md" rel="noopener">data/sources.md</a>. Data built {built}. Check everything with the county before you buy.</p>
  </div>
</footer>
</body>
</html>
'''


def fact(k, v, src=''):
    return f'<li><div class="k">{k}</div><div class="v">{v}</div>' + (f'<div class="src">{src}</div>' if src else '') + '</li>'


def state_law(S):
    tax = S.get('income_tax_top_rate')
    taxw = 'no data' if tax is None else ('None' if tax == 0 else f'{100 * tax:.2f}%')
    return ''.join([
        fact('County zoning, statewide pattern', e(S.get('zoning_note') or 'no data'), e(S.get('zoning_source_name') or '')),
        fact('Homeschool', e(S.get('homeschool') or 'no data'), e(S.get('homeschool_note') or '')),
        fact('Carry', e((S.get('carry') or 'no data').replace('_', ' ')), e(S.get('carry_note') or '')),
        fact('Right to farm', 'Yes' if S.get('right_to_farm') else 'no data', e(S.get('right_to_farm_note') or '')),
        fact('Rainwater collection', e((S.get('rainwater') or 'no data').replace('_', ' ')), e(S.get('rainwater_note') or '')),
        fact('Off-grid notes', e(S.get('offgrid_note') or 'no data')),
        fact('State income tax, top rate', taxw, e(S.get('income_tax_note') or '')),
    ])


def county_page(r):
    S = STATES.get(r['st'], {})
    st_name = S.get('name') or r['st']
    cname = r['name']
    base = re.sub(r' (County|Parish|Borough|Census Area|Municipality|City and Borough|city)$', '', cname, flags=re.I)
    unit = 'parish' if cname.endswith('Parish') else 'county'
    url = f"{SITE}/{paths[r['fips']]}"
    title = f"{cname}, {r['st']} for homesteading | Land Finder"
    bits = []
    if r['farm_value_acre'] is not None: bits.append(f"farm land about {money(r['farm_value_acre'])} an acre")
    if r['precip_in'] is not None: bits.append(f"{r['precip_in']:.0f} in. of rain")
    if r['growing_days'] is not None: bits.append(f"{r['growing_days']}-day growing season")
    if r['well_depth_med_ft'] is not None: bits.append(f"wells about {r['well_depth_med_ft']:.0f} ft")
    bits.append(ZWORD.get(r['zoning'], 'zoning unknown').lower().replace('unknown, verify with the county', 'zoning to verify'))
    desc = f"{cname}, {st_name}: " + ', '.join(bits) + '. Free facts, sources and records links for buying rural land.'
    near = sorted((hav(r['lat'], r['lon'], o['lat'], o['lon']), o) for o in ROWS if o['fips'] != r['fips'])[:8]
    netr = f"https://publicrecords.netronline.com/state/{r['st']}/county/{slug(base)}"
    lf = f"https://www.landandfarm.com/search/{slug(st_name)}/{slug(base)}-{unit}-land-for-sale/"
    prime = 'no data' if r['prime_pct'] is None else f"{fmt(r['prime_pct'], 0, '%')} <span class=\"src\">+ {fmt(r['prime_cond_pct'], 0, '%')} if drained or irrigated</span>"
    body = f'''<header>
  <div class="wrap">
    <p class="crumb"><a href="/">Land Finder</a> › <a href="/{r['st'].lower()}/">{e(st_name)}</a> › {e(cname)}</p>
    <h1>{e(cname)}, {e(st_name)}</h1>
    <p class="lede">Population {fmt(r['pop'])} · {fmt(r['density'])} people per square mile · {fmt(r['land_sqmi'])} square miles. The facts that matter for buying land and living on it, from public datasets.</p>
    <button class="theme" id="themeBtn" type="button" aria-label="Switch light or dark">Light / dark</button>
  </div>
</header>
<main class="wrap">
  <div class="buttons">
    <a class="btn" href="/#county={r['fips']}">Score it on the map<small>set what matters to you and compare</small></a>
    <a class="btn ghost" href="/parcel.html#{r['lat']:.4f},{r['lon']:.4f},10">Check a parcel's soil and water<small>type an address or draw a border</small></a>
  </div>

  <section class="card"><h2>Rules</h2><ul class="facts">
    {fact('County zoning', f"{e(ZWORD.get(r['zoning'], 'Unknown'))} <span class=\"src\">{e(zflag(r))}</span>" + (f"<div class=\"src\">{e(r['zoning_note'])}</div>" if r['zoning_note'] else ''),
          f'<a href="{e(r["zoning_source"])}" rel="noopener">Source</a>' if r['zoning_source'] else '')}
    {state_law(S)}
  </ul><p class="note"><a href="/{r['st'].lower()}/">Every county in {e(st_name)}</a></p></section>

  <section class="card"><h2>Land and water</h2><ul class="facts">
    {fact('Farm land value', money(r['farm_value_acre']) + (' per acre' if r['farm_value_acre'] is not None else ''), 'USDA Census of Agriculture 2022, land and buildings')}
    {fact('Rain per year', fmt(r['precip_in'], 1, ' in.'), 'NOAA nClimDiv, 1991–2020 average')}
    {fact('Growing season', fmt(r['growing_days'], 0, ' frost-free days'), f"NOAA 1991–2020 normals, {e(r['growing_station'])} ({r['growing_station_mi']} mi)" if r['growing_station'] else 'NOAA 1991–2020 normals')}
    {fact('Average temperature / January low', f"{fmt(r['tavg_f'], 1, '°F')} / {fmt(r['jan_tmin_f'], 1, '°F')}", 'NOAA nClimDiv, 1991–2020')}
    {fact('Well depth, median', fmt(r['well_depth_med_ft'], 0, ' ft') + (f" <span class=\"src\">({r['well_n']} USGS wells)</span>" if r['well_n'] else ''), 'USGS well inventory')}
    {fact('Prime farmland', prime, 'USDA NRCS soil survey')}
    {fact('Public land', fmt(r['public_land_pct'], 1, '% of county'), 'USGS PAD-US 4.1')}
  </ul></section>

  <section class="card"><h2>Elbow room and access</h2><ul class="facts">
    {fact('Nearest town of 5,000+', f"{e(r['town5k_name'])} <span class=\"src\">{fmt(r['town5k_mi'])} mi from the county's center</span>" if r['town5k_name'] else 'no data', 'Census places; straight-line, not road miles')}
    {fact('Nearest city of 50,000+', f"{e(r['city50k_name'])} <span class=\"src\">{fmt(r['city50k_mi'])} mi</span>" if r['city50k_name'] else 'no data', 'Census places, from the county center')}
    {fact('Nearest hospital', f"{e(r['hosp_name'])} <span class=\"src\">{fmt(r['hosp_mi'])} mi</span>" if r['hosp_name'] else 'no data', 'HIFLD hospitals, general and critical access')}
    {fact('Homes with cable, fiber or DSL', fmt(r['broadband_pct'], 0, '%'), 'Census ACS 2023 subscriptions')}
    {fact('Amish and Mennonite', f"{fmt(r['amish_districts'])} church districts here, {fmt(r['plain_districts_40mi'])} within 40 mi", 'Young Center, Elizabethtown College, 2026')}
  </ul></section>

  <section class="card"><h2>Money and hazards</h2><ul class="facts">
    {fact('Property tax, effective', fmt(r['tax_rate_pct'], 2, '%') + (f" <span class=\"src\">median {money(r['tax_med'])} on a {money(r['home_value_med'])} home</span>" if r['tax_med'] else ''), 'Census ACS 2023, owner-occupied homes')}
    {fact('Overall natural-hazard risk', f"{fmt(r['risk_score'])} <span class=\"src\">{e(r['risk_rating'] or '')}</span>", 'FEMA National Risk Index, 0 low to 100 high')}
    {fact('Tornado / wildfire', f"{fmt(r['tornado'])} / {fmt(r['wildfire'])}", 'FEMA National Risk Index')}
    {fact('Flood inland / coastal', f"{fmt(r['flood_inland'])} / {'n/a' if r['flood_coastal'] is None else fmt(r['flood_coastal'])}", 'FEMA National Risk Index')}
    {fact('Drought / hurricane / winter', f"{fmt(r['drought'])} / {'n/a' if r['hurricane'] is None else fmt(r['hurricane'])} / {fmt(r['winter'])}", 'FEMA National Risk Index')}
  </ul></section>

  <section class="card"><h2>Records to check before you buy</h2>
    <div class="buttons">
      {f'<a class="btn ghost" href="{e(r["website"])}" rel="noopener">County website<small>official site</small></a>' if r['website'] else ''}
      <a class="btn ghost" href="{netr}" rel="noopener">Public records directory<small>assessor, recorder, tax links</small></a>
      <a class="btn ghost" href="{lf}" rel="noopener">Land &amp; Farm listings<small>land for sale in {e(cname)}</small></a>
    </div>
    <p class="note">Pull the property card, read the deed and plat, check for back taxes, ask about ag-use rules, and ask the health department what a septic permit needs, in that order. <a href="/#sign">The full checklist</a>.</p>
  </section>

  <section class="card"><h2>Nearby counties</h2><ul class="near">
    {''.join(f'<li><a href="/{paths[o["fips"]]}">{e(o["name"])}, {o["st"]}</a> <span class="src">{d:.0f} mi</span></li>' for d, o in near)}
  </ul></section>
</main>
'''
    return HEAD.format(title=e(title), desc=e(desc), url=url, site=SITE) + body + FOOT.format(family=FAMILY, built=BUILT) + SCRIPT


def state_page(st, rows):
    S = STATES.get(st, {})
    st_name = S.get('name') or st
    url = f'{SITE}/{st.lower()}/'
    title = f'{st_name} counties for homesteading | Land Finder'
    desc = (f'All {len(rows)} counties in {st_name} with land price per acre, rain, growing season, well depth and zoning, '
            f'plus {st_name} homeschool, carry, right-to-farm and rainwater law. Free, from public data.')
    trs = ''.join(
        f'<tr><td><a href="/{paths[r["fips"]]}">{e(r["name"])}</a></td><td class="num">{money(r["farm_value_acre"])}</td>'
        f'<td class="num">{fmt(r["precip_in"], 0, " in")}</td><td class="num">{fmt(r["growing_days"], 0, " days")}</td>'
        f'<td class="num">{fmt(r["well_depth_med_ft"], 0, " ft")}</td><td>{e(ZWORD.get(r["zoning"], "Unknown").replace("Unknown, verify with the county", "Verify"))}</td></tr>'
        for r in sorted(rows, key=lambda x: x['name']))
    body = f'''<header>
  <div class="wrap">
    <p class="crumb"><a href="/">Land Finder</a> › {e(st_name)}</p>
    <h1>{e(st_name)}</h1>
    <p class="lede">{len(rows)} counties with the facts that matter for buying land and living on it. Open one for the full picture, or score them all on the map.</p>
    <button class="theme" id="themeBtn" type="button" aria-label="Switch light or dark">Light / dark</button>
  </div>
</header>
<main class="wrap">
  <div class="buttons"><a class="btn" href="/">Score every county on the map<small>set what matters to you</small></a></div>
  <section class="card"><h2>{e(st_name)} law for homesteaders</h2><ul class="facts">{state_law(S)}</ul></section>
  <section class="card"><h2>Counties</h2>
    <div class="tablewrap"><table><thead><tr><th>County</th><th class="num">Farm land $/acre</th><th class="num">Rain</th><th class="num">Growing season</th><th class="num">Well depth</th><th>County zoning</th></tr></thead>
    <tbody>{trs}</tbody></table></div>
    <p class="note">Land value is the USDA 2022 farm figure, land and buildings. Rain and season are 1991–2020 averages. Zoning marked Verify is not confirmed for that county.</p>
  </section>
  <section class="card"><h2>Other states</h2><p class="statelist">{STATE_LINKS}</p></section>
</main>
'''
    return HEAD.format(title=e(title), desc=e(desc), url=url, site=SITE) + body + FOOT.format(family=FAMILY, built=BUILT) + SCRIPT


SCRIPT = '''<script>
(function () {
  var b = document.getElementById('themeBtn'); if (!b) return;
  b.addEventListener('click', function () {
    var r = document.documentElement, cur = r.getAttribute('data-theme');
    var dark = cur === 'dark' || (!cur && matchMedia('(prefers-color-scheme: dark)').matches);
    var next = dark ? 'light' : 'dark'; r.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) {}
  });
})();
</script>
'''

by_state = {}
for r in ROWS:
    by_state.setdefault(r['st'], []).append(r)
STATE_LINKS = ' · '.join(f'<a href="/{st.lower()}/">{e(STATES.get(st, {}).get("name") or st)}</a>' for st in sorted(by_state, key=lambda s: STATES.get(s, {}).get('name') or s))

# clear old generated state folders (two-letter lower-case dirs only), then write
for name in os.listdir(ROOT):
    if re.fullmatch(r'[a-z]{2}', name) and os.path.isdir(os.path.join(ROOT, name)) and os.path.exists(os.path.join(ROOT, name, 'index.html')):
        shutil.rmtree(os.path.join(ROOT, name))
n = 0
for st, rows in by_state.items():
    d = os.path.join(ROOT, st.lower()); os.makedirs(d, exist_ok=True)
    io.open(os.path.join(d, 'index.html'), 'w', encoding='utf-8', newline='\n').write(state_page(st, rows))
    for r in rows:
        cd = os.path.join(ROOT, paths[r['fips']]); os.makedirs(cd, exist_ok=True)
        io.open(os.path.join(cd, 'index.html'), 'w', encoding='utf-8', newline='\n').write(county_page(r))
        n += 1

urls = [(f'{SITE}/', '1.0'), (f'{SITE}/parcel.html', '0.8')]
urls += [(f'{SITE}/{st.lower()}/', '0.7') for st in sorted(by_state)]
urls += [(f"{SITE}/{paths[r['fips']]}", '0.6') for r in sorted(ROWS, key=lambda x: paths[x['fips']])]
xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
xml += [f'  <url><loc>{u}</loc><lastmod>{BUILT}</lastmod><priority>{p}</priority></url>' for u, p in urls]
xml.append('</urlset>')
io.open(os.path.join(ROOT, 'sitemap.xml'), 'w', encoding='utf-8', newline='\n').write('\n'.join(xml) + '\n')
io.open(os.path.join(ROOT, 'robots.txt'), 'w', encoding='utf-8', newline='\n').write(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
# the map page links every state so crawlers can reach the county pages
io.open(os.path.join(ROOT, 'data', 'state_links.html'), 'w', encoding='utf-8', newline='\n').write(STATE_LINKS + '\n')
print(f'{len(by_state)} state pages, {n} county pages, {len(urls)} sitemap URLs')
