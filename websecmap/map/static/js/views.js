// We've taken some time to determine what would be a non-"all-in" approach to build this software.
// Vue indeed is incrementally adoptable and easy to write and learn.
// Angular was off the table due to bad experiences, React seems to intense, especially given javascripts syntax
// oh, and the react anti-patent clause is a big no.
// // https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc

// also contains the correct / consistent display order

// todo: {% if config.SHOW_HTTP_TLS_QUALYS %} {% if config.SHOW_HTTP_MISSING_TLS %} {% if config.SHOW_FTP %}
// {% if config.SHOW_DNS_DNSSEC %} {% if config.SHOW_HTTP_HEADERS_HSTS %} {% if config.SHOW_HTTP_HEADERS_XFO %}
// {% if config.SHOW_HTTP_HEADERS_X_CONTENT %} {% if config.SHOW_HTTP_HEADERS_X_XSS %}
// if it's not in here, it won't be shown. As simple as that. So these conditions have to be evaluated here,
// so there are a lot less IF's in the front end.
// also translations move to JS: {% trans "Encryption quality updates" %} {% trans "Certificate trust updates" %}
// {% trans "Lack of encryption updates" %} {% trans "FTP updates" %} {% trans "DNSSEC updates" %}
// {% trans "Forcing encryption updates" %} {% trans "X-Frame-Options updates" %} {% trans "X-Content-Type-Option updates" %}
// {% trans "X-XSS-Protection updates" %}
// DNS Security (DNSSEC)
// File transfer (FTP)
// Application of encryption (HTTPS)
// Encryption quality (TLS)
// Certificate trust (TLS)
// Enforcing encryption (HSTS)
// Clickjacking prevention (X-Frame-Options)
// X-XSS Protection
// X-Content Type Options
let issues = {

    "DNSSEC": {
        "name": "DNSSEC",
        "second opinion links": [{
            "url": "https://zonemaster.iis.se/",
            "language": "EN",
            "provider": "Zonemaster"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Domain_Name_System_Security_Extensions",
            "language": "EN",
            "provider": "Wikipedia",
        }],
        "relevant impacts": ["high"],
        "statistics": {
            "good": [
                {
                    'label': 'DNSSEC correct', 'explanation': 'DNSSEC seems to be implemented sufficiently.'
                }],
            "medium": [],
            "bad": [{'label': 'DNSSEC incorrect', 'explanation': 'DNSSEC is incorrectly or not configured (errors found).'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "tls_qualys_certificate_trusted": {
        "name": "tls_qualys_certificate_trusted",
        "second opinion links": [{
            "url": "https://www.ssllabs.com/ssltest/analyze.html?d=${url.url}&hideResults=on&latest",
            "language": "EN",
            "provider": "Qualys"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Transport_Layer_Security",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high"],
        "statistics": {
            "good": [{'label': "Trust", 'explanation': 'Certificate is trusted.'}],
            "medium": [],
            "bad": [{'label': "No trust", 'explanation': 'Certificate is not trusted.'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "tls_qualys_encryption_quality": {
        "name": "tls_qualys_encryption_quality",
        "second opinion links": [{
            "url": "https://www.ssllabs.com/ssltest/analyze.html?d=${url.url}&hideResults=on&latest",
            "language": "EN",
            "provider": "Qualys"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Transport_Layer_Security",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high", "low"],
        "statistics": {
            "good": [{'label': "TLS rated A-", 'explanation': 'Good Transport Security, rated A-.'},
                {'label': "TLS rated A", 'explanation': 'Good Transport Security, rated A.'},
                {'label': "TLS rated A+", 'explanation': 'Perfect Transport Security, rated A+.'}],
            "medium": [{'label': "TLS rated C", 'explanation': 'Less than optimal Transport Security, rated C.'},
            {'label': "TLS rated B", 'explanation': 'Less than optimal Transport Security, rated B.'}],
            "bad": [{'label': "Broken", 'explanation': 'Broken Transport Security, rated F'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "plain_https": {
        "name": "plain_https",
        "second opinion links": [{
            "url": "https://www.ssllabs.com/ssltest/analyze.html?d=${url.url}&hideResults=on&latest",
            "language": "EN",
            "provider": "Qualys"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Transport_Layer_Security",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high", "medium"],
        "statistics": {
            "good": [],
            "medium": [{'label': "Redirect from unsafe address", 'explanation': 'Redirects to a secure site, while a secure counterpart on the standard port is missing.'}],
            "bad": [{'label': "Not at all", 'explanation': 'Site does not redirect to secure url, and has nosecure alternative on a standard port.'},
            {'label': "Not at all", 'explanation': 'Site does not redirect to secure url, and has no secure alternative on a standard port.'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "ftp": {
        "name": "ftp",
        "second opinion links": [{
            "url": "https://ftptest.net/",
            "language": "EN",
            "provider": "ftptest.net"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/FTPS",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high", "medium"],
        "statistics": {
            "good": [{'label': "FTP secure", 'explanation': 'FTP Server supports TLS encryption protocol.'}],
            "medium": [],
            "bad": [{'label': "FTP insecure", 'explanation': 'FTP Server does not support encrypted transport or has protocol issues.'},
            {'label': "FTP outdated", 'explanation': 'FTP Server only supports insecure SSL protocol.'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "http_security_header_strict_transport_security": {
        "name": "http_security_header_strict_transport_security",
        "second opinion links": [{
            "url": "https://securityheaders.io/?q=${url.url}",
            "language": "EN",
            "provider": "Securityheaders.io"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/HTTP_Strict_Transport_Security",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high", "medium"],
        "statistics": {
            "good": [{'label': "Stats has", 'explanation': 'Strict-Transport-Security header present.'}],
            "medium": [{'label': "Stats hasn't", 'explanation': 'Missing Strict-Transport-Security header.'}],
            "bad": []
        },
        "category": ['website']
    },

    "http_security_header_x_frame_options": {
        "name": "http_security_header_x_frame_options",
        "second opinion links": [{
            "url": "https://securityheaders.io/?q=${url.url}",
            "language": "EN",
            "provider": "Securityheaders.io"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Clickjacking",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["medium"],
        "statistics": {
            "good": [{'label': "Stats has", 'explanation': 'X-Frame-Options header present.'}],
            "medium": [{'label': "Stats hasn't", 'explanation': 'Missing X-Frame-Options header.'}],
            "bad": []
        },
        "category": ['website']
    },

    "http_security_header_x_content_type_options": {
        "name": "http_security_header_x_content_type_options",
        "second opinion links": [{
            "url": "https://securityheaders.io/?q=${url.url}",
            "language": "EN",
            "provider": "Securityheaders.io"
        }],
        "documentation links": [{
            "url": "https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xcto",
            "language": "EN",
            "provider": "OWASP"
        }],
        "relevant impacts": ["low"],
        "statistics": {
            "good": [{'label': "Stats has", 'explanation': 'X-Content-Type-Options header present.'}],
            "medium": [{'label': "Stats hasn't", 'explanation': 'Missing X-Content-Type-Options header.'}],
            "bad": []
        },
        "category": ['website']
    },

    "http_security_header_x_xss_protection": {
        "name": "http_security_header_x_xss_protection",
        "second opinion links": [{
            "url": "https://securityheaders.io/?q=${url.url}",
            "language": "EN",
            "provider": "Securityheaders.io"
        }],
        "documentation links": [{
            "url": "https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xxxsp",
            "language": "EN",
            "provider": "OWASP"
        }],
        "relevant impacts": ["low"],
        "statistics": {
            "good": [{'label': "Stats has", 'explanation': 'X-XSS-Protection header present.'}],
            "medium": [{'label': "Stats hasn't", 'explanation': 'Missing X-XSS-Protection header.'}],
            "bad": []
        },
        "category": ['website']
    },

    "internet_nl_mail_starttls_tls_available": {
        "name": "internet_nl_mail_starttls_tls_available",
        "second opinion links": [{
            "url": "https://internet.nl/mail/${url.url}/",
            "language": "EN",
            "provider": "Internet.nl"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Opportunistic_TLS",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["high"],
        "statistics": {
            "good": [{'label': "STARTTLS Available", 'explanation': 'STARTTLS Available'},
            {'label': "Not relevant anymore", 'explanation': 'Not relevant. This address does not receive mail anymore.'}],
            "medium": [],
            "bad": [{'label': "STARTTLS Missing", 'explanation': 'STARTTLS Missing'}]
        },
        "category": ['confidentiality', 'integrity']
    },

    "internet_nl_mail_auth_spf_exist": {
        "name": "internet_nl_mail_auth_spf_exist",
        "second opinion links": [{
            "url": "https://internet.nl/mail/${url.url}/",
            "language": "EN",
            "provider": "Internet.nl"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/Sender_Policy_Framework",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["medium"],
        "statistics": {
            "good": [{'label': "SPF Available", 'explanation': 'SPF Available'},
            {'label': "Not relevant anymore", 'explanation': 'Not relevant. This address does not receive mail anymore.'}],
            "medium": [{'label': "SPF Missing", 'explanation': 'SPF Missing'}],
            "bad": []
        },
        "category": ['confidentiality', 'integrity']
    },

    "internet_nl_mail_auth_dkim_exist": {
        "name": "internet_nl_mail_auth_dkim_exist",
        "second opinion links": [{
            "url": "https://internet.nl/mail/${url.url}/",
            "language": "EN",
            "provider": "Internet.nl"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/DomainKeys_Identified_Mail",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["medium"],
        "statistics": {
            "good": [{'label': "DKIM Available", 'explanation': 'DKIM Available'},
            {'label': "Not relevant anymore", 'explanation': 'Not relevant. This address does not receive mail anymore.'}],
            "medium": [{'label': "DKIM Missing", 'explanation': 'DKIM Missing'}],
            "bad": []
        },
        "category": ['confidentiality', 'integrity']
    },

    "internet_nl_mail_auth_dmarc_exist": {
        "name": "internet_nl_mail_auth_dmarc_exist",
        "second opinion links": [{
            "url": "https://internet.nl/mail/${url.url}/",
            "language": "EN",
            "provider": "Internet.nl"
        }],
        "documentation links": [{
            "url": "https://en.wikipedia.org/wiki/DMARC",
            "language": "EN",
            "provider": "Wikipedia"
        }],
        "relevant impacts": ["medium"],
        "statistics": {
            "good": [{'label': "DMARC Available", 'explanation': 'DMARC Available'},
            {'label': "Not relevant anymore", 'explanation': 'Not relevant. This address does not receive mail anymore.'}],
            "medium": [{'label': "DMARC Missing", 'explanation': 'DMARC Missing'}],
            "bad": []
        },
        "category": ['confidentiality', 'integrity']
    },

};

// todo: define this order somewhere else. Config option or something.
let ordered_issues = [
    issues['DNSSEC'],
    issues["tls_qualys_certificate_trusted"],
    issues["tls_qualys_encryption_quality"],
    issues["plain_https"],
    issues["ftp"],
    issues["internet_nl_mail_starttls_tls_available"],
    issues["internet_nl_mail_auth_spf_exist"],
    issues["internet_nl_mail_auth_dkim_exist"],
    issues["internet_nl_mail_auth_dmarc_exist"],
    issues["http_security_header_strict_transport_security"],
    issues["http_security_header_x_frame_options"],
    issues["http_security_header_x_content_type_options"],
    issues["http_security_header_x_xss_protection"],
];

// what issues are at url level
let url_issue_names = [
    issues['DNSSEC']['name'],
];

// what issues are at endpoint level
let endpoint_issue_names = [
    issues["tls_qualys_certificate_trusted"]['name'],
    issues["tls_qualys_encryption_quality"]['name'],
    issues["plain_https"]['name'],
    issues["ftp"]['name'],
    issues["http_security_header_strict_transport_security"]['name'],
    issues["http_security_header_x_frame_options"]['name'],
    issues["http_security_header_x_content_type_options"]['name'],
    issues["http_security_header_x_xss_protection"]['name'],
    issues['internet_nl_mail_starttls_tls_available']['name'],
    issues['internet_nl_mail_auth_spf_exist']['name'],
    issues['internet_nl_mail_auth_dkim_exist']['name'],
    issues['internet_nl_mail_auth_dmarc_exist']['name'],
];

function debounce(func, wait, immediate) {
    let timeout;
    return function () {
        let context = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function () {
            timeout = null;
            if (!immediate) func.apply(context, args);
        }, wait);
        if (immediate && !timeout) func.apply(context, args);
    };
}


// https://stackoverflow.com/questions/15762768/javascript-math-round-to-two-decimal-places
function roundTo(n, digits) {
    if (digits === undefined) {
        digits = 0;
    }

    let multiplicator = Math.pow(10, digits);
    n = parseFloat((n * multiplicator).toFixed(11));
    let test = (Math.round(n) / multiplicator);
    return +(test.toFixed(digits));
}


// support for week numbers in javascript
// https://stackoverflow.com/questions/7765767/show-week-number-with-javascript
Date.prototype.getWeek = function () {
    let onejan = new Date(this.getFullYear(), 0, 1);
    return Math.ceil((((this - onejan) / 86400000) + onejan.getDay() + 1) / 7);
};

// support for an intuitive timestamp
// translation?
Date.prototype.humanTimeStamp = function () {
    return this.getFullYear() + " " + gettext("week") + " " + this.getWeek();
};

// todo: the week should also be in the state.
// and this is where we slowly creep towards vuex.
const state_mixin = {
    data: {
        layer: "",
        country: ""
    },
    // watchers have implicit behaviour: if code is depending on two variables, setting each one seperately
    // causes wathchers to execute the code twice. Therefore the watcher has been replaced by a function.

    methods: {
       set_state: function(country, layer) {

           // do not set the state or call any action when the html element has not been created. See configuration.
           if (!document.getElementById(this.$options.el.replace("#","")))
               return;

           // prevent loading when things didn't change.
           if (country === this.country && layer === this.layer)
               return;

           this.country = country;
           this.layer = layer;
           this.load();
       }
    },
    computed: {
        valid_state: function(){
            if (!this.country || !this.layer)
                return false;
            return true;
        }
    }
};

const new_state_mixin = {
    // new state mixin that is pure functional, and does not depend on html elements
    data: {
        state: {
            'country': "",
            'layer': "",
            'week': 0,
        },
    },
    // watchers have implicit behaviour: if code is depending on two variables, setting each one seperately
    // causes wathchers to execute the code twice. Therefore the watcher has been replaced by a function.

    methods: {

        // make sure the first state set is as atomic as possible.
        set_state: function(country, layer, week=0) {
            // atomic change:
            this.state = {'country': country, 'week': week, 'layer': layer};
       }
    },
    watch: {
        state: function(){
            this.load()
        }
    }
};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

let default_color_scheme = {
    'high_background': 'rgba(255, 99, 132, 0.2)',
    'high_border': 'rgba(255, 99, 132, 0.2)',
    'medium_background': 'rgba(255, 102, 0, 0.2)',
    'medium_border': 'rgba(255,102,0,1)',
    'low_background': 'rgba(255, 255, 0, 0.2)',
    'low_border': 'rgba(255,255,0,1)',
    'good_background': 'rgba(50, 255, 50, 0.2)',
    'good_border': 'rgba(50, 255, 50, 1)',
    'addresses_background': 'rgba(0, 0, 0, 0.2)',
    'addresses_border': 'rgba(0,0,0,1)',
    'services_background': 'rgba(0, 40, 255, 0.2)',
    'services_border': 'rgba(0,40,255,1)',
};

const report_mixin = {
    methods: {

    }
};


const translation_mixin = {
    methods: {
        translate: function (string) {
            return gettext(string);
        }
    }
};


// This helps showing some regions that might not be set to 'displayed' and is for demo purposes
function germany() {
    vueMapStateBar.countries = ["NL", "DE"];
    vueMapStateBar.layers = ["bundesland", "regierungsbezirk", "landkreis_kreis_kreisfreie_stadt",
    "samtgemeinde_verwaltungsgemeinschaft"];
}

// meant to be called from console: vueMap.preview('NL', 'municipality');
function preview(country, layer){
    // also show tiles on map.
    map.loadTiles();
    vueMap.country = country;
    vueMap.layer = layer;
    vueMap.load();
}


const chart_mixin = {
    props: {
        data: {type: Array, required: true},
        axis: {type: Array, required: false},
        color_scheme: {type: Object, required: false}
    },
    data: {
        // [Vue warn]: The "data" option should be a function that returns a per-instance value in component definitions.
        // so what should i use then? No suggestion?
        chart: {}
    },
    render: function(createElement) {
        return createElement(
            'canvas',
            {
                ref: 'canvas'
            },
        )
    },
    mounted: function () {
        this.buildChart();
        this.renderData();
    },
    watch: {
        data: function(newsetting, oldsetting){
            this.renderData();
        },

        // Supports changing the colors of this graph ad-hoc.
        // charts.js is not reactive.
        color_scheme: function(newsetting, oldsetting){
            this.renderData();
        },
    }
};

Vue.component('vulnerability-chart', {
    mixins: [chart_mixin],

    methods: {
        // let's see if we can do it even better.
        buildChart: function(){
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'line',
                data: {
                    datasets: []
                },
                options: {
                    legend: {
                        display: false
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: 'Risks over time'
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                    scales: {
                        xAxes: [{
                            display: true,
                            type: 'time',
                            distribution: 'linear',
                            time: {
                                unit: 'month'
                            },
                            scaleLabel: {
                                display: false,
                                labelString: 'Month'
                            }
                        }],
                        yAxes: [{
                            display: true,
                            stacked: true,
                            scaleLabel: {
                                display: false,
                                labelString: 'Value'
                            }
                        }]
                    }
                }
            });
        },

        renderData: function(){
            let data = this.data;

            let labels = Array();
            let high = Array();
            let medium = Array();
            let low = Array();

            for(let i=0; i<data.length; i++){
                labels.push(data[i].date);
                high.push(data[i].high);
                medium.push(data[i].medium);
                low.push(data[i].low);
            }

            this.chart.data.labels = labels;
            this.chart.data.datasets = [{
                        label: '# High risk',
                        data: high,
                        backgroundColor: this.color_scheme.high_background,
                        borderColor: this.color_scheme.high_border,
                        borderWidth: 1,
                        lineTension: 0,
                        hidden: !this.axis.includes('high')
                    },
                    {
                        label: '# Medium risk',
                        data: medium,
                        backgroundColor: this.color_scheme.medium_background,
                        borderColor: this.color_scheme.medium_border,
                        borderWidth: 1,
                        lineTension: 0,
                        hidden: !this.axis.includes('medium')
                    },
                    {
                        label: '# Low risk',
                        data: low,
                        backgroundColor: this.color_scheme.low_background,
                        borderColor: this.color_scheme.low_border,
                        borderWidth: 1,
                        lineTension: 0,
                        hidden: !this.axis.includes('low')
                    },
                ];

            this.chart.update();
        }
    }
});

// not because pie charts are useful, but because they look cool.
// https://www.businessinsider.com/pie-charts-are-the-worst-2013-6?international=true&r=US&IR=T
// https://www.datapine.com/blog/notorious-pie-charts/
Vue.component('vulnerability-donut', {
    mixins: [chart_mixin],

    methods: {

        buildChart: function(){
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'doughnut',
                data: {

                },
                options: {
                    legend: {
                        display: true
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: "Today's risk overview",
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                }
            });

        },
        renderData: function(){
            let data = this.data;

            let labels = Array();
            let high = Array();
            let medium = Array();
            let low = Array();
            let ok = Array();

            high.push(data[data.length-1].high);
            medium.push(data[data.length-1].medium);
            low.push(data[data.length-1].low);
            ok.push(data[data.length-1].ok);

            let backgroundColor = [];
            let borderColor = [];
            let chartdata = [];

            if (this.axis.includes('high')){
                backgroundColor.push(this.color_scheme.high_background);
                borderColor.push(this.color_scheme.high_border);
                labels.push('# High risk');
                chartdata.push(high);
            }
            if (this.axis.includes('medium')){
                backgroundColor.push(this.color_scheme.medium_background);
                borderColor.push(this.color_scheme.medium_border);
                labels.push('# Medium risk');
                chartdata.push(medium);

            }
            if (this.axis.includes('low')){
                backgroundColor.push(this.color_scheme.low_background);
                borderColor.push(this.color_scheme.low_border);
                labels.push('# Low risk');
                chartdata.push(low);
            }

            // Only include OK in the donuts, not the graphs. Otherwise the graphs become unreadable (too much data)
            backgroundColor.push(this.color_scheme.good_background);
            borderColor.push(this.color_scheme.good_border);
            labels.push('# No risk');
            chartdata.push(ok);

            this.chart.data.labels = labels;
            this.chart.data.datasets = [{
                data: chartdata,
                backgroundColor: backgroundColor,
                borderColor: borderColor,
                borderWidth: 1,
                lineTension: 0,
            }];

            this.chart.update();
        }
    }
});

Vue.component('connectivity-chart', {
    mixins: [chart_mixin],

    methods: {
        buildChart: function() {
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'line',
                data: {

                },
                options: {
                    legend: {
                        display: false
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: 'Internet connectivity'
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                    scales: {
                        xAxes: [{
                            display: true,
                            type: 'time',
                            distribution: 'linear',
                            time: {
                                unit: 'month'
                            },
                            scaleLabel: {
                                display: false,
                                labelString: 'Month'
                            }
                        }],
                        yAxes: [{
                            display: true,
                            stacked: false,
                            scaleLabel: {
                                display: false,
                                labelString: 'Value'
                            },
                            ticks: {
                                min: 0,
                            }
                        }]
                    }
                }
            });
        },

        renderData: function(){
            let data = this.data;

            let labels = Array();

            let urls = Array();
            let endpoints = Array();

            for(let i=0; i<data.length; i++){
                labels.push(data[i].date);
                urls.push(data[i].urls);
                endpoints.push(data[i].endpoints);
            }

            this.chart.data.labels = labels;
            this.chart.data.datasets = [{
                label: '# Internet Adresses',
                data: urls,
                backgroundColor: this.color_scheme.addresses_background,
                borderColor: this.color_scheme.addresses_border,
                borderWidth: 1,
                lineTension: 0
            },
            {
                label: '# Services',
                data: endpoints,
                backgroundColor: this.color_scheme.services_background,
                borderColor: this.color_scheme.services_border,
                borderWidth: 1,
                lineTension: 0
            }];

            this.chart.update();
        }
    }
});

const data_loader_mixin = {
    // might need a callback function after data loading is done...
    data: {
            data: []
    },

    methods: {
        load_data_from_url: function(url){
            fetch(url)
                    .then(response => response.json()).then(data => {
                        this.data = data;
            }).catch((fail) => {console.log('An error occurred: ' + fail)});
        }
    }
};

function views(autoload_default_map_data=true) {

    window.vueDomainlist = new Vue({
        name: "domainlist",

        mixins: [state_mixin],
        el: '#domainlist',
        template: '#domainlist_template',

        data: {urls: Array},
        methods: {
            colorize: function (high, medium, low) {
                if (high > 0) return "high";
                if (medium > 0) return "medium";
                return "good";
            },
            load: debounce(function (organization_id, weeks_back) {

                if (!weeks_back)
                    weeks_back = 0;

                if (!this.country || !this.layer)
                    return;

                // symptom of state mixing loads this even though it's not needed (and doesn't have the right arguments)
                if (!organization_id)
                    return;

                $.getJSON('/data/report/' + this.country + '/' + this.layer + '/' + organization_id + '/' + weeks_back, function (data) {
                    vueDomainlist.urls = data.calculation["organization"]["urls"];
                });
            }, 42)
        }
    });


    // ticker
    // todo: determine the scroll time dynamically, as it might be too fast / too slow depending on the data.
    window.vueTicker = new Vue({
        name: "ticker",

        mixins: [state_mixin],
        el: '#ticker',
        data: {
            tickertext: "",
            visible: false,
            changes: Array(),
            slogan: ""
        },
        mounted: function () {
            this.visible = !(TICKER_VISIBLE_VIA_JS_COMMAND === 'true');
        },
        methods: {
            toggleVisibility: function (){
              this.visible = !this.visible;
              // evil fix.
              setTimeout(function(){ vueTicker.setMarqueeSpeed()}, 2000);
            },
            setMarqueeSpeed: function (){
                // Time = Distance/Speed
                // https://stackoverflow.com/questions/38118002/css-marquee-speed
                // todo: use the virtual dom instead of real dom...
                try {
                    var spanSelector = document.getElementById("marquee").querySelector("span");
                    var timeTaken = this.tickertext.length / 20;  // about N characters per second.
                    spanSelector.style.animationDuration = timeTaken + "s";
                } catch(err) {
                    console.log("Marquee was not visible in the DOM.")
                    // Weird is that when the property is set when hiding... it isn't stored. probably
                    // because it affects the real dom only, not the virtual dom.
                }
            },
            colorize: function (value, rank) {
                if (value === 0)
                    return "black";

                if (rank === "high")
                    return "high";

                if (rank === "medium")
                    return "medium";

                if (rank === "low")
                    return "low";

                return "good";
            },
            arrow: function(value, rank){
                if (value > 0)
                    return "<a class='high'>▲</a>+"+ value + " ";
                if (value === 0)
                    return "▶0";
                if (value < 0)
                    return "<a class='good'>▼</a>-" + (value * -1) + " ";
            },
            get_tickertext: function() {
                // weird that this should be a function...
                return this.tickertext;
            },
            load: function () {

                if (!this.country || !this.layer)
                    return;


                fetch('/data/ticker/' + this.country + '/' + this.layer + '/0/0').then(response => response.json()).then(data => {

                    // reset the text for the new data.
                    this.tickertext = "";

                    this.changes = data.changes;
                    this.slogan = data.slogan;

                    for (let j=0; j<this.changes.length; j++){
                        let change = this.changes[j];

                        this.tickertext += " &nbsp; &nbsp; " + change['organization'].toUpperCase() + " &nbsp; ";

                        if (!change['high_now'] && !change['medium_now'] && !change['low_now']){

                            this.tickertext += "<span class='goodrow' title='---------------------------------------" +
                                "------'>PERFECT</span>  ";

                        } else {

                            this.tickertext += "<span class='" + this.colorize(change['high_now'], 'high') + "row'>" + change['high_now'] + "</span>";
                            this.tickertext += this.arrow(change['high_changes'], 'high');
                            this.tickertext += " &nbsp; ";

                            this.tickertext += "<span class='" + this.colorize(change['medium_now'], 'medium') + "row'>" + change['medium_now'] + "</span>";
                            this.tickertext += this.arrow(change['medium_changes'], 'medium');
                            this.tickertext += " &nbsp; ";

                            this.tickertext += "<span class='" + this.colorize(change['low_now'], 'low') + "row'>" + change['low_now'] + "</span>";
                            this.tickertext += this.arrow(change['low_changes'], 'low');
                            this.tickertext += "  ";

                        }

                        if (j % 10 === 0) {
                            this.tickertext += " &nbsp; &nbsp; <b> " + this.slogan.toUpperCase() + " </b> &nbsp; "
                        } else {
                            // show space between each rating, except the first / after the closing message
                            this.tickertext += " &nbsp; ";
                        }
                    }

                    if (this.visible)
                        this.setMarqueeSpeed()

                }).catch((fail) => {console.log('A Ticker error occurred: ' + fail)});
            }
        }
    });

    /*
    * {
          "tls_qualys": [
            {
              "old": {
                "date": "2018-02-23T08:02:52.779740+00:00",
                "high": 1277,
                "medium": 18,
                "low": 783
              },
              "new": {
                "date": "2018-03-26T08:02:52.779774+00:00",
                "high": 916,
                "medium": 3,
                "low": 730
              },
              "improvements": {
                "high": 361,
                "medium": 15,
                "low": 53
              }
            }
          ],
          "security_headers_strict_transport_security": [
    * */


    window.vueFullScreenReport = new Vue({
        name: "fullscreenreport",
        el: '#fullscreenreport',
        mixins: [state_mixin, report_mixin, translation_mixin],
        methods: {
            show: function () {
                this.visible = true;
            },
            hide: function () {
                this.visible = false;
            },
        }
    });

    // there are some issues with having the map in a Vue. Somehow the map doesn't
    // render. So we're currently not using that feature over there.
    // It's also hard, since then we have to have themap, historycontrol, fullscreenreport, domainlist
    // it's just too much in single vue.
    // also: the fullscreen report only loads from something ON the map.
    // and all of this for a loading indicator per vue :))
    // knowing fullscreen here would be nice...
    // state is managed here.
    window.vueMap = new Vue({
        name: "Map",

        mounted: function () {
            // wait until the default layer and default languages have been set...

            // initial load.
            if (!autoload_default_map_data) {
                // make sure this only works once
                console.log("1/2 Explicitly disabled automatic loading of default map data. Please load map data yourself.");
                return;
            }
            this.load(0)
        },
        mixins: [state_mixin, translation_mixin],

        el: '#historycontrol',
        template: '#historycontrol_template',
        data: {
            // # historyslider
            loading: false,
            week: 0,
            selected_organization: -1,
            features: null,

            // keep track if we need to show everything, or can stay zoomed in:
            previously_loaded_country: null,
            previously_loaded_layer: null,

            displayed_issue: "",

            issues: ordered_issues
        },
        computed: {
            visibleweek: function () {
                let x = new Date();
                x.setDate(x.getDate() - this.week * 7);
                return x.humanTimeStamp();
            },


        },
        watch: {
            displayed_issue: function(newsetting, oldsetting){
                this.load(this.week)
            },
        },
        methods: {
            clear_filter: function (){
                this.displayed_issue = "";
            },
            set_state: function(country, layer, skip_map){
                console.log("Set map/site state");
                this.country = country;
                this.layer = layer;

                // The first time the map is not allowed to load in any regards:
                // set state is a second attempt of loading data via the layernavbar
                if (!autoload_default_map_data) {
                    // make sure this only works once
                    autoload_default_map_data = true;
                    console.log("2/2 Explicitly disabled automatic loading of default map data. Please load map data yourself.");
                    return;
                }


                // skip_map is used in loading the defaults, where the map is already (probably) loaded.
                // The first time the map loads based on the default settings in the backend. This shows the map
                // faster as it saves a roundtrip. Loading the map faster is a better experience for visitors.
                if (skip_map) {
                    console.log('Skipping the map on the default load.');
                } else {
                    vueMap.show_week();
                }

                app.set_state(this.country, this.layer);

                vueDomainlist.set_state(this.country, this.layer);
                vueTicker.set_state(this.country, this.layer);

                // this needs state as the organizaton name in itself is not unique.
                vueFullScreenReport.set_state(this.country, this.layer);
            },
            // slowly moving the map into a vue. NOPE. denied.
            load: function (week) {
                if (week === undefined)
                    week = 0;

                this.loading = true;

                if (this.preview){
                    this.show_data(`/data/map/${this.country}/${this.layer}/${week * 7}/${this.displayed_issue}/`);
                    return;
                }

                // the first time the map defaults are loaded, this saves a trip to the server of what the defaults are
                // it's possible that this is slower than the rest of the code, and thus a normal map is loaded.
                // it is possible to override the default using the initial_map_data_url parameter.
                if (!this.country || !this.layer) {
                    if (initial_map_data_url !== undefined && initial_map_data_url !== '') {
                        this.show_data(initial_map_data_url);
                    } else {
                        this.show_data(`/data/map_default/${week * 7}/${this.displayed_issue}/`);
                    }
                    return;
                }

                this.show_data(`/data/map/${this.country}/${this.layer}/${week * 7}/${this.displayed_issue}/`);

            },
            show_data: function(url) {
                console.log(`Loading map data from: ${url}`);
                fetch(url).then(response => response.json()).then(data => {
                    this.loading = true;

                    // Don't need to zoom out when the filters change, only when the layer/country changes.
                    let fitBounds = false;
                    if (this.previously_loaded_country !== this.country || this.previously_loaded_layer !== this.layer)
                        fitBounds = true;

                    map.plotdata(data, fitBounds);
                    this.previously_loaded_country = this.country;
                    this.previously_loaded_layer = this.layer;

                    // make map features (organization data) available to other vues
                    // do not update this attribute if an empty list is returned as currently
                    // the map does not remove organizations for these kind of responses.
                    if (data.features.length > 0) {
                        this.features = data.features;
                    }
                    this.loading = false;
                }).catch((fail) => {
                    console.log('A map error occurred: ' + fail);
                    // allow you to load again:
                    this.loading = false;
                });
            },
            next_week: function () {
                if (this.week > 0) {
                    this.week -= 1;
                    this.show_week();
                }
            },
            previous_week: function () {
                // caused 1, 11, 111 :) lol
                if (this.week <= 52) {
                    this.week += 1;
                    this.show_week();
                }
            },
            show_week: function (e) {
                if (e) {
                    this.week = parseInt(e.target.value);
                }

                this.load(this.week);

                // nobody understands that when you drag the map slider, the rest
                // of the site and all reports are also old.
                // so don't. Add matching UI elsewhere...

                if (this.selected_organization > -1) {
                    // console.log(selected_organization);
                    // todo: requests the "report" page 3x.
                    // due to asyncronous it's hard to just "copy" results.
                    // vueReport.load(vueMap.selected_organization, this.week);
                    // vueFullScreenReport.load(vueMap.selected_organization, this.week);
                    vueDomainlist.load(this.selected_organization, this.week);
                }
            }
        }
    });

    // merged layer and country navbars to have a single point of setting the state at startup.
    window.vueMapStateBar = new Vue({
        name: "MapStateBar",
        mixins: [translation_mixin],
        el: '#map_state_bar',

        data: {
            layers: [""],
            countries: [""],
            selected_layer: "",
            selected_country: "",
        },

        mounted: function() {
            this.get_defaults();
        },

        // todo: load the map without parameters should result in the default settings to save a round trip.
        methods: {
            get_defaults: function() {
                fetch('/data/defaults/').then(response => response.json()).then(data => {
                    this.selected_layer = data.layer;
                    this.selected_country = data.country;
                    // countries are already loaded in the django template for faster menus
                    // then load this as fast as you can.
                    this.get_layers();
                    vueMap.set_state(this.selected_country, this.selected_layer, true);
                }).catch((fail) => {console.log('An error occurred: ' + fail)});
            },
            get_countries: function() {
                fetch('/data/countries/').then(response => response.json()).then(countries => {
                    // it's fine to clear the navbar if there are no layers for this country
                    this.countries = countries;

                    // this is async, therefore you cannot call countries and then layers. You can only do while...
                    this.get_layers();
                }).catch((fail) => {console.log('An error occurred: ' + fail)});
            },
            get_layers: function() {
                fetch('/data/layers/' + this.selected_country + '/').then(response => response.json()).then(layers => {
                    // it's fine to clear the navbar if there are no layers for this country
                    this.layers = layers;
                    app.layers = layers;  // todo: Move this to app... so layers will be reactive.
                });
            },
            set_country: function(country_name) {
                // when changing the country, a new set of layers will appear.
                this.selected_country = country_name;

                // the first layer of the country is the default. Load the map and set that one.
                fetch('/data/layers/' + this.selected_country + '/').then(response => response.json()).then(layers => {
                    // yes, there are layers.
                    if (layers.length) {
                        this.layers = layers;
                        this.selected_layer = layers[0];
                        vueMap.set_state(this.selected_country, this.selected_layer);
                    } else {
                        this.layers = [""];
                        vueMap.set_state(this.selected_country, this.selected_layer);
                    }
                });
            },
            set_layer: function(layer_name){
                this.selected_layer = layer_name;
                vueMap.set_state(this.selected_country, this.selected_layer);
            }
        }
    });




    window.vueInfo = new Vue({
        name: 'infobox',
        el: '#infobox',
        template: '#map_item_hover',

        data:{
            properties: {
                organization_name: "",
                high: 0,
                medium: 0,
                low: 0,
                high_urls: 0,
                medium_urls: 0,
                low_urls: 0,
                total_urls: 0
            }
        },

        computed: {
            high: function () {
                return this.perc(this.properties.high_urls, this.properties.total_urls);
            },
            medium: function () {
                return this.perc(this.properties.medium_urls, this.properties.total_urls);
            },
            low: function () {
                return this.perc(this.properties.low_urls, this.properties.total_urls);
            },
            perfect: function () {
                return this.perc(this.properties.total_urls -
                    (this.properties.low_urls + this.properties.medium_urls + this.properties.high_urls),
                    this.properties.total_urls);
            },
            unknown: function () {
                return 0;
            },
            total: function(){
                return this.properties.high + this.properties.medium + this.properties.low;
            }
        },

        methods: {
            perc: function (amount, total) {
                return (!amount || !total) ? "0%" : roundTo(amount / total * 100, 2) + "%";
            },
            showreport: function(organization_id) {
                map.showreport_direct(organization_id);
            }
        }

    });

    window.app = new Vue({
        i18n,
        el: '#app',
        name: 'app',
        mixins: [new_state_mixin],

        data: {
            issues: ordered_issues,
            color_scheme: default_color_scheme,
            layers: [],

            organization: null,

            // determines what week the data is shown from. Should be part of state.
            week: 0,

            // the app state is leading for the rest. So we should have a state value here, and when that is changed,
            // it is reflected through the app. (probably already so, but not explicit enough.)
        },

        // expected by state_mixin
        methods: {
          load: function(){}
        },

        mounted: function(){
            console.log("App loaded...")
        },

        computed: {
            // load list of organizations from map features
            // todo: this doesn't update when region changes.
            // todo: get map data from somewhere else. This should be placed elsewhere.
            organizations: function () {
                if (vueMap.features != null) {
                    let organizations = vueMap.features.map(function (feature) {
                        return {
                            "id": feature.properties.organization_id,
                            "label": feature.properties.organization_name,
                            "name": feature.properties.organization_name,
                            "slug": feature.properties.organization_slug
                        }
                    });
                    return organizations.sort(function (a, b) {
                        if (a['name'] > b['name']) return 1;
                        if (a['name'] < b['name']) return -1;
                        return 0;
                    });
                }
            }
        },
    });
    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    // vueMap.load(0);
}
