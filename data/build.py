#!/usr/bin/env python3
"""Build data/counties.json (and the helper files the page loads) from public datasets.

Run from the repo root:   python -I data/build.py
Downloads live in ./downloads (see data/sources.md for every URL). Nothing in this
script talks to the network; fetch_all.sh does the downloading.

Only the Python standard library is used, plus pyshp (pip install pyshp) for the
county boundary file.
"""
import csv, glob, gzip, io, json, math, os, re, statistics, sys, tarfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DL = os.path.join(ROOT, "downloads")
MANUAL = os.path.join(ROOT, "data", "manual")
OUT = os.path.join(ROOT, "data")

def p(*parts):
    return os.path.join(DL, *parts)

# ---------------------------------------------------------------- state tables
STATES = {
 "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC",
 "12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY",
 "22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT",
 "31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH",
 "40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT",
 "50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"}
ABBR2FIPS = {v: k for k, v in STATES.items()}
STATE_NAMES = {
 "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado",
 "CT":"Connecticut","DE":"Delaware","DC":"District of Columbia","FL":"Florida","GA":"Georgia",
 "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky",
 "LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota",
 "MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
 "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota",
 "OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island",
 "SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont",
 "VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming"}
# NOAA nClimDiv uses its own 01-50 state codes.
CLIMDIV2FIPS = {
 "01":"01","02":"04","03":"05","04":"06","05":"08","06":"09","07":"10","08":"12","09":"13","10":"16",
 "11":"17","12":"18","13":"19","14":"20","15":"21","16":"22","17":"23","18":"24","19":"25","20":"26",
 "21":"27","22":"28","23":"29","24":"30","25":"31","26":"32","27":"33","28":"34","29":"35","30":"36",
 "31":"37","32":"38","33":"39","34":"40","35":"41","36":"42","37":"44","38":"45","39":"46","40":"47",
 "41":"48","42":"49","43":"50","44":"51","45":"53","46":"54","47":"55","48":"56","49":"15","50":"02"}

def haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.8
    a = math.radians(lat1); b = math.radians(lat2)
    d = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(d))

class Grid:
    """Cheap nearest-point lookup: points bucketed in 1-degree cells."""
    def __init__(self, pts):
        self.cells = defaultdict(list)
        for pt in pts:  # (lat, lon, payload)
            self.cells[(int(math.floor(pt[0])), int(math.floor(pt[1])))].append(pt)
    def nearest(self, lat, lon, max_ring=12):
        best = None
        ci, cj = int(math.floor(lat)), int(math.floor(lon))
        for ring in range(0, max_ring + 1):
            found_any = False
            for i in range(ci - ring, ci + ring + 1):
                for j in range(cj - ring, cj + ring + 1):
                    if max(abs(i - ci), abs(j - cj)) != ring:
                        continue
                    for pt in self.cells.get((i, j), ()):
                        found_any = True
                        d = haversine_mi(lat, lon, pt[0], pt[1])
                        if best is None or d < best[0]:
                            best = (d, pt[2])
            # once we have a candidate and have searched one ring beyond its distance, stop
            if best is not None and ring >= 1 and best[0] < (ring - 1) * 55:
                break
        return best
    def within(self, lat, lon, miles):
        out = []
        ring = int(miles / 55) + 1
        ci, cj = int(math.floor(lat)), int(math.floor(lon))
        for i in range(ci - ring, ci + ring + 1):
            for j in range(cj - ring, cj + ring + 1):
                for pt in self.cells.get((i, j), ()):
                    d = haversine_mi(lat, lon, pt[0], pt[1])
                    if d <= miles:
                        out.append((d, pt[2]))
        return sorted(out)

def num(s):
    if s is None: return None
    s = str(s).strip().replace(",", "")
    if s in ("", "(D)", "(Z)", "(NA)", "-", "null", "None"): return None
    try: return float(s)
    except ValueError: return None

def r1(x): return None if x is None else round(x, 1)
def r2(x): return None if x is None else round(x, 2)

