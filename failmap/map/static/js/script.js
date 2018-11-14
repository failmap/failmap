// Registry Sentry for error reporting
let sentry_token = document.head.querySelector("[name=sentry_token]").getAttribute('content');
let version = document.head.querySelector("[name=version]").getAttribute('content');
let country = document.head.querySelector("[name=country]").getAttribute('content');
let mapbox_token = document.head.querySelector("[name=mapbox_token]").getAttribute('content');
let debug = document.head.querySelector("[name=debug]").getAttribute('content');
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

    // vulnerabilities:
    gettext('report_header_tls_qualys');
    gettext('report_header_plain_https');
    gettext('report_header_security_headers_x_xss_protection');
    gettext('report_header_security_headers_x_frame_options');
    gettext('report_header_security_headers_x_content_type_options');
    gettext('report_header_security_headers_strict_transport_security');
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

    // some countries:
    gettext('country_AD');
    gettext('country_AE');
    gettext('country_AF');
    gettext('country_AG');
    gettext('country_AI');
    gettext('country_AL');
    gettext('country_AM');
    gettext('country_AO');
    gettext('country_AQ');
    gettext('country_AR');
    gettext('country_AS');
    gettext('country_AT');
    gettext('country_AU');
    gettext('country_AW');
    gettext('country_AX');
    gettext('country_AZ');
    gettext('country_BA');
    gettext('country_BB');
    gettext('country_BD');
    gettext('country_BE');
    gettext('country_BF');
    gettext('country_BG');
    gettext('country_BH');
    gettext('country_BI');
    gettext('country_BJ');
    gettext('country_BL');
    gettext('country_BM');
    gettext('country_BN');
    gettext('country_BO');
    gettext('country_BR');
    gettext('country_BS');
    gettext('country_BT');
    gettext('country_BW');
    gettext('country_BY');
    gettext('country_BZ');
    gettext('country_CA');
    gettext('country_CD');
    gettext('country_CF');
    gettext('country_CG');
    gettext('country_CH');
    gettext('country_CI');
    gettext('country_CK');
    gettext('country_CL');
    gettext('country_CM');
    gettext('country_CN');
    gettext('country_CO');
    gettext('country_CR');
    gettext('country_CU');
    gettext('country_CV');
    gettext('country_CW');
    gettext('country_CY');
    gettext('country_CZ');
    gettext('country_DE');
    gettext('country_DJ');
    gettext('country_DK');
    gettext('country_DM');
    gettext('country_DO');
    gettext('country_DZ');
    gettext('country_EC');
    gettext('country_EE');
    gettext('country_EG');
    gettext('country_EH');
    gettext('country_ER');
    gettext('country_ES');
    gettext('country_ET');
    gettext('country_FI');
    gettext('country_FJ');
    gettext('country_FK');
    gettext('country_FM');
    gettext('country_FO');
    gettext('country_FR');
    gettext('country_GA');
    gettext('country_GB');
    gettext('country_GD');
    gettext('country_GE');
    gettext('country_GG');
    gettext('country_GH');
    gettext('country_GL');
    gettext('country_GM');
    gettext('country_GN');
    gettext('country_GQ');
    gettext('country_GR');
    gettext('country_GS');
    gettext('country_GT');
    gettext('country_GU');
    gettext('country_GW');
    gettext('country_GY');
    gettext('country_HK');
    gettext('country_HM');
    gettext('country_HN');
    gettext('country_HR');
    gettext('country_HT');
    gettext('country_HU');
    gettext('country_ID');
    gettext('country_IE');
    gettext('country_IL');
    gettext('country_IM');
    gettext('country_IN');
    gettext('country_IO');
    gettext('country_IQ');
    gettext('country_IR');
    gettext('country_IS');
    gettext('country_IT');
    gettext('country_JE');
    gettext('country_JM');
    gettext('country_JO');
    gettext('country_JP');
    gettext('country_KE');
    gettext('country_KG');
    gettext('country_KH');
    gettext('country_KI');
    gettext('country_KM');
    gettext('country_KN');
    gettext('country_KP');
    gettext('country_KR');
    gettext('country_KW');
    gettext('country_KY');
    gettext('country_KZ');
    gettext('country_LA');
    gettext('country_LB');
    gettext('country_LC');
    gettext('country_LI');
    gettext('country_LK');
    gettext('country_LR');
    gettext('country_LS');
    gettext('country_LT');
    gettext('country_LU');
    gettext('country_LV');
    gettext('country_LY');
    gettext('country_MA');
    gettext('country_MC');
    gettext('country_MD');
    gettext('country_ME');
    gettext('country_MF');
    gettext('country_MG');
    gettext('country_MH');
    gettext('country_MK');
    gettext('country_ML');
    gettext('country_MM');
    gettext('country_MN');
    gettext('country_MO');
    gettext('country_MP');
    gettext('country_MR');
    gettext('country_MS');
    gettext('country_MT');
    gettext('country_MU');
    gettext('country_MV');
    gettext('country_MW');
    gettext('country_MX');
    gettext('country_MY');
    gettext('country_MZ');
    gettext('country_NA');
    gettext('country_NC');
    gettext('country_NE');
    gettext('country_NF');
    gettext('country_NG');
    gettext('country_NI');
    gettext('country_NL');
    gettext('country_NO');
    gettext('country_NP');
    gettext('country_NR');
    gettext('country_NU');
    gettext('country_NZ');
    gettext('country_OM');
    gettext('country_PA');
    gettext('country_PE');
    gettext('country_PF');
    gettext('country_PG');
    gettext('country_PH');
    gettext('country_PK');
    gettext('country_PL');
    gettext('country_PM');
    gettext('country_PN');
    gettext('country_PR');
    gettext('country_PS');
    gettext('country_PT');
    gettext('country_PW');
    gettext('country_PY');
    gettext('country_QA');
    gettext('country_RO');
    gettext('country_RS');
    gettext('country_RU');
    gettext('country_RW');
    gettext('country_SA');
    gettext('country_SB');
    gettext('country_SC');
    gettext('country_SD');
    gettext('country_SE');
    gettext('country_SG');
    gettext('country_SH');
    gettext('country_SI');
    gettext('country_SK');
    gettext('country_SL');
    gettext('country_SM');
    gettext('country_SN');
    gettext('country_SO');
    gettext('country_SR');
    gettext('country_SS');
    gettext('country_ST');
    gettext('country_SV');
    gettext('country_SX');
    gettext('country_SY');
    gettext('country_SZ');
    gettext('country_TC');
    gettext('country_TD');
    gettext('country_TF');
    gettext('country_TG');
    gettext('country_TH');
    gettext('country_TJ');
    gettext('country_TL');
    gettext('country_TM');
    gettext('country_TN');
    gettext('country_TO');
    gettext('country_TR');
    gettext('country_TT');
    gettext('country_TW');
    gettext('country_TZ');
    gettext('country_UA');
    gettext('country_UG');
    gettext('country_US');
    gettext('country_UY');
    gettext('country_UZ');
    gettext('country_VA');
    gettext('country_VC');
    gettext('country_VE');
    gettext('country_VG');
    gettext('country_VI');
    gettext('country_VN');
    gettext('country_VU');
    gettext('country_WF');
    gettext('country_WS');
    gettext('country_YE');
    gettext('country_ZA');
    gettext('country_ZM');
    gettext('country_ZW');


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
