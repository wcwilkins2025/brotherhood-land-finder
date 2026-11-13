# Sources

Every dataset the Brotherhood Land Finder uses, with its date and URL. All are public
files or keyless public APIs. Nothing needed an account or a paid key. Downloaded and
built 2026-11-13 by `data/fetch_all.sh` and `data/build.py`.

Geography: the 3,144 counties and county equivalents of the 50 states and DC as the
Census Bureau defines them in 2023. Connecticut is its nine planning regions, not the
old eight counties; datasets still keyed to the old counties (NOAA climate, NRCS soils,
USDA farm values) show "no data" for Connecticut.

## County rows

| Field(s) | Dataset | Date | URL | How it was used |
|---|---|---|---|---|
| `fips`, `name`, `st`, `lat`, `lon`, `land_sqmi` | Census Bureau, 2023 Gazetteer, counties | 2023 | https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip | County list, internal point (center), land area |
| `pop`, `density` | Census Bureau, Vintage 2024 county population estimates (`co-est2024-alldata.csv`) | July 1, 2024 | https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv | `POPESTIMATE2024`; density = population / land square miles |
| `farm_value_acre` | USDA NASS, 2022 Census of Agriculture, Quick Stats bulk file | 2022 (file dated 2024-02-14) | https://www.nass.usda.gov/sites/default/files/datasets/qs.census2022.txt.gz | Item "AG LAND, INCL BUILDINGS - ASSET VALUE, MEASURED IN $ / ACRE", county level, domain TOTAL. "(D)" (withheld) becomes no data. This is the average value of farm land and buildings per acre as reported by farm operators, not a listing price. |
| `precip_in`, `tavg_f`, `jan_tmin_f` | NOAA NCEI nClimDiv county dataset (`climdiv-pcpncy`, `climdiv-tmpccy`, `climdiv-tmincy`, version 1.0.0, release 2026-11-05) | 1895 to present | https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/ | 1991 to 2020 averages: annual precipitation total, annual mean temperature, January mean minimum. Counties need at least 20 complete years. nClimDiv is gridded from station data, so small counties share values with neighbors. |
| `growing_days`, `growing_station`, `growing_station_mi` | NOAA NCEI, U.S. Climate Normals 1991-2020, annual/seasonal, by station | 1991-2020 (archive dated 2023-04-04) | https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/archive/us-climate-normals_1991-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz | Variable `ANN-TMIN-PRBGSL-T32FP50` (median length of the frost-free season at 32 °F). The county value is the median of the up to three nearest stations within 60 miles of the county center; the panel names the nearest station and its distance. 7,247 stations report the variable. |
| `well_depth_med_ft`, `well_n` | USGS National Water Information System, site inventory, groundwater sites (`siteType=GW`, expanded output) | Inventory as of 2026-11-13 | https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd=XX&siteType=GW&siteOutput=expanded | Median `well_depth_va` of USGS-inventoried wells in the county; shown only where 5 or more wells have a depth. USGS wells skew toward monitoring, irrigation and public-supply wells, so the median can run deeper than a typical house well. State well-log databases are more complete and are where a buyer should look next. |
| `prime_pct`, `prime_cond_pct` | USDA NRCS, SSURGO soil survey via Soil Data Access (tables `legend`, `mapunit`, column `farmlndcl`) | Current SSURGO (queried 2026-11-13) | https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest | Acres of map units classed "All areas are prime farmland" (prime) and "Prime farmland if ..." (conditional) divided by all mapped acres in the survey area. Only survey areas whose symbol is a county code (for example MO225) are used; counties covered by multi-county survey areas (common in Georgia, Kentucky, Texas, the West) show no data. |
| `town5k_mi`, `town5k_name`, `city50k_mi`, `city50k_name` | Census Bureau, 2023 Gazetteer, places; ACS 2019-2023 5-year table B01003 (total population) | 2023 | https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip ; https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b01003.dat | Straight-line distance from the county center to the nearest incorporated place or Census Designated Place of 5,000+ (and 50,000+) people. New England towns that are not Census places are not counted. |
| `hosp_mi`, `hosp_name` | HIFLD (Homeland Infrastructure Foundation-Level Data) Hospitals, federal ArcGIS Online copy | Records dated 2014-2017 (service current 2026) | https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Hospitals/FeatureServer/0 | Nearest hospital with status OPEN and type GENERAL ACUTE CARE or CRITICAL ACCESS (5,238 hospitals), straight-line from the county center. HRSA's own download needed an interactive session, so HIFLD was used. Rural hospitals have closed since 2017; confirm the nearest one is still open. |
| `home_value_med`, `tax_med`, `tax_rate_pct` | Census Bureau, ACS 2019-2023 5-year, tables B25077 (median home value) and B25103 (median real estate taxes paid) | 2019-2023 | https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b25077.dat ; .../acsdt5y2023-b25103.dat | Effective property tax rate = median taxes paid / median home value, owner-occupied homes. Agricultural land is usually taxed lower than this. |
| `broadband_pct` | Census Bureau, ACS 2019-2023 5-year, table B28002 (presence and types of internet subscriptions) | 2019-2023 | https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b28002.dat | Share of households with a cable, fiber-optic or DSL subscription (E007 / E001). This is subscription, not availability. See "Not included" for the FCC map. |
| `risk_score`, `risk_rating`, `flood_inland`, `flood_coastal`, `wildfire`, `tornado`, `drought`, `hurricane`, `earthquake`, `winter`, `hail` | FEMA National Risk Index, county layer, official FEMA_NationalRiskIndex ArcGIS service | December 2025 release | https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0 ; documentation https://hazards.fema.gov/nri/ | Risk Index scores (0 to 100 percentile ranks among counties): `RISK_SCORE`, `IFLD_RISKS`, `CFLD_RISKS`, `WFIR_RISKS`, `TRND_RISKS`, `DRGT_RISKS`, `HRCN_RISKS`, `ERQK_RISKS`, `WNTW_RISKS`, `HAIL_RISKS`. The zip on hazards.fema.gov reset every connection, so the same data was read from FEMA's feature service. |
| `amish_districts`, `mennonite_districts`, `plain_settlements`, `plain_districts_40mi` | Young Center for Anabaptist and Pietist Studies, Elizabethtown College, "Amish Population in the United States by State, County, and Settlement, 2026" | 2026 | https://www.etown.edu/centers/young-center/files/Amish-Pop-2026_by-state-and-county.pdf | 705 settlements, 3,229 church districts (matches the Young Center's US total). A settlement spanning several counties is split evenly across them. Old Order Mennonite rows are partial (24 counties) and come from JAPAS articles, GAMEO and Wikipedia; see `data/manual/amish.json` for each row's source. `plain_districts_40mi` sums districts in all counties whose center is within 40 miles. |
| `public_land_pct` | USGS Gap Analysis Project, PAD-US 4.1 Vector Analysis and Summary Statistics, county table | 2025-03-31 | https://www.sciencebase.gov/catalog/item/6759b69fd34edfeb8710a3ea (DOI 10.5066/P96WBCHS) | Acres managed by federal, state, local, regional or territorial agencies divided by county area (land plus water). Tribal, NGO and private conservation land excluded. Details in `data/manual/public_land_broadband_sources.md`. |
| `zoning`, `zoning_level`, `zoning_source`, `zoning_note` | County-by-county verification (see below) | 2026-11-13 | `data/manual/zoning_*.json` | See "Zoning". |
| `zoning_pattern` | State pattern (see below) | 2026-11-13 | `data/manual/zoning_state.json` | See "Zoning". |
| `website` | Wikidata, property P856 (official website) on items with P882 (FIPS county code) | Queried 2026-11-13 | https://query.wikidata.org/sparql | Official county website where Wikidata has one (3,011 of 3,144). Community-edited; a few may be stale. |

