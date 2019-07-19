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


function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

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

function views() {


    window.vueFullScreenReport = new Vue({
        name: "fullscreenreport",
        el: '#fullscreenreport',
        mixins: [state_mixin, report_mixin, translation_mixin],
        data: {
            visible: false,
        },
        methods: {
            show: function () {
                this.visible = true;
            },
            hide: function () {
                this.visible = false;
            },
            load: function (){}
        }
    });

    const app = new Vue({
        i18n,
        el: '#app',
        name: 'app',
        mixins: [new_state_mixin],

        data: {
            // A reference to leaflet, so we can call leaflet functions.
            L: L,

            // These are all issues in websecmap that can be shown in the front end. Randomly ordered:
            all_issues: {

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

            },

            // this is the correctly ordered set with issues. in an easy list.
            issues: [
                this.all_issues['DNSSEC'],
                this.all_issues["tls_qualys_certificate_trusted"],
                this.all_issues["tls_qualys_encryption_quality"],
                this.all_issues["plain_https"],
                this.all_issues["ftp"],
                this.all_issues["internet_nl_mail_starttls_tls_available"],
                this.all_issues["internet_nl_mail_auth_spf_exist"],
                this.all_issues["internet_nl_mail_auth_dkim_exist"],
                this.all_issues["internet_nl_mail_auth_dmarc_exist"],
                this.all_issues["http_security_header_strict_transport_security"],
                this.all_issues["http_security_header_x_frame_options"],
                this.all_issues["http_security_header_x_content_type_options"],
                this.all_issues["http_security_header_x_xss_protection"],
            ],

            // These issues are specific for the URL level, others are on endpoint level.
            url_issue_names: [
                this.all_issues['DNSSEC']['name'],
            ],

            available_color_schemes: {
                trafficlight: "/static/css/colors.trafficlight.css",
                pink: "/static/css/colors.trafficlight.css",
                deutranopia: "/static/css/colors.deutranopia.css",
            },

            active_color_scheme: "trafficlight",
            colors_used_for_charts: {
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
            },

            available_themes: {
                default: {css: "/static/css/vendor/bootstrap.min.css", map_tilelayer: 'light'},
                darkly: {css: "/static/css/vendor/bootstrap-darkly.min.css", map_tilelayer: 'dark'},
            },

            layers: [],

            // todo: this should come FROM websecmap and should be then avialble in reports.. or we
            // should let the reports method get all options itself. This is now a placeholder.
            organizations: [],

            // the app state is leading for the rest. So we should have a state value here, and when that is changed,
            // it is reflected through the app. (probably already so, but not explicit enough.)

            organization: 0
        },


        methods: {
            // expected by state_mixin
            load: function(){},

            // switch themes
            // http://jsfiddle.net/82AsF/

            set_theme: function(theme_name) {
                let possible_themes = Object.keys(this.available_themes);
                if (!possible_themes.includes(theme_name)) {
                    console.log(`Theme not available. Available schemes are: ${possible_themes}.`)
                }

                let theme_link = 'link[href="'+$('link#active_theme').attr('href') + '"]';
                $(theme_link).attr('href', this.available_themes.theme_name.css);
            },

            set_color_scheme: function(scheme_name) {
                let schemes = Object.keys(this.available_color_schemes);
                if (!schemes.includes(scheme_name)){
                    console.log(`Color scheme not available. Available schemes are: ${schemes}.`)
                }
                this.active_color_scheme = scheme_name;

                // this overrides the <link id="colorscheme" in the body to point to a new stylesheet.
                // this change is supported by most browsers and takes some time to process...
                let colorscheme_link = 'link[href="'+$('link#colorscheme').attr('href') + '"]';
                $(colorscheme_link).attr('href', `/static/css/colors.${scheme_name}.css`);

                setTimeout(this.set_graph_colorscheme, 2000);
                return true;
            },

            set_graph_colorscheme: function(){
                // This is a terrible solution to retrieve the active colors from an 'inkpot' on the body of the page.
                // The inkpot contains the colors of the currently active CSS file.
                // It is not possible to obtain these color reference in javascript by querying the CSS file...
                let charts_high = $('.charts_high');
                let charts_medium = $('.charts_medium');
                let charts_low = $('.charts_low');
                let charts_good = $('.charts_good');
                let charts_connectivity_internet_adresses = $('.charts_connectivity_internet_adresses');
                let charts_connectivity_services = $('.charts_connectivity_services');

                this.colors_used_for_charts = {
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
            }
        },

        mounted: function(){
            console.log("App loaded...")
        },
    });
    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    // vueMap.load(0);
}
