"""Configuration constants for the OTC KPI dashboard."""

IGNORE_STATIONS = [
    "BE-SOOP-Belgica",
    "NO-SOOP-Nuka Arctica",
    "UK-SOOP-UK-Caribbean",
]

KPI_COL = "fCO2 [uatm] QC Flag"

COLORMAPS = ["RdBu", "Blues", "Viridis", "YlOrRd", "RdYlGn"]

DEFAULT_N_MONTHS = 12
DEFAULT_CMAP = "RdBu"

# Descriptive message shown below the heatmap. Supports plain text or HTML.
# Set to "" to hide.
DESCRIPTION = """
This dashboard monitors the data quality of fCO₂ measurements in Level 2 datasets, as well as the availability of Level 1 Near Real-Time (NRT) data from ICOS ocean stations.

The heatmap displays the monthly percentage of fCO₂ records flagged as good quality (QC = 2) relative to all valid measurements. Higher percentages indicate better data quality for a given month. Empty cells represent months where no Level 2 data are available. Hover over each cell to view the number of valid measurements and those classified as good quality. Dark grey horizontal bars indicate the temporal coverage of the most recent Level 1 NRT data for stations that provide NRT observations.

Use the controls above the dashboard to adjust the number of months displayed and the color scale. The dropdown menu below the heatmap provides links to station landing pages, along with access to the most recent data objects for both Level 1 NRT and Level 2 datasets.

All data are sourced in real time from ICOS Carbon Portal.
"""

# How often to refresh data from ICOS (seconds). Default: 6 hours.
CACHE_TTL = 6 * 60 * 60

# Path to the disk cache file for Level-2 processed results.
import os as _os
DISK_CACHE_PATH = _os.path.join(_os.path.dirname(__file__), "l2_cache.pkl")

L2_LATEST_QUERY = """
PREFIX cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
PREFIX prov:   <http://www.w3.org/ns/prov#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>

SELECT ?dobj ?timeStart ?timeEnd ?station
FROM <http://meta.icos-cp.eu/resources/cpmeta/>
FROM <http://meta.icos-cp.eu/resources/icos/>
FROM <http://meta.icos-cp.eu/resources/extrastations/>
WHERE {
    VALUES ?spec {
        <http://meta.icos-cp.eu/resources/cpmeta/icosOtcL2Product>
        <http://meta.icos-cp.eu/resources/cpmeta/icosOtcFosL2Product>
    }
    ?dobj cpmeta:hasObjectSpec ?spec .
    ?dobj cpmeta:wasAcquiredBy/prov:wasAssociatedWith ?station .
    ?dobj cpmeta:hasStartTime | (cpmeta:wasAcquiredBy / prov:startedAtTime) ?timeStart .
    ?dobj cpmeta:hasEndTime | (cpmeta:wasAcquiredBy / prov:endedAtTime) ?timeEnd .
    {
        SELECT ?station (MAX(xsd:dateTime(?timeEnd)) AS ?maxTime)
        WHERE {
            VALUES ?spec {
                <http://meta.icos-cp.eu/resources/cpmeta/icosOtcL2Product>
                <http://meta.icos-cp.eu/resources/cpmeta/icosOtcFosL2Product>
            }
            ?dobj cpmeta:hasObjectSpec ?spec .
            ?station a cpmeta:OS .
            ?dobj cpmeta:wasAcquiredBy/prov:wasAssociatedWith ?station .
            ?dobj cpmeta:hasEndTime | (cpmeta:wasAcquiredBy / prov:endedAtTime) ?timeEnd .
        }
        GROUP BY ?station
    }
    FILTER(xsd:dateTime(?timeEnd) = ?maxTime)
    FILTER NOT EXISTS {[] cpmeta:isNextVersionOf ?dobj}
}
ORDER BY DESC(?timeEnd)
"""

NRT_QUERY = """
PREFIX cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
PREFIX prov:   <http://www.w3.org/ns/prov#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>

SELECT ?dobj ?timeStart ?timeEnd ?station
FROM <http://meta.icos-cp.eu/resources/cpmeta/>
FROM <http://meta.icos-cp.eu/resources/icos/>
FROM <http://meta.icos-cp.eu/resources/extrastations/>
WHERE {
    VALUES ?spec {
        <http://meta.icos-cp.eu/resources/cpmeta/icosOtcL1Product_v2>
        <http://meta.icos-cp.eu/resources/cpmeta/icosOtcFosL1Product>
    }
    ?dobj cpmeta:hasObjectSpec ?spec .
    ?dobj cpmeta:wasAcquiredBy/prov:wasAssociatedWith ?station .
    ?dobj cpmeta:hasStartTime | (cpmeta:wasAcquiredBy / prov:startedAtTime) ?timeStart .
    ?dobj cpmeta:hasEndTime | (cpmeta:wasAcquiredBy / prov:endedAtTime) ?timeEnd .
    {
        SELECT ?station (MAX(xsd:dateTime(?timeEnd)) AS ?maxTime)
        WHERE {
            VALUES ?spec {
                <http://meta.icos-cp.eu/resources/cpmeta/icosOtcL1Product_v2>
                <http://meta.icos-cp.eu/resources/cpmeta/icosOtcFosL1Product>
            }
            ?dobj cpmeta:hasObjectSpec ?spec .
            ?station a cpmeta:OS .
            ?dobj cpmeta:wasAcquiredBy/prov:wasAssociatedWith ?station .
            ?dobj cpmeta:hasEndTime | (cpmeta:wasAcquiredBy / prov:endedAtTime) ?timeEnd .
        }
        GROUP BY ?station
    }
    FILTER(xsd:dateTime(?timeEnd) = ?maxTime)
    FILTER NOT EXISTS {[] cpmeta:isNextVersionOf ?dobj}
}
ORDER BY DESC(?timeEnd)
"""
