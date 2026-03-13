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

# How often to refresh data from ICOS (seconds). Default: 6 hours.
CACHE_TTL = 6 * 60 * 60

NRT_QUERY = """
PREFIX cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
PREFIX prov:   <http://www.w3.org/ns/prov#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>

SELECT ?dobj ?timeEnd ?station ?stationName
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
    ?station rdfs:label ?stationName .
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
