// Registry Sentry for error reporting
let sentry_token = document.head.querySelector("[name=sentry_token]").getAttribute('content');
let version = document.head.querySelector("[name=version]").getAttribute('content');
if (sentry_token) {
    Raven.config(sentry_token, {release: version}).install();
}

// https://stackoverflow.com/questions/7625991/
// how-to-properly-add-entries-for-computed-values-to-the-django-internationalizati
var dynamic_translations = function(){
    // statistics
    gettext('2 weeks ago');
    gettext('3 weeks ago');
    gettext('1 month ago');
    gettext('2 months ago');
    gettext('3 months ago');
    gettext('7 days ago');
    gettext('now');

    // system vulnerability messages
    gettext("Has a secure equivalent, which wasn't so in the past.");
    // todo: equalize these messages so it's always the same.
    gettext('Site does not redirect to secure url, and has no secure alternative on a standard port.');
    gettext('Redirects to a secure site, while a secure counterpart on the standard port is missing.');
    gettext('Broken Transport Security, rated F');
    gettext('Certificate not valid for domain name.');
    gettext('Could not establish trust.  For the certificate installation: Less than optimal Transport Security, rated C.');
    gettext('Could not establish trust.  For the certificate installation: Less than optimal Transport Security, rated B.');
    gettext('Could not establish trust.  For the certificate installation: Good Transport Security, rated A-.');
    gettext('Could not establish trust.  For the certificate installation: Good Transport Security, rated A.');
    gettext('Less than optimal Transport Security, rated C.');
    gettext('Less than optimal Transport Security, rated B.');
    gettext('Good Transport Security, rated A-.');
    gettext('Good Transport Security, rated A.');
    gettext('Perfect Transport Security, rated A+.');
    gettext('X-Content-Type-Options header present.');
    gettext('Missing X-Content-Type-Options header.');
    gettext('X-XSS-Protection header present.');
    gettext('Missing X-XSS-Protection header.');
    gettext('X-Frame-Options header present.');
    gettext('Missing X-Frame-Options header.');
    gettext('Strict-Transport-Security header present.');
    gettext('Missing Strict-Transport-Security header.');
    gettext('Missing Strict-Transport-Security header. Offers no insecure alternative service.');

    // vulnerabilities:
    gettext('report_header_tls_qualys');
    gettext('report_header_plain_https');
    gettext('report_header_security_headers_x_xss_protection');
    gettext('report_header_security_headers_x_frame_options');
    gettext('report_header_security_headers_x_content_type_options');
    gettext('report_header_security_headers_strict_transport_security');

    // some categories:
    gettext('category_menu_municipality');
    gettext('category_menu_cyber');
    gettext('category_menu_unknown');
    gettext('category_menu_water_board');
    gettext('category_menu_province');
    gettext('category_menu_hacking');
    // and germany
    gettext('bundesland');
    gettext('regierungsbezirk');
    gettext('landkreis_kreis_kreisfreie_stadt');
    gettext('samtgemeinde_verwaltungsgemeinschaft');
    gettext('stadt_gemeinde');
    gettext('stadtbezirk_gemeindeteil_mit_selbstverwaltung');
    gettext('stadtteil_gemeindeteil_ohne_selbstverwaltung');

    // some countries:
    gettext('country_NL');
    gettext('country_DE');
    gettext('country_SE');
    gettext('country_AT');
};

$(document).ready(function () {
    failmap.initializemap("nl");
    views(); // start all vues
    lazyload(); // allow for lazy loading of images

    // if browser contains report anchor with organization id load that organization
    let match = RegExp('report-([0-9]+)').exec(location.hash);
    if (match) {
        let organization_id = match[1];
        location.href = '#report';
        vueReport.selected = organization_id;
    }

});