# ---------------------------------------------------------------- 1. counties
def load_counties():
    rows = {}
    with open(p("census", "2023_Gaz_counties_national.txt"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            r = {k.strip(): (v.strip() if v else v) for k, v in r.items()}
            fips = r["GEOID"]
            if fips[:2] not in STATES: continue
            rows[fips] = dict(fips=fips, name=r["NAME"], st=r["USPS"], lat=float(r["INTPTLAT"]),
                              lon=float(r["INTPTLONG"]), land_sqmi=float(r["ALAND_SQMI"]))
    return rows

def add_population(c):
    with open(p("census", "co-est2024-alldata.csv"), encoding="latin-1") as f:
        for r in csv.DictReader(f):
            if r["SUMLEV"] != "050": continue
            fips = r["STATE"] + r["COUNTY"]
            if fips in c:
                c[fips]["pop"] = int(r["POPESTIMATE2024"])
    for row in c.values():
        row.setdefault("pop", None)
        row["density"] = r1(row["pop"] / row["land_sqmi"]) if row["pop"] and row["land_sqmi"] else None

# ---------------------------------------------------------------- 2. farmland value (USDA)
def add_farm_value(c):
    with open(p("usda", "agland_value_county.txt"), encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for r in rd:
            if r["DOMAIN_DESC"] != "TOTAL" or not r["COUNTY_ANSI"]: continue
            fips = r["STATE_FIPS_CODE"] + r["COUNTY_ANSI"]
            if fips in c:
                c[fips]["farm_value_acre"] = num(r["VALUE"])
    for row in c.values(): row.setdefault("farm_value_acre", None)

# ---------------------------------------------------------------- 3. climate (NOAA nClimDiv, 1991-2020)
def read_climdiv(fname, element, years=(1991, 2020)):
    """Return {fips: [year -> [12 monthly values]]} for one element code."""
    out = defaultdict(dict)
    with open(fname, encoding="utf-8") as f:
        for line in f:
            if line[5:7] != element: continue
            yr = int(line[7:11])
            if yr < years[0] or yr > years[1]: continue
            st = CLIMDIV2FIPS.get(line[0:2])
            if not st: continue
            fips = st + line[2:5]
            vals = [float(line[11 + 7 * i: 18 + 7 * i]) for i in range(12)]
            out[fips][yr] = vals
    return out

def add_climate(c):
    pf = glob.glob(p("noaa", "climdiv-pcpncy-*"))[0]
    tf = glob.glob(p("noaa", "climdiv-tmpccy-*"))[0]
    nf = glob.glob(p("noaa", "climdiv-tmincy-*"))[0]
    pr = read_climdiv(pf, "01"); ta = read_climdiv(tf, "02"); tn = read_climdiv(nf, "28")
    for fips, row in c.items():
        yrs = [sum(v) for v in pr.get(fips, {}).values() if all(x > -9 for x in v)]
        row["precip_in"] = r1(statistics.mean(yrs)) if len(yrs) >= 20 else None
        yrs = [statistics.mean(v) for v in ta.get(fips, {}).values() if all(x > -90 for x in v)]
        row["tavg_f"] = r1(statistics.mean(yrs)) if len(yrs) >= 20 else None
        jan = [v[0] for v in tn.get(fips, {}).values() if v[0] > -90]
        row["jan_tmin_f"] = r1(statistics.mean(jan)) if len(jan) >= 20 else None

# ---------------------------------------------------------------- 4. growing season (NOAA normals stations)
def add_growing_season(c):
    pts = []
    for fn in glob.glob(p("noaa", "normals", "US*.csv")):
        with open(fn, encoding="utf-8", errors="replace") as f:
            rd = csv.DictReader(f)
            row = next(rd, None)
            if not row: continue
            gsl = num(row.get("ANN-TMIN-PRBGSL-T32FP50"))
            if gsl is None: continue
            try:
                lat = float(row["LATITUDE"]); lon = float(row["LONGITUDE"])
            except (KeyError, ValueError):
                continue
            pts.append((lat, lon, (gsl, row["STATION"], row["NAME"].strip())))
    g = Grid(pts)
    for fips, row in c.items():
        near = g.within(row["lat"], row["lon"], 60)[:3]
        if near:
            row["growing_days"] = int(round(statistics.median([n[1][0] for n in near])))
            row["growing_station"] = near[0][1][2]
            row["growing_station_mi"] = r1(near[0][0])
        else:
            row["growing_days"] = None; row["growing_station"] = None; row["growing_station_mi"] = None
    return len(pts)

# ---------------------------------------------------------------- 5. groundwater (USGS NWIS well depths)
def add_wells(c):
    depths = defaultdict(list)
    for fn in glob.glob(p("usgs", "nwis_gw_*.rdb")):
        hdr = None
        with open(fn, encoding="latin-1") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.rstrip("\n").split("\t")
                if hdr is None:
                    hdr = parts; continue
                if parts[0] != "USGS": continue  # skips the format row (5s 15s ...)
                r = dict(zip(hdr, parts))
                d = num(r.get("well_depth_va"))
                if d is None or d <= 0 or d > 5000: continue
                fips = r.get("state_cd", "") + r.get("county_cd", "")
                if len(fips) == 5: depths[fips].append(d)
    for fips, row in c.items():
        d = depths.get(fips, [])
        row["well_n"] = len(d)
        row["well_depth_med_ft"] = int(statistics.median(d)) if len(d) >= 5 else None

# ---------------------------------------------------------------- 6. prime farmland (NRCS SSURGO via SDA)
def add_prime(c):
    acres = defaultdict(lambda: defaultdict(float))
    for fn in glob.glob(p("nrcs", "farmland_*.json")):
        with open(fn, encoding="utf-8") as f:
            d = json.load(f)
        for area, name, cls, ac in d.get("Table", []):
            m = re.fullmatch(r"([A-Z]{2})(\d{3})", area)
            if not m or m.group(1) not in ABBR2FIPS: continue
            fips = ABBR2FIPS[m.group(1)] + m.group(2)
            cls = cls or ""
            if cls == "All areas are prime farmland": k = "prime"
            elif cls.startswith("Prime farmland if"): k = "cond"
            elif cls.startswith("Farmland of statewide"): k = "statewide"
            else: k = "other"
            acres[fips][k] += num(ac) or 0.0
    for fips, row in c.items():
        a = acres.get(fips)
        tot = sum(a.values()) if a else 0
        if tot > 0:
            row["prime_pct"] = r1(100 * a["prime"] / tot)
            row["prime_cond_pct"] = r1(100 * a["cond"] / tot)
        else:
            row["prime_pct"] = None; row["prime_cond_pct"] = None

# ---------------------------------------------------------------- 7. towns and hospitals (distance from county center)
def load_place_pops():
    pops = {}
    with open(p("census", "acsdt5y2023-b01003.dat"), encoding="utf-8") as f:
        for line in f:
            if not line.startswith("1600000US"): continue
            geo, e, _m = line.rstrip("\n").split("|")[:3]
            pops[geo[9:]] = num(e)
    return pops

def load_places():
    pops = load_place_pops()
    places = []
    with open(p("census", "2023_Gaz_place_national.txt"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            r = {k.strip(): (v.strip() if v else v) for k, v in r.items()}
            if r["USPS"] not in ABBR2FIPS: continue
            pop = pops.get(r["GEOID"])
            if not pop: continue
            name = re.sub(r" (city|town|village|CDP|borough|municipality|comunidad|zona urbana|urban county|consolidated government|metro government|metropolitan government|unified government)( \(balance\))?$", "", r["NAME"])
            places.append(dict(name=name, st=r["USPS"], lat=float(r["INTPTLAT"]), lon=float(r["INTPTLONG"]), pop=int(pop)))
    return places

def add_towns(c, places):
    g5 = Grid([(x["lat"], x["lon"], x) for x in places if x["pop"] >= 5000])
    g50 = Grid([(x["lat"], x["lon"], x) for x in places if x["pop"] >= 50000])
    for fips, row in c.items():
        n = g5.nearest(row["lat"], row["lon"])
        row["town5k_mi"] = r1(n[0]) if n else None
        row["town5k_name"] = f'{n[1]["name"]}, {n[1]["st"]}' if n else None
        n = g50.nearest(row["lat"], row["lon"])
        row["city50k_mi"] = r1(n[0]) if n else None
        row["city50k_name"] = f'{n[1]["name"]}, {n[1]["st"]}' if n else None

def add_hospitals(c):
    pts = []; src_dates = set()
    for fn in glob.glob(p("hifld", "hospitals_*.json")):
        with open(fn, encoding="utf-8") as f:
            for ft in json.load(f)["features"]:
                a = ft["attributes"]
                if a.get("STATUS") != "OPEN": continue
                if a.get("TYPE") not in ("GENERAL ACUTE CARE", "CRITICAL ACCESS"): continue
                if a.get("LATITUDE") is None: continue
                src_dates.add((a.get("SOURCEDATE") or "")[:4])
                pts.append((a["LATITUDE"], a["LONGITUDE"], (a["NAME"].title(), a.get("CITY", "").title(), a.get("STATE"))))
    g = Grid(pts)
    for fips, row in c.items():
        n = g.nearest(row["lat"], row["lon"])
        row["hosp_mi"] = r1(n[0]) if n else None
        row["hosp_name"] = f"{n[1][0]} ({n[1][1]}, {n[1][2]})" if n else None
    return len(pts), sorted(d for d in src_dates if d)

# ---------------------------------------------------------------- 8. property tax and broadband (ACS 2023 5-year)
def read_acs(table):
    out = {}
    with open(p("census", f"acsdt5y2023-{table}.dat"), encoding="utf-8") as f:
        for line in f:
            if not line.startswith("0500000US"): continue
            parts = line.rstrip("\n").split("|")
            out[parts[0][9:]] = parts[1:]
    return out

def add_acs(c):
    val = read_acs("b25077"); tax = read_acs("b25103"); bb = read_acs("b28002")
    for fips, row in c.items():
        v = num(val.get(fips, [None])[0]); t = num(tax.get(fips, [None])[0])
        row["home_value_med"] = int(v) if v else None
        row["tax_med"] = int(t) if t else None
        row["tax_rate_pct"] = r2(100 * t / v) if v and t else None
        b = bb.get(fips)
        # B28002: E001 total households; E007 broadband such as cable, fiber optic or DSL
        if b:
            tot = num(b[0]); cab = num(b[12])
            row["broadband_pct"] = r1(100 * cab / tot) if tot and cab is not None else None
        else:
            row["broadband_pct"] = None

# ---------------------------------------------------------------- 9. FEMA National Risk Index
def add_fema(c):
    keep = {"RISK_SCORE": "risk_score", "RISK_RATNG": "risk_rating", "IFLD_RISKS": "flood_inland",
            "CFLD_RISKS": "flood_coastal", "WFIR_RISKS": "wildfire", "TRND_RISKS": "tornado",
            "DRGT_RISKS": "drought", "HRCN_RISKS": "hurricane", "ERQK_RISKS": "earthquake",
            "WNTW_RISKS": "winter", "HAIL_RISKS": "hail"}
    ver = None
    for fn in glob.glob(p("fema", "nri_*.json")):
        with open(fn, encoding="utf-8") as f:
            for ft in json.load(f)["features"]:
                a = ft["attributes"]; fips = a["STCOFIPS"]
                ver = a.get("NRI_VER") or ver
                if fips not in c: continue
                for k, v in keep.items():
                    x = a.get(k)
                    c[fips][v] = r1(x) if isinstance(x, (int, float)) else (x if x else None)
    for row in c.values():
        for v in keep.values(): row.setdefault(v, None)
    return ver

# ---------------------------------------------------------------- 10. manual inputs
def read_json(name):
    fn = os.path.join(MANUAL, name)
    if not os.path.exists(fn): return None
    with open(fn, encoding="utf-8") as f:
        return json.load(f)

def add_public_land(c):
    fn = os.path.join(MANUAL, "public_land.csv")
    got = {}
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                got[r["fips"]] = num(r["public_land_pct"])
    for fips, row in c.items(): row["public_land_pct"] = got.get(fips)

def add_amish(c):
    d = read_json("amish.json")
    per = defaultdict(lambda: {"amish": 0.0, "mennonite": 0.0, "names": [], "unknown": 0})
    if d:
        for s in d.get("settlements", []):
            f = s.get("fips")
            if not f or f not in c: continue
            grp = "mennonite" if (s.get("group") or "").lower().startswith("menn") else "amish"
            if s.get("districts") is not None: per[f][grp] += float(s["districts"])
            else: per[f]["unknown"] += 1
            if s.get("name") and s["name"] not in per[f]["names"]: per[f]["names"].append(s["name"])
    for fips, row in c.items():
        a = per.get(fips)
        row["amish_districts"] = r1(a["amish"]) if a else 0
        row["mennonite_districts"] = r1(a["mennonite"]) if a else 0
        row["plain_settlements"] = "; ".join(a["names"]) if a else None
    # church districts within 40 miles of the county center (county itself included)
    g = Grid([(c[f]["lat"], c[f]["lon"], f) for f in per if f in c])
    for fips, row in c.items():
        near = g.within(row["lat"], row["lon"], 40)
        tot = sum(per[f]["amish"] + per[f]["mennonite"] for _d, f in near)
        row["plain_districts_40mi"] = r1(tot)
    return d

THIRD_PARTY_LISTS = {"MO", "AR"}

def add_zoning(c):
    state = read_json("zoning_state.json") or {"states": {}}
    verified = {}
    for fn in sorted(glob.glob(os.path.join(MANUAL, "zoning_??.json"))):
        with open(fn, encoding="utf-8") as f:
            d = json.load(f)
        for r in d.get("counties", []):
            if r.get("fips"): verified[r["fips"]] = r
    for fips, row in c.items():
        v = verified.get(fips)
        sp = state["states"].get(row["st"], {})
        pat = sp.get("pattern", "unknown")
        if v:
            row["zoning"] = v["zoning"]; row["zoning_level"] = v.get("level", "state_list")
            row["zoning_source"] = v.get("source_url"); row["zoning_note"] = v.get("note")
            if row["zoning_level"] == "state_list":
                # Missouri and Arkansas have no official statewide list; the fallback lists are third-party
                if row["st"] in THIRD_PARTY_LISTS: row["zoning_level"] = "third_party_list"
                # a county the list does not name, whose own site could not be read, is unverified
                n = (v.get("note") or "").lower()
                if any(k in n for k in ("not named", "not on state list", "unverif", "no county website", "not listed", "unreachable")):
                    row["zoning"] = "verify"
        else:
            row["zoning_level"] = "state_pattern"; row["zoning_source"] = sp.get("source_url"); row["zoning_note"] = sp.get("note")
            if pat == "none_statewide": row["zoning"] = "none"
            elif pat == "all_zoned": row["zoning"] = "county"
            elif pat == "municipal": row["zoning"] = "municipal"
            else: row["zoning"] = "verify"
        row["zoning_pattern"] = pat
    return state, len(verified)

def add_websites(c):
    sites = {}
    fn = p("wikidata", "county_sites.csv")
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["site"] and r["fips"] not in sites and r["site"].startswith("http"):
                    sites[r["fips"]] = r["site"]
    for fips, row in c.items(): row["website"] = sites.get(fips)

# ---------------------------------------------------------------- 11. map and lookup helpers
def write_geojson():
    import shapefile  # pyshp
    sf = shapefile.Reader(p("shapes", "cb_2023_us_county_20m.shp"))
    fields = [f[0] for f in sf.fields[1:]]
    feats = []
    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        if rec["STATEFP"] not in STATES: continue
        geom = sr.shape.__geo_interface__
        def rnd(coords):
            if isinstance(coords[0], (int, float)): return [round(coords[0], 3), round(coords[1], 3)]
            return [rnd(x) for x in coords]
        feats.append({"type": "Feature", "id": rec["GEOID"], "properties": {}, "geometry": {"type": geom["type"], "coordinates": rnd(geom["coordinates"])}})
    with open(os.path.join(OUT, "counties.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, separators=(",", ":"))
    return len(feats)

def write_places(places):
    keep = sorted([x for x in places if x["pop"] >= 1000], key=lambda x: -x["pop"])
    rows = [[x["name"], x["st"], round(x["lat"], 3), round(x["lon"], 3), x["pop"]] for x in keep]
    with open(os.path.join(OUT, "places.json"), "w", encoding="utf-8") as f:
        json.dump({"fields": ["name", "st", "lat", "lon", "pop"], "rows": rows}, f, separators=(",", ":"))
    return len(rows)

def write_zips():
    z = {}
    with open(p("census", "2023_Gaz_zcta_national.txt"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            r = {k.strip(): (v.strip() if v else v) for k, v in r.items()}
            z[r["GEOID"]] = [round(float(r["INTPTLAT"]), 3), round(float(r["INTPTLONG"]), 3)]
    with open(os.path.join(OUT, "zips.json"), "w", encoding="utf-8") as f:
        json.dump(z, f, separators=(",", ":"))
    return len(z)

# ---------------------------------------------------------------- main
FIELDS = ["fips","name","st","lat","lon","land_sqmi","pop","density",
          "farm_value_acre","precip_in","tavg_f","jan_tmin_f","growing_days","growing_station","growing_station_mi",
          "well_depth_med_ft","well_n","prime_pct","prime_cond_pct",
          "town5k_mi","town5k_name","city50k_mi","city50k_name","hosp_mi","hosp_name",
          "home_value_med","tax_med","tax_rate_pct","broadband_pct",
          "risk_score","risk_rating","flood_inland","flood_coastal","wildfire","tornado","drought","hurricane","earthquake","winter","hail",
          "amish_districts","mennonite_districts","plain_settlements","plain_districts_40mi","public_land_pct",
          "zoning","zoning_level","zoning_pattern","zoning_source","zoning_note","website"]

def main():
    c = load_counties(); print(len(c), "counties")
    add_population(c); print("population done")
    add_farm_value(c); print("farm value done")
    add_climate(c); print("climate done")
    nst = add_growing_season(c); print("growing season done,", nst, "stations")
    add_wells(c); print("wells done")
    add_prime(c); print("prime farmland done")
    places = load_places(); add_towns(c, places); print("towns done,", len(places), "places")
    nh, hdates = add_hospitals(c); print("hospitals done,", nh, "open general/critical-access hospitals, source years", hdates[:1], "-", hdates[-1:])
    add_acs(c); print("acs done")
    ver = add_fema(c); print("fema done,", ver)
    add_public_land(c); print("public land done")
    amish = add_amish(c); print("amish done")
    zstate, nver = add_zoning(c); print("zoning done,", nver, "verified counties")
    add_websites(c); print("websites done")

    states_law = read_json("states.json") or {"states": {}}
    state_block = {}
    for ab in STATE_NAMES:
        law = states_law["states"].get(ab, {})
        zs = zstate["states"].get(ab, {})
        state_block[ab] = {"name": STATE_NAMES[ab],
            "homeschool": law.get("homeschool"), "homeschool_note": law.get("homeschool_note"),
            "carry": law.get("carry"), "carry_note": law.get("carry_note"),
            "right_to_farm": law.get("right_to_farm"), "right_to_farm_note": law.get("right_to_farm_note"),
            "rainwater": law.get("rainwater"), "rainwater_note": law.get("rainwater_note"),
            "offgrid_note": law.get("offgrid_note"),
            "income_tax_top_rate": law.get("income_tax_top_rate"), "income_tax_note": law.get("income_tax_note"),
            "zoning_pattern": zs.get("pattern"), "zoning_note": zs.get("note"), "zoning_estimate": zs.get("unzoned_estimate"),
            "zoning_source": zs.get("source_url"), "zoning_source_name": zs.get("source_name")}

    rows = [[c[f].get(k) for k in FIELDS] for f in sorted(c)]
    # coverage report
    cov = {}
    for i, k in enumerate(FIELDS):
        cov[k] = sum(1 for r in rows if r[i] is not None)
    out = {"built": "2026-11-13", "n": len(rows), "fields": FIELDS, "rows": rows, "states": state_block,
           "sources_note": "See data/sources.md for every dataset, date and URL.",
           "fema_version": ver, "coverage": cov,
           "state_sources": {"laws": states_law.get("sources"), "zoning_checked": zstate.get("checked"),
                             "amish": (amish or {}).get("source"), "amish_method": (amish or {}).get("method")}}
    with open(os.path.join(OUT, "counties.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print("counties.json written;", os.path.getsize(os.path.join(OUT, "counties.json")) // 1024, "KB")
    print("coverage:", json.dumps(cov))
    print("geojson features:", write_geojson())
    print("places:", write_places(places))
    print("zips:", write_zips())

if __name__ == "__main__":
    main()