## State block (`states` in counties.json)

| Field | Dataset | Date | URL |
|---|---|---|---|
| `homeschool`, `homeschool_note` | HSLDA state law summaries. Level: none (no notice), low (notice only), moderate (notice plus testing, evaluation or a diploma requirement), high (approval or curriculum review). | Read 2026-11-13 | https://hslda.org/legal |
| `carry`, `carry_note` | handgunlaw.us state pages (updated 2026-11-11) and state statutes; permitless-carry dates cross-checked on Wikipedia "Constitutional carry". After Bruen no state is coded may-issue; the nine formerly may-issue states are flagged in the note. | 2026-11 | https://www.handgunlaw.us/ |
| `right_to_farm`, `right_to_farm_note` | National Agricultural Law Center, right-to-farm statute compilation and provisions chart | 2022-2023 | https://nationalaglawcenter.org/state-compilations/right-to-farm/ |
| `rainwater`, `rainwater_note`, `offgrid_note` | State sources where they exist (Colorado State University Extension, Utah Division of Water Rights, Nevada NRS 533.027, Oregon ORS 537.141, Washington Department of Ecology, Texas Water Development Board); other states rest on Rainplan's March 2026 50-state survey (secondary). Off-grid notes from primalsurvivor.net state guides (2022-2023) for 11 states, null elsewhere. | 2025-2026 | See `data/manual/states.json` `sources` |
| `income_tax_top_rate`, `income_tax_note` | Tax Foundation, State Individual Income Tax Rates and Brackets, 2026 | As of 2026-01-01 | https://taxfoundation.org/data/all/state/state-income-tax-rates/ |
| `zoning_pattern`, `zoning_note`, `zoning_estimate`, `zoning_source` | State statutes, state associations of counties, university extension and NACo land-use surveys, one source per state | 2026-11-13 | `data/manual/zoning_state.json` |

