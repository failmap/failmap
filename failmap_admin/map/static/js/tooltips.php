<?php
require_once("../../vendor/autoload.php");
require_once('../../configuration.php');
require_once('../../code/functions.php');
?>
// Generated on <?php echo date(DATE_RFC2822); ?> in <?php echo round((microtime(TRUE)-$_SERVER['REQUEST_TIME_FLOAT']), 4); ?>s
$(document).ready(function() {
$('.tooltip').tooltipster({
theme: 'tooltipster-light'
});
<?php

/* Should look like:
$('#my-tooltip').tooltipster({
    content: $('<span><img src="my-image.png" /> <strong>This text is in bold case !</strong></span>')
});
*/

$previousUrl = ""; $i=0;

// ssllabs can discover multiple endpoints per domain. There can be multiple IP-address on both IPv4 and IPv6.
$sql = "SELECT
                              organization,
                              url.url as theurl,
                              scans_ssllabs.ipadres,
                              scans_ssllabs.servernaam,
                              scans_ssllabs.poort,
                              scans_ssllabs.scandate,
                              scans_ssllabs.scantime,
                              scans_ssllabs.rating
                            FROM `url` left outer join scans_ssllabs ON url.url = scans_ssllabs.url
                            LEFT OUTER JOIN scans_ssllabs as t2 ON (
                              scans_ssllabs.url = t2.url
                              AND scans_ssllabs.ipadres = t2.ipadres
                              AND scans_ssllabs.poort = t2.poort
                              AND t2.scanmoment > scans_ssllabs.scanmoment
                              AND t2.scanmoment <= NOW())
                            WHERE t2.url IS NULL
                              AND organization <> ''
                              AND scans_ssllabs.scanmoment <= now()
                              AND url.isDead = 0
                              AND scans_ssllabs.isDead = 0
                            order by organization ASC";

$results = DB::query($sql);
foreach ($results as $row) {

    if ($previousUrl != $row['theurl']) {
        if ($i!=0){print "</span>')}); \n ";}

        print "$('#".makeHTMLId($row['theurl'])."').tooltipster({ animation: 'fade', interactive: 'true', theme: 'tooltipster-light', content: $('<span>";
    }

    if ($row['ipadres']) {
        if ($row['rating'] === '0')
            $unknown = "Geen beveiligde verbinding gevonden.<br /><br />Dit komt vaak doordat:<br /><ul><li>er gekozen is publieke informatie zo benaderbaar mogelijk te maken,</li><li>er gebruik wordt gemaakt van filtering,</li><li>er geen dienst (meer) draait,</li><li>een ander poortnummer wordt gebruikt dan 443.</li></ul><br />";
        else
            $unknown = "";

        $colorOordeel = getRatingColor($row['rating']);
        print $unknown."<span style=\"color: #".$colorOordeel."\">Domein: ".$row['theurl']."<br />Adres: ".$row['ipadres'].":".$row['poort']."<br /></span>Reverse name: ".$row['servernaam']."<br />Scantijd: ".$row['scandate']." ".$row['scantime']." <br /><br /><a href=\"https://www.ssllabs.com/ssltest/analyze.html?d=".$row['theurl']."&hideResults=on&latest\" target=\"_blank\">Second opinion</a><br /><br />";
    } else {
        print "Geen informatie gevonden. Dit domein wordt mogelijk niet gebruikt of moet nog worden niet getest.";
    }

    $previousUrl = $row['theurl'];
    $i++;
}
print "</span>')}); \n ";
?>
});