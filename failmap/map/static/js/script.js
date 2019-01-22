// Registry Sentry for error reporting
let sentry_token = document.head.querySelector("[name=sentry_token]").getAttribute('content');
let version = document.head.querySelector("[name=version]").getAttribute('content');
let country = document.head.querySelector("[name=country]").getAttribute('content');
let mapbox_token = document.head.querySelector("[name=mapbox_token]").getAttribute('content');
let debug = document.head.querySelector("[name=debug]").getAttribute('content');
let initial_map_data_url = document.head.querySelector("[name=initial_map_data_url]").getAttribute('content');
let TICKER_VISIBLE_VIA_JS_COMMAND = document.head.querySelector("[name=TICKER_VISIBLE_VIA_JS_COMMAND]").getAttribute('content');
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
    gettext('DNSSEC is incorrectly or not configured (errors found).');
    gettext('DNSSEC seems to be implemented sufficiently.');
    gettext('FTP Server only supports insecure SSL protocol.');
    gettext('FTP Server does not configured to show if encryption is available.');
    gettext('FTP Server supports TLS encryption protocol.');
    gettext('FTP Server does not support encrypted transport or has protocol issues.');
    gettext('An FTP connection could not be established properly. Not possible to verify encryption.');
    gettext('not trusted');
    gettext('trusted');
    gettext('Certificate is not trusted.');
    gettext('Certificate is trusted.');
    gettext('Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options header.');
    gettext('Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.');

    // vulnerabilities:
    gettext('report_header_tls_qualys');
    gettext('report_header_plain_https');
    gettext('report_header_http_security_header_x_xss_protection');
    gettext('report_header_http_security_header_x_frame_options');
    gettext('report_header_http_security_header_x_content_type_options');
    gettext('report_header_http_security_header_strict_transport_security');
    gettext('report_header_DNSSEC');
    gettext('report_header_ftp');
    gettext('report_header_tls_qualys_certificate_trusted');
    gettext('report_header_tls_qualys_encryption_quality');

    // some categories:
    gettext('category_menu_municipality');
    gettext('category_menu_cyber');
    gettext('category_menu_unknown');
    gettext('category_menu_water_board');
    gettext('category_menu_province');
    gettext('category_menu_hacking');
    gettext('category_menu_country');
    gettext('category_menu_region');
    gettext('category_menu_county');
    gettext('category_menu_district');
    gettext('category_menu_government');
    gettext('category_menu_healthcare');
    gettext('category_menu_finance');

    // scan types
    gettext('Strict-Transport-Security');
    gettext('X-Content-Type-Options');
    gettext('X-Frame-Options');
    gettext('X-XSS-Protection');
    gettext('plain_https');
    gettext('tls_qualys');
    gettext('DNSSEC');
    gettext('ftp');
    gettext('tls_qualys_encryption_quality');
    gettext('tls_qualys_certificate_trusted');

    // and germany
    gettext('category_menu_bundesland');
    gettext('category_menu_regierungsbezirk');
    gettext('category_menu_landkreis_kreis_kreisfreie_stadt');
    gettext('category_menu_samtgemeinde_verwaltungsgemeinschaft');
    gettext('category_menu_stadt_gemeinde');
    gettext('category_menu_stadtbezirk_gemeindeteil_mit_selbstverwaltung');
    gettext('category_menu_stadtteil_gemeindeteil_ohne_selbstverwaltung');

    // historycontrol
    gettext('One week earlier');
    gettext('One week later');
    gettext('Moment');
    gettext('Risks');
};

let document_ready = function() {
    failmap.initialize(mapbox_token, country, debug);
    views(); // start all vues
    lazyload(); // allow for lazy loading of images

    // date and time to the current locale, whatever it may be:
    moment.locale(window.navigator.userLanguage || window.navigator.language);

    // if browser contains report anchor with organization id load that organization
    let match = RegExp('report-([a-z-]+)').exec(location.hash);
    if (match) {
        let organization_name = match[1];
        location.href = '#report';
        vueReport.selected = organization_name;
    }

    // switch themes
    // http://jsfiddle.net/82AsF/
    let themes = {
        "default": "/static/css/vendor/bootstrap.min.css",
        "darkly" : "/static/css/vendor/bootstrap-darkly.min.css",
    };

    $(function(){
       let themesheet = $('<link href="'+themes['default']+'" rel="stylesheet" />');
        themesheet.appendTo('head');
        $('.theme-link').click(function(){
            let selected_theme = $(this).attr('data-theme');
           let themeurl = themes[selected_theme];
           let thing = 'link[href="'+$('link#active_theme').attr('href') + '"]';
           $(thing).attr('href', themeurl);

           if (selected_theme === 'darkly')
               failmap.set_theme('dark');

           if (selected_theme === 'default')
                failmap.set_theme('light');
        });
    });
};