## Zoning

No national dataset of county zoning exists. The page scores zoning three ways and
says which one applies to each county:

1. **Verified counties** (`zoning_level` = `county_site` or `state_list`). Five starting states, in
   `data/manual/zoning_MO.json`, `zoning_TN.json`, `zoning_KY.json`, `zoning_AR.json`, plus Texas by statute.
   `county_site` means the status was read on the county's own website (URL recorded per county).
   `state_list` means it comes from an official statewide list:
   - Tennessee: UT Center for Local Planning, Tennessee County Zoning Viewer (layer edited 2026-08-21), cross-checked against the Sycamore Institute, April 2026. 49 counties zoned, 46 none. 56 confirmed on county sites.
   - Kentucky: Kentucky Transportation Cabinet, Planning Units 2010 list (the only per-county list found; KACo's 2025 "Planning and Zoning 101" gives counts of 58 counties with planning and 40 with zoning but no names). 42 county, 11 partial, 67 none. 27 confirmed on county sites. Rows that rest only on the 2010 list are labeled as such.
   - Missouri and Arkansas have **no official statewide list**. The fallback lists are third-party (Bolthole Index, reviewed 2026-06-26, for Missouri; a 2018 Northwest Arkansas Democrat-Gazette article naming the zoned counties for Arkansas) and are labeled `third_party_list` on the page with a "verify" flag. Missouri: 32 counties confirmed on county sites (80 none, 28 county, 7 partial overall). Arkansas: 48 confirmed on county sites (60 none, 12 partial, 3 county overall).
   - Texas: counties have no general zoning authority (Texas Local Government Code, chapter 231 gives narrow exceptions). All 254 counties are "none" by state law.
   Any county the list does not name and whose own site could not be read is marked "verify".
2. **State law settles it** (`zoning_level` = `state_pattern`, pattern `none_statewide` or `all_zoned`).
3. **Everything else is "verify"** and scored from the state's general pattern (mostly none, mixed, mostly zoned, municipal).

## Map and lookups

| File | Dataset | URL |
|---|---|---|
| `counties.geojson` | Census Bureau, 2023 cartographic boundary file, counties, 1:20,000,000 (`cb_2023_us_county_20m`), coordinates rounded to 3 decimals | https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_20m.zip |
| `places.json` | 2023 place gazetteer plus ACS 2023 B01003, places of 1,000+ people | as above |
| `zips.json` | Census Bureau, 2023 Gazetteer, ZIP Code Tabulation Areas (centers) | https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip |
| Map library | d3 7.9.0 from cdnjs (no API key, no tiles, no tracking) | https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js |

## Link kit

Per-county buttons are built from the county name, not from a dataset, because no national list of
assessor, recorder, GIS or health-department URLs exists:

- County website: Wikidata (above).
- Public records directory: NETR Online, `https://publicrecords.netronline.com/state/XX/county/<name>` (free directory of assessor, recorder and tax links; format confirmed 2026-11-13).
- Assessor, GIS, deeds, health department: DuckDuckGo searches with the county and state typed in.
- Land & Farm: `https://www.landandfarm.com/search/<state>/<county>-county-land-for-sale/` (format confirmed 2026-11-13). The site's acreage filter is a form, not a URL parameter, so the user sets 10 to 50 acres after the page opens. Land.com, LandSearch and LandWatch refuse automated reads, so no listings are read or shown.

## Not included (and why)

- **FCC National Broadband Map availability by county.** Every download endpoint requires a browser session (HTTP 401/403 to any client without one). The Census broadband-subscription share stands in and is labeled as such. To add it by hand: download the "Fixed Broadband Availability Summary by Geography Type" CSV from https://broadbandmap.fcc.gov/data-download/nationwide-data, keep county rows for Any Technology (fixed terrestrial), and fill `data/manual/broadband.csv`.
- **USDA NASS Quick Stats API** needs a free key; the bulk file was used instead.
- **Census Bureau API** now requires a key; the summary files on www2.census.gov were used instead.
- **HRSA hospital data** needs an interactive export; HIFLD was used.
- **Old Order Mennonite settlements by county**: no source publishes them; 24 counties were assembled from articles and are marked partial.
- **Groundwater quality or aquifer yield**: no keyless county-level dataset was found; well depth is the only groundwater indicator.
- **Land listing prices**: listing sites block automated reads; the tool links to searches instead of showing prices.
