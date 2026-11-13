#!/bin/sh
# Downloads every public dataset data/build.py reads into ./downloads (gitignored).
# Everything here is a plain public file or a keyless public API. No accounts, no keys.
# Dates and descriptions: data/sources.md
set -e
cd "$(dirname "$0")/.."
mkdir -p downloads/census downloads/fema downloads/noaa/normals downloads/usda downloads/nrcs downloads/usgs downloads/hifld downloads/wikidata downloads/shapes
cd downloads

# Census Bureau: county and place gazetteers (centroids, land area), ZCTA centroids, county boundaries
curl -sSL -o census/gaz_counties.zip https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip
curl -sSL -o census/gaz_places.zip   https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip
curl -sSL -o census/gaz_zcta.zip     https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip
unzip -o -q census/gaz_counties.zip -d census/; unzip -o -q census/gaz_places.zip -d census/; unzip -o -q census/gaz_zcta.zip -d census/
curl -sSL -o shapes/cb_2023_us_county_20m.zip https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_20m.zip
unzip -o -q shapes/cb_2023_us_county_20m.zip -d shapes/
# Census Bureau: 2024 population estimates (counties)
curl -sSL -o census/co-est2024-alldata.csv https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv
# Census Bureau: ACS 2019-2023 5-year table-based summary files (B01003 population, B25077 median home value,
# B25103 median real estate taxes paid, B28002 internet subscriptions)
for t in b01003 b25077 b25103 b28002; do
  curl -sSL -o census/acsdt5y2023-$t.dat https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-$t.dat
done

# NOAA nClimDiv county monthly precipitation, mean temperature and minimum temperature (1895-present)
B=https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current
V=$(curl -sS $B/ | grep -oE 'climdiv-pcpncy-v[0-9.]+-[0-9]+' | head -1 | sed 's/climdiv-pcpncy-//')
for f in pcpncy tmincy tmpccy; do curl -sSL -o noaa/climdiv-$f-$V $B/climdiv-$f-$V; done
curl -sSL -o noaa/county-readme.txt $B/county-readme.txt
# NOAA 1991-2020 US Climate Normals, annual/seasonal, by station (growing season length)
curl -sSL -o noaa/normals_annualseasonal_by_station.tar.gz https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/archive/us-climate-normals_1991-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz
tar -xzf noaa/normals_annualseasonal_by_station.tar.gz -C noaa/normals

# USDA NASS Quick Stats bulk file for the 2022 Census of Agriculture (309 MB); keep only the county land-value rows
curl -sSL -o usda/qs.census2022.txt.gz https://www.nass.usda.gov/sites/default/files/datasets/qs.census2022.txt.gz
zcat usda/qs.census2022.txt.gz | head -1 > usda/agland_value_county.txt
zcat usda/qs.census2022.txt.gz | grep -F 'AG LAND, INCL BUILDINGS - ASSET VALUE, MEASURED IN $ / ACRE' | awk -F'\t' '$13=="COUNTY"' >> usda/agland_value_county.txt

# USDA NRCS Soil Data Access: SSURGO map-unit acres by prime-farmland class, per soil survey area
for st in AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY; do
  printf '{"query":"SELECT l.areasymbol, l.areaname, mu.farmlndcl, SUM(mu.muacres) AS acres FROM legend l INNER JOIN mapunit mu ON mu.lkey = l.lkey WHERE l.areasymbol LIKE %s%s%%%s GROUP BY l.areasymbol, l.areaname, mu.farmlndcl ORDER BY l.areasymbol","format":"JSON"}' "'" "$st" "'" > nrcs/q.json
  curl -sS -X POST https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest -H "Content-Type: application/json" --data-binary @nrcs/q.json -o nrcs/farmland_$st.json; sleep 1
done

# USGS NWIS site inventory: groundwater wells with depth, per state
for st in AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY; do
  curl -sS -o usgs/nwis_gw_$st.rdb "https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd=$st&siteType=GW&siteOutput=expanded"; sleep 1
done

# FEMA National Risk Index, county layer (official FEMA_NationalRiskIndex ArcGIS service; the zip on hazards.fema.gov resets connections)
S=https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0
for off in 0 2000; do curl -sS -o fema/nri_$off.json "$S/query?where=1%3D1&outFields=*&returnGeometry=false&resultOffset=$off&resultRecordCount=2000&f=json"; done

# HIFLD hospitals (Homeland Infrastructure Foundation-Level Data, federal ArcGIS Online copy)
S=https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Hospitals/FeatureServer/0
for off in 0 2000 4000 6000; do curl -sS -o hifld/hospitals_$off.json "$S/query?where=1%3D1&outFields=ID,NAME,CITY,STATE,TYPE,STATUS,COUNTYFIPS,LATITUDE,LONGITUDE,BEDS,TRAUMA,SOURCEDATE&returnGeometry=false&resultOffset=$off&resultRecordCount=2000&f=json"; done

# Wikidata: official website of each county (property P856) keyed by FIPS (P882)
Q='SELECT ?fips ?site WHERE { ?c wdt:P882 ?fips . OPTIONAL { ?c wdt:P856 ?site . } FILTER(STRLEN(?fips) = 5) }'
curl -sS -G https://query.wikidata.org/sparql --data-urlencode "query=$Q" -H "Accept: text/csv" -o wikidata/county_sites.csv
echo "All downloads done. Now run: python -I data/build.py"
