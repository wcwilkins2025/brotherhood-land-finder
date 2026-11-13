# Sources: public_land.csv and broadband.csv

Gathered 2026-11-13.

## public_land.csv (3,222 rows)

**Dataset:** USGS Gap Analysis Project, *PAD-US 4.1 Vector Analysis and Summary Statistics*,
file `PADUS4_1SummaryStatistics_TabularData_CSV.zip` -> `PADUS4_1VectorAnalysis_Uni_Counties_Clip_CENSUS2022.csv`.
Publication date 2025-03-31 (PAD-US 4.1, revised March 2025). DOI https://doi.org/10.5066/P96WBCHS.
ScienceBase item: https://www.sciencebase.gov/catalog/item/6759b69fd34edfeb8710a3ea
Direct file: https://www.sciencebase.gov/catalog/file/get/6759b69fd34edfeb8710a3ea?f=__disk__29%2F74%2F0b%2F29740bfde5519713b02c6190b07c47e965ce5d23

**What the table is:** PAD-US 4.1 with overlapping designations removed, clipped to Census 2022 county
boundaries, then summarized as acres (`GIS_AcrsDb`) per county x manager type x GAP status x public access.
The remainder of each county that is not in PAD-US appears as rows with `MngTp_Desc = Unknown`,
`GAP_Sts = 4`, `Pub_Access = UK`, so the sum of all rows for a county equals the county's total
Census boundary area (land + water; checked against the Census 2022 Gazetteer, ratio 1.000 for every county).

**Computation of `public_land_pct`:**

    public_land_pct = 100 * sum(GIS_AcrsDb where MngTp_Desc in
                       {Federal, State, Local Government, Regional Agency Special District, Territorial})
                      / sum(GIS_AcrsDb for all rows of the county)

- Included: federal, state, local-government, regional/special-district and territorial managers, all
  GAP statuses and all public-access categories (open, restricted, closed, unknown). Military lands are
  in the Federal rows.
- Excluded: American Indian Lands, Non-Governmental Organization, Private, Joint, Unknown.
- Denominator is the county's total boundary area (land + water), because that is the extent PAD-US was
  clipped to and PAD-US includes marine/water protected areas; using land-only area would push 13 coastal
  counties above 100%. For inland counties the difference from a land-only share is negligible.
- Rounded to 2 decimals.

**FIPS mapping:** PAD-US gives county name + state abbreviation only. Names were matched (accent-stripped)
to the Census 2022 county Gazetteer (https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2022_Gazetteer/2022_Gaz_counties_national.zip)
to get the 5-digit GEOID. All 3,222 Gazetteer counties/equivalents (50 states, DC, Puerto Rico) matched.
Connecticut uses the 2022 planning regions (FIPS 09110-09190), not the old counties.
13 PAD-US rows for AS, GU, MP and VI are not in the Gazetteer and were dropped.

## broadband.csv (header only, no data)

**Intended dataset:** FCC National Broadband Map / Broadband Data Collection, Fixed Broadband Availability
Summary by Geography Type (county rows), latest release.
https://broadbandmap.fcc.gov/data-download/nationwide-data

**Why empty:** The download and listing endpoints
(`https://broadbandmap.fcc.gov/api/public/map/listAsOfDates`,
`.../api/public/map/downloads/listAvailabilityData/<date>`,
`.../api/national_map_process/nbm_get_data_download/<date>`,
`.../nbm/map/api/national_map_process/nbm_get_data_download/<date>`)
return HTTP 401 "Unauthorized" or an Akamai HTTP 403 "Access Denied" to plain curl and to a generic
fetch tool. The site hands out a browser session that curl does not replicate, and the instruction was not
to scrape around it, so no data was pulled. No mirror of the current BDC county summary was found on
data.gov or opendata.fcc.gov (only Form 477 "Area Table" files through June 2020, which the FCC marks as
superseded). To fill this file, download the nationwide "Fixed Broadband Summary by Geography Type" CSV
in a browser, keep rows with `geography_type = County`, `technology = Any Technology` (fixed terrestrial,
not satellite), area_data_type Total/Residential as desired, and take the 100/20 and 25/3 speed-tier
shares of locations.
