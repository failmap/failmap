// (c) Fail Map project. This data can be used under the Creative Commons Non-Commercial Attribution Share-Alike license. All data, sources and more can be found in our github repo.
// Generated on <?php echo date(DATE_RFC2822); ?> in <?php echo round((microtime(TRUE)-$_SERVER['REQUEST_TIME_FLOAT']), 4); ?>s
var statesData = {
    "type": "FeatureCollection",
    "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
    "features": [
<?php
    require_once("../../vendor/autoload.php");
    require_once('../../configuration.php');

    // todo: this file will require some filtering as input. Otherwise layers in the map will overwrite each other.
    // This file is not templated, for the simple reason a template engine would increase complexity. This is a tradeoff.

    // Below query can handle scenario's that an organization has multiple areas. In the latest dataset this is all handled in multipolygons (thanks geoJSON).
    // We're grouping on area because of this, since no area is unique.

    // This query is not time-constrained. So you cannot browse through data in the past. This might become a desired feature.

    // when creating new sets of data, you can use these replacements. Would rather have it
    // automated, yet that is very hard (custom, flaky, soft). Map changes are manual.
    //         (.*?)  (.*) (after reducing only organization and multipoly)
    // Regex: UPDATE coordinate SET area = "$2" WHERE organization = "$1"

    $sql = "SELECT
              url.organization as organization,
              area,
              geoJsonType,
              max(scans_ssllabs.rating) as rating
            FROM `url`
            left outer join scans_ssllabs ON url.url = scans_ssllabs.url
            left outer join organization ON url.organization = organization.name
            inner join coordinate ON coordinate.organization = organization.name
            LEFT OUTER JOIN scans_ssllabs as t2 ON (
              scans_ssllabs.url = t2.url
              AND scans_ssllabs.ipadres = t2.ipadres
              AND scans_ssllabs.poort = t2.poort
              AND t2.scanmoment > scans_ssllabs.scanmoment
              AND t2.scanmoment <= DATE_ADD(now(), INTERVAL -0 DAY))
            WHERE t2.url IS NULL
              AND url.organization <> ''
              AND scans_ssllabs.scanmoment <= DATE_ADD(now(), INTERVAL -0 DAY)
              AND url.isDead = 0
              AND scans_ssllabs.isDead = 0
            group by (area)
            order by url.organization ASC, rating DESC";
    //$sql = "select coordinate.organization, area, max(rating) as rating, max(ratingNoTrust) as oordeelInternVertrouwen from coordinate left outer join organization ON coordinate.organization = organization.name left outer JOIN url ON url.organization = organization.name left outer JOIN scans_ssllabs ON scans_ssllabs.url = url.url GROUP BY area";
    $results = DB::query($sql);
    foreach ($results as $row) {
        print '       {"type":"Feature", "properties":{"OrganizationType": "municipality", "OrganizationName": "'.$row['organization'].'", "Overall":"'.$row['rating'].'", "TLS":"'.$row['rating'].'" }, "geometry": {"type": "'.$row['geoJsonType'].'", "coordinates": '.$row['area'].' } },'."\n";
    }
?>
    ]
};
