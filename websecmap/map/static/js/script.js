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
    gettext('STARTTLS Available');
    gettext('STARTTLS Missing');
    gettext('SPF Available');
    gettext('SPF Missing');
    gettext('DKIM Available');
    gettext('DKIM Missing');
    gettext('DMARC Available');
    gettext('DMARC Missing');
    gettext('DANE Available');
    gettext('DANE Missing');

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
    gettext('category_menu_state');
    gettext('category_menu_school');

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
    gettext('http_security_header_strict_transport_security');
    gettext('http_security_header_x_frame_options');
    gettext('http_security_header_x_content_type_options');
    gettext('http_security_header_x_xss_protection');
    gettext('internet_nl_mail_starttls_tls_available');
    gettext('internet_nl_mail_auth_spf_exist');
    gettext('internet_nl_mail_auth_dkim_exist');
    gettext('internet_nl_mail_auth_dmarc_exist');

    gettext('Stats hasn\'t');
    gettext('Stats has');
    gettext('Broken');
    gettext('TLS rated C');
    gettext('TLS rated B');
    gettext('TLS rated A');
    gettext('TLS rated A-');
    gettext('TLS rated A+');
    gettext('Not at all');
    gettext('Redirect from unsafe address');
    gettext('FTP Insecure');
    gettext('FTP');
    gettext('Redirect from unsafe address');


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

let current_colorscheme = "trafficlight";
function set_colorscheme(scheme_name){
    let thing = 'link[href="'+$('link#colorscheme').attr('href') + '"]';
    current_colorscheme = scheme_name;
    $(thing).attr('href', `/static/css/colors.${scheme_name}.css`);

    setTimeout(set_graph_colorscheme, 2000);

    return true;
}

function set_graph_colorscheme(){
    // can we now access elements that contain these colors via javascript selectors, because that's not
    // a horrible solution at all... </sarcasm>
    // The browser has to load it... so we need to run this at a timeout... (you've got to be kidding me)
    // try the color scheme:
    let charts_high = $('.charts_high');
    let charts_medium = $('.charts_medium');
    let charts_low = $('.charts_low');
    let charts_good = $('.charts_good');
    let charts_connectivity_internet_adresses = $('.charts_connectivity_internet_adresses');
    let charts_connectivity_services = $('.charts_connectivity_services');

    let new_color_scheme = {
        'high_background': charts_high.css('background-color'),
        'high_border': charts_high.css('background-color'),
        'medium_background': charts_medium.css('background-color'),
        'medium_border': charts_medium.css('background-color'),
        'low_background': charts_low.css('background-color'),
        'low_border': charts_low.css('background-color'),
        'good_background': charts_good.css('background-color'),
        'good_border': charts_good.css('background-color'),
        'addresses_background': charts_connectivity_internet_adresses.css('background-color'),
        'addresses_border': charts_connectivity_internet_adresses.css('background-color'),
        'services_background': charts_connectivity_services.css('background-color'),
        'services_border': charts_connectivity_services.css('background-color'),
    };

    vueGraphs.color_scheme = new_color_scheme;
    vueReport.color_scheme = new_color_scheme;
    vueFullScreenReport.color_scheme = new_color_scheme;

}



let document_ready = function() {
    map.initialize(mapbox_token, country, debug);
    Vue.component('v-select', VueSelect.VueSelect);

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

    let colorschemes = {
        "trafficlight": "/static/css/colors.trafficlight.css",
        "pink": "/static/css/colors.trafficlight.css",
    };

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
                map.set_theme('dark');

            if (selected_theme === 'default')
                map.set_theme('light');
        });
    });
};
