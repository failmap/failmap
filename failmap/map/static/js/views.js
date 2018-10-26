// We've taken some time to determine what would be a non-"all-in" approach to build this software.
// Vue indeed is incrementally adoptable and easy to write and learn.
// Angular was off the table due to bad experiences, React seems to intense, especially given javascripts syntax
// oh, and the react anti-patent clause is a big no.
// // https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc

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
        category: "",
        country: ""
    },
    // watchers have implicit behaviour: if code is depending on two variables, setting each one seperately
    // causes wathchers to execute the code twice. Therefore the watcher has been replaced by a function.

    methods: {
       set_state: function(country, category) {

           // do not set the state or call any action when the html element has not been created. See configuration.
           if (!document.getElementById(this.$options.el.replace("#","")))
               return;

           // prevent loading when things didn't change.
           if (country === this.country && category === this.category)
               return;

           this.country = country;
           this.category = category;
           this.load();
       }
    }
};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const report_mixin = {
    data: {
        calculation: '',
        rating: 0,
        points: 0,
        high: 0,
        medium: 0,
        low: 0,
        when: 0,
        twitter_handle: '',
        name: "",
        urls: Array,
        mailto: document.head.querySelector("[name=mailto]").getAttribute('content'),
        selected: null,
        loading: false,
        visible: false,  // fullscreenreport
        promise: false,
    },
    // https://vuejs.org/v2/api/#updated
    updated: function () {
      this.$nextTick(function () {
          lazyload()
      })
    },
    methods: {

        vulnerability_timeline_for_organization: function(organization_id){
            fetch('/data/organization_vulnerability_timeline/' + organization_id)
                .then(response => response.json()).then(data => {
                // data

                let labels = Array();
                let high = Array();
                let medium = Array();
                let low = Array();

                let urls = Array();
                let endpoints = Array();

                for(let i=0; i<data.length; i++){
                    labels.push(data[i].date);
                    high.push(data[i].high);
                    medium.push(data[i].medium);
                    low.push(data[i].low);
                    urls.push(data[i].urls);
                    endpoints.push(data[i].endpoints);
                }

                let ctx = document.getElementById("organization_vulnerability_timeline").getContext('2d');
                let myChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,

                        datasets: [{
                            label: '# High risk',
                            data: high,
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            borderColor: 'rgba(255,99,132,1)',
                            borderWidth: 1
                        },
                        {
                            label: '# Medium risk',
                            data: medium,
                            backgroundColor: 'rgba(255, 102, 0, 0.2)',
                            borderColor: 'rgba(255,102,0,1)',
                            borderWidth: 1
                        },
                        {
                            label: '# Low risk',
                            data: low,
                            backgroundColor: 'rgba(255, 255, 0, 0.2)',
                            borderColor: 'rgba(255,255,0,1)',
                            borderWidth: 1
                        },
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        title: {
                            display: true,
                            text: 'Vulnerabilities over time for this organization'
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


                let context = document.getElementById("organization_connectivity_timeline").getContext('2d');
                let myChart2 = new Chart(context, {
                    type: 'line',
                    data: {
                        labels: labels,

                        datasets: [{
                            label: '# Internet Adresses',
                            data: urls,
                            backgroundColor: 'rgba(0, 0, 0, 0.2)',
                            borderColor: 'rgba(0,0,0,1)',
                            borderWidth: 1
                        },
                        {
                            label: '# Services',
                            data: endpoints,
                            backgroundColor: 'rgba(0, 40, 255, 0.2)',
                            borderColor: 'rgba(0,40,255,1)',
                            borderWidth: 1
                        },
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        title: {
                            display: true,
                            text: 'Internet connectivity of this organization'
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

            }).catch((fail) => {console.log('An error occurred: ' + fail)});
        },

        colorize: function (high, medium, low) {
            if (high > 0) return "red";
            if (medium > 0) return "orange";
            return "green";
        },
        colorizebg: function (high, medium, low) {
            if (high > 0) return "rgba(251, 173, 173, 0.3)";
            if (medium > 0) return "rgba(249, 209, 139, 0.3)";
            return "rgba(191, 255, 171, 0.3)";
        },
        idize: function (url) {
            url = url.toLowerCase();
            return url.replace(/[^0-9a-z]/gi, '')
        },
        idizetag: function (url) {
            url = url.toLowerCase();
            return "#" + url.replace(/[^0-9a-z]/gi, '')
        },
        humanize: function (date) {
            // It's better to show how much time was between the last scan and now. This is easier to understand.
            return moment(date).fromNow();
        },
        translate: function(string){
            return gettext(string);
        },
        create_header: function (rating) {
            return this.translate("report_header_" + rating.type);
        },
        // todo: have documentation links for all vulnerabilities for a dozen countries, so to stress the importance
        second_opinion_links: function (rating, url) {
            if (rating.type === "security_headers_strict_transport_security")
                return  '<a href="https://securityheaders.io/?q=' + url.url + '" target="_blank" class="btn-sm ,"><i class="fas fa-clipboard-check"></i> ' + gettext('Second opinion') + ' (securityheaders.io)</a> ' +
                        '<a href="https://en.wikipedia.org/wiki/HTTP_Strict_Transport_Security" target="_blank" class="btn-sm"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (wikipedia)</a> ';
            if (rating.type === "tls_qualys")
                return  '<a href="https://www.ssllabs.com/ssltest/analyze.html?d=' + url.url + '&hideResults=on&latest" target="_blank" class="btn-sm ,"><i class="fas fa-clipboard-check"></i> ' + gettext('Second opinion') + ' (qualys)</a> ' +
                        '<a href="https://en.wikipedia.org/wiki/Transport_Layer_Security" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (wikipedia)</a> ';
            if (rating.type === "security_headers_x_xss_protection")
                return  '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xxxsp" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (owasp)</a>';
            if (rating.type === "security_headers_x_frame_options")
                return  '<a href="https://en.wikipedia.org/wiki/Clickjacking" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (wikipedia)</a>';
            if (rating.type === "security_headers_x_content_type_options")
                return  '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xcto" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (owasp)</a>';
            if (rating.type === "DNSSEC")
                return  '<a href="https://dnssec-debugger.verisignlabs.com/" target="_blank" class="btn-sm ,"><i class="fas fa-clipboard-check"></i> ' + gettext('Second opinion') + ' (verisign)</a> ' +
                        '<a href="https://en.wikipedia.org/wiki/Domain_Name_System_Security_Extensions" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (wikipedia)</a> ';
            if (rating.type === "ftp")
                return  '<a href="https://ftptest.net/" target="_blank" class="btn-sm ,"><i class="fas fa-clipboard-check"></i> ' + gettext('Second opinion') + ' (ftptest.net)</a> ' +
                        '<a href="https://en.wikipedia.org/wiki/FTPS" target="_blank" class="btn-sm ,"><i class="fas fa-book"></i> ' + gettext('Documentation') + ' (wikipedia)</a>';
        },
        explain_link: function(address, rating, url) {
            subject = gettext("Explanation of finding");
            body = gettext("Hi!,\n" +
                "\n" +
                "I would like to explain the below finding.\n" +
                "\n" +
                "Address: {{ url }}\n" +
                "Scan Type: {{ scan_type }}\n" +
                "Scan ID: {{ scan_id }}\n" +
                "Impact: High: {{ high }}, Medium {{ medium }}, Low: {{ low }}.\n" +
                "\n" +
                "I believe the finding to be incorrect. This is why:\n" +
                "[... please enter your explanation for review here ...]\n" +
                "\n" +
                "I acknowledge that this finding will be published together with my organizations name.\n" +
                "\n" +
                "tip: please refer to documentation or standards where possible. Be aware that an explanation is valid " +
                "for one year by default.\n" +
                "\n" +
                "Kind regards,\n" +
                "");

            explain = this.translate("Explain");

            // use a sort-of-templating language
            body = body.replace("{{ url }}", url.url);
            body = body.replace("{{ scan_type }}", rating.type);
            body = body.replace("{{ scan_id }}", rating.scan);
            body = body.replace("{{ high }}", rating.high);
            body = body.replace("{{ medium }}", rating.medium);
            body = body.replace("{{ low }}", rating.low);

            // make it so it can be sent in the mail:
            subject = encodeURIComponent(subject);
            body = encodeURIComponent(body);

            link = "<a href='mailto:" + address + "?subject=" + subject + "&body=" + body + "' class='btn-sm'><i class='fas fa-comments'></i> " + explain + "</a>";

            return link;
        },
        total_awarded_points: function (high, medium, low) {
            let marker = vueReport.make_marker(high, medium, low);
            return '<span class="total_awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
        },
        organization_points: function (high, medium, low) {
            let marker = vueReport.make_marker(high, medium, low);
            return '<span class="total_awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
        },
        awarded_points: function (high, medium, low) {
            let marker = vueReport.make_marker(high, medium, low);
            return '<span class="awarded_points_' + this.colorize(high, medium, low) + '">+ ' + marker + '</span>'
        },
        make_marker: function (high, medium, low) {
            if (high === 0 && medium === 0 && low === 0)
                return gettext("score perfect");
            else if (high > 0)
                return gettext("score high");
            else if (medium > 0)
                return gettext("score medium");
            else
                return gettext("score low");
        },
        // fullscreen report
        show: function () {
            this.visible = true;
        },
        hide: function () {
            this.visible = false;
        },
        // end fullscreen report
        endpoint_type: function (endpoint) {
            return endpoint.protocol + "/" + endpoint.port + " (IPv" + endpoint.ip_version + ")";
        },
        load: function (organization_id, weeks_ago) {

            if (!weeks_ago) {
                weeks_ago = 0;
            }

            if (!this.country || !this.category)
                return;

            // against symptom of autoloading when setting state, this doesn't have the right parameters.
            if (!organization_id)
                return;

            vueReport.loading = true;
            vueReport.name = null;
            let self = this;
            $.getJSON('/data/report/' + this.country + '/' + this.category + '/' + organization_id + '/' + weeks_ago, function (data) {
                self.loading = false;
                self.urls = data.calculation["organization"]["urls"];
                self.points = data.rating;
                self.high = data.calculation["organization"]["high"];
                self.medium = data.calculation["organization"]["medium"];
                self.low = data.calculation["organization"]["low"];
                self.when = data.when;
                self.name = data.name;
                self.twitter_handle = data.twitter_handle;
                self.promise = data.promise;
                self.slug = data.slug;

                // include id in anchor to allow url sharing
                let newHash = 'report-' + self.slug;
                $('a#report-anchor').attr('name', newHash);
                history.replaceState({}, '', '#' + newHash);
                self.vulnerability_timeline_for_organization(organization_id);
            });
        },
        show_in_browser: function () {
            // you can only jump once to an anchor, unless you use a dummy
            location.hash = "#loading";
            location.hash = "#report";
        },
        formatDate: function (date) {
            return new Date(date).toISOString().substring(0, 10)
        },
        closereport: function(){
            this.name = "";
        },
        printreport: function(divId){
            css1 = new String ('<link href="/static/css/vendor/bootstrap.min.css" rel="stylesheet" type="text/css">');
            css3 = new String ('<link href="/static/css/vendor/fa-svg-with-js.css" rel="stylesheet" type="text/css">');
            css4 = new String ('<link href="/static/css/overrides.css" rel="stylesheet" type="text/css">');
            window.frames["print_frame"].document.body.innerHTML=css1 + css3 + css4 + document.getElementById(divId).innerHTML;

            // there is no real guarantee that the content / css has loaded...
            // even load doesn't do that it seems.
            setTimeout(vueReport.theprint,1000);
        },
        theprint: function(){
            window.frames["print_frame"].window.focus();
            window.frames["print_frame"].window.print();
        }
    }
};


// 6 requests is expensive. Could be one with increased complexity.
const latest_mixin = {
    template: '#latest_table',
    methods: {
        load: function(){

            if (!this.country || !this.category) {
                return;
            }

            fetch(this.data_url + this.country + '/' + this.category + '/' + this.scan)
                .then(response => response.json()).then(data => {
                    this.scans = data.scans;
            }).catch((fail) => {console.log('An error occurred: ' + fail)});
        },
        rowcolor: function (scan) {
            if (scan.high === 0 && scan.medium === 0 && scan.low === 0)
                return "greenrow";
            else if (scan.high > 0)
                return "redrow";
            else if (scan.medium > 0)
                return "orangerow";
            else
                return "yellowrow";
        },
        translate: function(string){
            return gettext(string);
        }
    },
    data: {
        scans: Array,
        data_url: "/data/latest_scans/"
    }
};


const translation_mixin = {
    methods: {
        translate: function (string) {
            return gettext(string);
        }
    }
};


const top_mixin = {
    mounted: function () {
        this.load(0)
    },
    props: {
        filterKey: String,

    },
    data: {
        data: Array, // a short list of 10 items.
        fulldata: Array, // a much larger list.
        columns: ['rank', 'high', 'medium', 'low', 'organization_id', 'total_urls', 'total_endpoints'],
        sortKey: '',
        metadata: {},
        key: {}
    },
    methods: {
        showReport: function (organization_id) {
            vueReport.show_in_browser();
            vueReport.load(organization_id, vueMap.week);
            vueDomainlist.load(organization_id, vueMap.week);
        },
        humanize: function (date) {
            return new Date(date).humanTimeStamp()
        },
        load: function (weeknumber) {

            if (!this.country || !this.category)
                return;

            if (weeknumber === undefined)
                weeknumber = 0;

            let self = this;
            $.getJSON(this.$data.data_url + this.country + '/' + this.category + '/' + weeknumber, function (data) {
                self.data = data.ranking.slice(0,10);
                self.fulldata = data.ranking;
                self.metadata  = data.metadata;
            });
        },
        sortBy: function (key) {
            this.sortKey = key;
            this.sortOrders[key] = this.sortOrders[key] * -1
        },
        swapFull: function(){
            temp = Array;
            temp = this.data;
            this.data = this.fulldata;
            this.fulldata = temp;
        }
    },
    computed: {
        filteredData: function () {
          let sortKey = this.sortKey;
          let filterKey = this.filterKey && this.filterKey.toLowerCase();
          let order = this.sortOrders[sortKey] || 1;
          let data = this.data;
          if (filterKey) {
            data = data.filter(function (row) {
              return Object.keys(row).some(function (key) {
                return String(row[key]).toLowerCase().indexOf(filterKey) > -1
              })
            })
          }
          if (sortKey) {
            data = data.slice().sort(function (a, b) {
              a = a[sortKey];
              b = b[sortKey];
              return (a === b ? 0 : a > b ? 1 : -1) * order
            })
          }
          return data
        }
    },
    filters: {
        capitalize: function (str) {
            return str.charAt(0).toUpperCase() + str.slice(1)
        }
    }
};


function extracrunchycyber(){
    vueMapStateBar.countries = ["NL", "DE"];
}


function extra() {
    vueMapStateBar.countries = ["NL", "DE", "SE"];
    vueMapStateBar.categories = ["municipality", "cyber", "unknown"];
}

function germany() {
    vueMapStateBar.countries = ["NL", "DE"];
    vueMapStateBar.categories = ["bundesland", "regierungsbezirk", "landkreis_kreis_kreisfreie_stadt",
    "samtgemeinde_verwaltungsgemeinschaft"];
}


function views() {

    window.vueGraphs = new Vue({
        name: "graphs",
        mixins: [state_mixin],

        // the mixin requires data to exist, otherwise massive warnings.
        data: {
            nothing: "",
        },

        el: '#graphs',

        mounted: function() {
            this.load(0)
        },

        methods: {
            load: function () {

                if (!this.country || !this.category)
                    return;

                // data.total
                // security_headers_strict_transport_security

                fetch('/data/vulnstats/' + this.country + '/' + this.category + '/0')
                    .then(response => response.json()).then(data => {

                        this.vulnerability_graph('timeline_all_vulnerabilities', data.total, 'hml');
                        this.vulnerability_graph('timeline_tls_qualys_vulnerabilities', data.tls_qualys, 'hl');
                        this.vulnerability_graph('timeline_missing_https_encryption_vulnerabilities', data.plain_https, 'hm');
                        this.vulnerability_graph('timeline_hsts_vulnerabilities', data.security_headers_strict_transport_security, 'm');
                        this.vulnerability_graph('timeline_xfo_vulnerabilities', data.security_headers_x_frame_options, 'm');
                        this.vulnerability_graph('timeline_xcto_vulnerabilities', data.security_headers_x_content_type_options, 'l');
                        this.vulnerability_graph('timeline_xxss_vulnerabilities', data.security_headers_x_xss_protection, 'l');
                        this.vulnerability_graph('timeline_dnssec_vulnerabilities', data.DNSSEC, 'h');
                        this.vulnerability_graph('timeline_unencrypted_ftp_vulnerabilities', data.ftp, 'hm');
                }).catch((fail) => {console.log('An error occurred: ' + fail)});

            },
            vulnerability_graph: function(element, data, axis){

                if (data === undefined)
                    return;

                let labels = Array();
                let high = Array();
                let medium = Array();
                let low = Array();

                for(let i=0; i<data.length; i++){
                    labels.push(new Date(data[i].date));
                    high.push(data[i].high);
                    medium.push(data[i].medium);
                    low.push(data[i].low);
                }

                let datasets = Array();

                if (axis.indexOf('h') !== -1)
                    datasets.push({
                            label: '# High risk',
                            data: high,
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            borderColor: 'rgba(255,99,132,1)',
                            borderWidth: 1
                        });

                if (axis.indexOf('m') !== -1)
                    datasets.push({
                            label: '# Medium risk',
                            data: medium,
                            backgroundColor: 'rgba(255, 102, 0, 0.2)',
                            borderColor: 'rgba(255,102,0,1)',
                            borderWidth: 1
                        });


                if (axis.indexOf('l') !== -1)
                    datasets.push({
                            label: '# Low risk',
                            data: low,
                            backgroundColor: 'rgba(255, 255, 0, 0.2)',
                            borderColor: 'rgba(255,255,0,1)',
                            borderWidth: 1
                        });

                let ctx = document.getElementById(element).getContext('2d');
                let myChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: datasets,
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        title: {
                            display: false,
                            text: ''
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
            }
        }
    });

    window.vueStatistics = new Vue({
        name: "statistics",

        mixins: [state_mixin],
        el: '#statistics',
        mounted: function () {
            this.load(0)
        },
        data: {
            data: Array,
            services: [],
            endpoints_now: 0,

            // sorting
            columns: ['ip_version', 'protocol', 'port', 'amount'],
            sortKey: 'amount',
            sortOrders: {'ip_version': 1, 'protocol': 1, 'port': 1, 'amount': -1}
        },
        computed: {
            greenpercentage: function () {
                return this.perc(this.data.data, "green", "total_organizations");
            },

            redpercentage: function () {
                return this.perc(this.data.data, "red", "total_organizations");
            },

            orangepercentage: function () {
                if (this.data.data) {
                    let score = 100 -
                        roundTo(this.data.data.now["no_rating"] / this.data.data.now["total_organizations"] * 100, 2) -
                        roundTo(this.data.data.now["red"] / this.data.data.now["total_organizations"] * 100, 2) -
                        roundTo(this.data.data.now["green"] / this.data.data.now["total_organizations"] * 100, 2);
                    return roundTo(score, 2) + "%";
                }
                return 0
            },
            unknownpercentage: function () {
                return this.perc(this.data.data, "no_rating", "total_organizations");
            },
            greenurlpercentage: function () {
                return this.perc(this.data.data, "green_urls", "total_urls");
            },

            redurlpercentage: function () {
                return this.perc(this.data.data, "red_urls", "total_urls");
            },

            orangeurlpercentage: function () {
                if (this.data.data) {
                    let score = 100 -
                        roundTo(this.data.data.now["red_urls"] / this.data.data.now["total_urls"] * 100, 2) -
                        roundTo(this.data.data.now["green_urls"] / this.data.data.now["total_urls"] * 100, 2);
                    return roundTo(score, 2) + "%";
                }
                return 0
            },
            filteredData: function () {
                let sortKey = this.sortKey;
                let filterKey = this.filterKey && this.filterKey.toLowerCase();
                let order = this.sortOrders[sortKey] || 1;
                let data = this.services;
                if (filterKey) {
                    data = data.filter(function (row) {
                        return Object.keys(row).some(function (key) {
                            return String(row[key]).toLowerCase().indexOf(filterKey) > -1
                        })
                    })
                }
                if (sortKey) {
                    data = data.slice().sort(function (a, b) {
                        a = a[sortKey];
                        b = b[sortKey];
                        return (a === b ? 0 : a > b ? 1 : -1) * order
                    })
                }
                return data
            }
        },
        methods: {
            load: function (weeknumber) {

                if (!this.country || !this.category)
                    return;

                if (weeknumber === undefined)
                    weeknumber = 0;

                let self = this;
                $.getJSON('/data/stats/' + this.country + '/' + this.category + '/' + weeknumber, function (data) {
                    self.data = data;

                    self.endpoints_now = data.data.now['endpoints'];

                    for(let i=0; i<data.data.now['endpoint'].length; i++){
                        let z = data.data.now['endpoint'][i][1];
                        self.services.push({
                            'amount': z.amount,
                            'ip_version': z.ip_version,
                            'protocol': z.protocol,
                            'port': z.port})
                    }
                });
            },
            perc: function (data, amount, total) {
                return (!data) ? "0%" :
                    roundTo(data.now[amount] / data.now[total] * 100, 2) + "%";
            },
            translate: function(string){
                return gettext(string);
            },
            sortBy: function (key) {
                this.sortKey = key;
                this.sortOrders[key] = this.sortOrders[key] * -1;
            }
        }
    });

    window.vueDomainlist = new Vue({
        name: "domainlist",

        mixins: [state_mixin],
        el: '#domainlist',
        template: '#domainlist_template',

        data: {urls: Array},
        methods: {
            colorize: function (high, medium, low) {
                if (high > 0) return "red";
                if (medium > 0) return "orange";
                return "green";
            },
            load: debounce(function (organization_id, weeks_back) {

                if (!weeks_back)
                    weeks_back = 0;

                if (!this.country || !this.category)
                    return;

                // symptom of state mixing loads this even though it's not needed (and doesn't have the right arguments)
                if (!organization_id)
                    return;

                $.getJSON('/data/report/' + this.country + '/' + this.category + '/' + organization_id + '/' + weeks_back, function (data) {
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
            data: Array
        },
        methods: {
            colorize: function (value, rank) {
                if (value === 0)
                    return "black";

                if (rank === "high")
                    return "red";

                if (rank === "medium")
                    return "orange";

                if (rank === "low")
                    return "yellow";

                if (high > 0) return "red";
                if (medium > 0) return "orange";
                return "green";
            },
            arrow: function(value, rank){
                if (value > 0)
                    return "<a style='color: red'>▲</a>"+ value + " ";
                if (value === 0)
                    return "▶0";
                if (value < 0)
                    return "<a style='color: green'>▼</a>" + (value * -1) + " ";
            },
            get_tickertext: function() {
                // weird that this should be a function...
                return this.tickertext;
            },
            load: debounce(function () {
                // /data/ticker/NL/municipality/0/0

                if (!this.country || !this.category)
                    return;


                self = this;
                $.getJSON('/data/ticker/' + this.country + '/' + this.category + '/0/0', function (data) {
                    j = 0;

                    self.data = data;

                    for (j=0;j<data.length;j++){
                        self.tickertext += "  &nbsp; " + data[j]['organization'] + " ";

                        self.tickertext += "<a style='color: " + self.colorize(data[j]['high_now'], 'high') +"'>" + data[j]['high_now'] + "</a>";
                        self.tickertext += self.arrow(data[j]['high_changes'], 'high');
                        self.tickertext += " | ";

                        self.tickertext += "<a style='color: " + self.colorize(data[j]['medium_now'], 'medium') +"'>" + data[j]['medium_now'] + "</a>";
                        self.tickertext += self.arrow(data[j]['medium_changes'], 'medium');
                        self.tickertext += " | ";

                        self.tickertext += "<a style='color: " + self.colorize(data[j]['low_now'], 'low') +"'>" + data[j]['low_now'] + "</a>";
                        self.tickertext += self.arrow(data[j]['low_changes'], 'low');
                        self.tickertext += " ";

                        if (j % 10 === 0) {
                            self.tickertext += " - <b> failmap.org, monitor governments </b> - "
                        }
                    }
                });
            }, 42)
        }
    });

    window.vueExport = new Vue({
        name: "export",

        mixins: [translation_mixin, state_mixin],
        el: '#export',
        data: {
            categories: Array
        },
        methods: {
            create_link: function(category, linktype){
                return '/data/export/' + linktype + '/' + this.country + '/' + category + '/json/';
            },
            load: function(){
                // doesn't have a load method, but is auto called via the state_mixin.
                // values are set via another vue, which is not very nice, but it works...
            }
        }
    });


    window.vueFullscreen = new Vue({
        name: "fullscreen",

        el: '#fullscreen',
        data: {
            fullscreen: gettext("View Full Screen")
        },
        methods: {
            toggleFullScreen: function () {
                failmap.map.toggleFullscreen(failmap.map.options);
                if (vueFullscreen.fullscreen === gettext("View Full Screen")) {
                    vueFullscreen.fullscreen = gettext("Exit Full Screen")
                } else {
                    vueFullscreen.fullscreen = gettext("View Full Screen")
                }
            }
        }
    });

    window.vueTopfail = new Vue({
        name: "topfail",

        el: '#topfail',
        data: {
            data_url: "/data/topfail/",
            sortOrders: {'rank': 1, 'organization_id': 1, 'high': 1, 'medium': 1, 'low': 1}
        },
        mixins: [top_mixin, state_mixin]
    });

    window.vueTopwin = new Vue({
        name: "topwin",
        el: '#topwin',
        data: {
            data_url: "/data/topwin/",
            sortOrders: {'rank': 1, 'organization_id': 1, 'high': 1, 'medium': 1, 'low': 1}
        },
        mixins: [top_mixin, state_mixin]
    });

    // todo: https://css-tricks.com/intro-to-vue-5-animations/
    window.vueLatestTlsQualys = new Vue({
        name: "latest_tls_qualys",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_tls_qualys',
        data: {scan: "tls_qualys", element_id: "latest_tls_qualys"}
    });

    window.vueLatestPlainHttps = new Vue({
        name: "latest_plain_https",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_plain_https',
        data: {scan: "plain_https", element_id: "latest_plain_https"}
    });

    window.vueLatestFtp = new Vue({
        name: "latest_ftp",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_ftp',
        data: {scan: "ftp", element_id: "latest_ftp"}
    });

    window.vueLatestHSTS = new Vue({
        name: "latest_security_headers_strict_transport_security",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_security_headers_strict_transport_security',
        data: {scan: "Strict-Transport-Security", element_id: "latest_security_headers_strict_transport_security"}
    });

    window.vueLatestXContentTypeOptions = new Vue({
        name: "latest_security_headers_x_frame_options",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_security_headers_x_frame_options',
        data: {scan: "X-Content-Type-Options", element_id: "latest_security_headers_x_frame_options"}
    });

    window.vueLatestXFrameOptions = new Vue({
        name: "latest_security_headers_x_content_type_options",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_security_headers_x_content_type_options',
        data: {scan: "X-Frame-Options", element_id: "latest_security_headers_x_content_type_options"}
    });

    window.vueLatestXXSSProtection = new Vue({
        name: "latest_security_headers_x_xss_protection",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_security_headers_x_xss_protection',
        data: {scan: "X-XSS-Protection", element_id: "latest_security_headers_x_xss_protection"}
    });

    window.vueLatestDNSSEC = new Vue({
        name: "latest_DNSSEC",
        mixins: [latest_mixin, state_mixin],
        el: '#latest_DNSSEC',
        data: {scan: "DNSSEC", element_id: "latest_DNSSEC"}
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
    window.vueImprovements = new Vue({
        name: "issue_improvements",
        el: '#issue_improvements',
        mixins: [state_mixin],

        mounted: function () {
            this.load(0)
        },

        data: {
            data: null,
            tls_qualys: {high: 0, medium:0, low: 0},
            security_headers_strict_transport_security: {high: 0, medium:0, low: 0},
            security_headers_x_content_type_options: {high: 0, medium:0, low: 0},
            security_headers_x_xss_protection: {high: 0, medium:0, low: 0},
            security_headers_x_frame_options: {high: 0, medium:0, low: 0},
            plain_https: {high: 0, medium:0, low: 0},
            ftp: {high: 0, medium:0, low: 0},
            overall: {high: 0, medium:0, low: 0}
        },

        methods: {
            load: function (weeks_ago) {

                if (!this.country || !this.category)
                    return;

                if (!weeks_ago) {
                    weeks_ago = 0;
                }

                let self = this;
                $.getJSON('/data/improvements/' + this.country + '/' + this.category + '/' + weeks_ago + '/0', function (data) {
                    if ($.isEmptyObject(data)) {
                        self.data = null;
                        self.tls_qualys = {high: 0, medium:0, low: 0};
                        self.security_headers_strict_transport_security = {high: 0, medium:0, low: 0};
                        self.security_headers_x_content_type_options = {high: 0, medium:0, low: 0};
                        self.security_headers_x_xss_protection = {high: 0, medium:0, low: 0};
                        self.security_headers_x_frame_options = {high: 0, medium:0, low: 0};
                        self.plain_https = {high: 0, medium:0, low: 0};
                        self.ftp = {high: 0, medium:0, low: 0};
                        self.overall = {high: 0, medium:0, low: 0}
                    } else {
                        self.data = data;
                        if (data.tls_qualys !== undefined)
                            self.tls_qualys = data.tls_qualys.improvements;
                        if (data.security_headers_strict_transport_security !== undefined)
                            self.security_headers_strict_transport_security = data.security_headers_strict_transport_security.improvements;
                        if (data.security_headers_x_content_type_options !== undefined)
                            self.security_headers_x_content_type_options = data.security_headers_x_content_type_options.improvements;
                        if (data.security_headers_x_xss_protection !== undefined)
                            self.security_headers_x_xss_protection = data.security_headers_x_xss_protection.improvements;
                        if (data.security_headers_x_frame_options !== undefined)
                            self.security_headers_x_frame_options = data.security_headers_x_frame_options.improvements;
                        if (data.plain_https !== undefined)
                            self.plain_https = data.plain_https.improvements;
                        if (data.ftp !== undefined)
                            self.ftp = data.ftp.improvements;
                        if (data.overall !== undefined)
                            self.overall = data.overall.improvements;
                    }
                });
            },
            goodbad: function (value) {
                if (value === 0)
                    return "improvements_neutral";

                if (value > 0)
                    return "improvements_good";

                return "improvements_bad"
            }
        }
    });



    window.vueFullScreenReport = new Vue({
        name: "fullscreenreport",
        el: '#fullscreenreport',
        mixins: [state_mixin, report_mixin],

        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
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
            // wait until the default category and default languages have been set...

            // initial load.
            this.load(0)
        },
        mixins: [state_mixin],

        el: '#historycontrol',
        template: '#historycontrol_template',
        data: {
            // # historyslider
            loading: false,
            week: 0,
            selected_organization: -1,
            features: null,

            displayed_issue: ""
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
            set_state: function(country, category, skip_map){
                console.log("Set state");
                this.country = country;
                this.category = category;

                // skip_map is used in loading the defaults, where the map is already (probably) loaded.
                // The first time the map loads based on the default settings in the backend. This shows the map
                // faster as it saves a roundtrip. Loading the map faster is a better experience for visitors.
                if (skip_map) {
                    console.log('Skipping the map on the default load.');
                } else {
                    vueMap.show_week();
                }

                vueTopfail.set_state(this.country, this.category);
                vueTopwin.set_state(this.country, this.category);
                vueStatistics.set_state(this.country, this.category);
                vueLatestPlainHttps.set_state(this.country, this.category);
                vueLatestFtp.set_state(this.country, this.category);
                vueLatestTlsQualys.set_state(this.country, this.category);
                vueLatestXContentTypeOptions.set_state(this.country, this.category);
                vueLatestHSTS.set_state(this.country, this.category);
                vueLatestXFrameOptions.set_state(this.country, this.category);
                vueLatestXXSSProtection.set_state(this.country, this.category);
                vueLatestDNSSEC.set_state(this.country, this.category);
                vueGraphs.set_state(this.country, this.category);
                vueImprovements.set_state(this.country, this.category);
                vueExport.set_state(this.country, this.category);
                vueDomainlist.set_state(this.country, this.category);
                vueTicker.set_state(this.country, this.category);
                vueExplains.set_state(this.country, this.category);

                // this needs state as the organizaton name in itself is not unique.
                vueReport.set_state(this.country, this.category);
                vueFullScreenReport.set_state(this.country, this.category);
            },
            // slowly moving the failmap into a vue. NOPE. denied.
            load: function (week) {
                if (week === undefined)
                    week = 0;

                let self = this;
                self.loading = true;

                // the first time the map defaults are loaded, this saves a trip to the server of what the defaults are
                // it's possible that this is slower than the rest of the code, and thus a normal map is loaded.
                if (!this.country || !this.category) {
                    $.getJSON('/data/map_default/' + week * 7 + '/' +
                        self.displayed_issue + '/' , function (mapdata) {
                        self.loading = true;
                        failmap.plotdata(mapdata);

                        if (mapdata.features.length > 0) {
                            self.features = mapdata.features;
                        }
                        self.loading = false;
                    });
                } else {
                    $.getJSON('/data/map/' + this.country + '/' + this.category + '/' + week * 7 + '/' +
                        self.displayed_issue + '/', function (mapdata) {
                        self.loading = true;

                        failmap.plotdata(mapdata);

                        // make map features (organization data) available to other vues
                        // do not update this attribute if an empty list is returned as currently
                        // the map does not remove organizations for these kind of responses.
                        if (mapdata.features.length > 0) {
                            self.features = mapdata.features;
                        }
                        self.loading = false;
                    });
                }
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
                // vueTopfail.load(this.week);

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

    // merged category and country navbars to have a single point of setting the state at startup.
    window.vueMapStateBar = new Vue({
        name: "MapStateBar",
        mixins: [translation_mixin],
        el: '#map_state_bar',

        data: {
            categories: [""],
            countries: [""],
            selected_category: "",
            selected_country: "",
            default_category: "",
            default_country: ""
        },

        mounted: function() {
            this.get_defaults();
        },

        // todo: load the map without parameters should result in the default settings to save a round trip.
        methods: {
            get_defaults: function() {
                fetch('/data/defaults/').then(response => response.json()).then(data => {
                    this.selected_category = data.category;
                    this.selected_country = data.country;
                    this.default_category = data.category;
                    this.default_country = data.country;
                    // done in the map.
                    vueMap.set_state(this.selected_country, this.selected_category, true);
                    this.get_countries();
                }).catch((fail) => {console.log('An error occurred: ' + fail)});
            },
            get_countries: function() {
                fetch('/data/countries/').then(response => response.json()).then(countries => {
                    // it's fine to clear the navbar if there are no categories for this country
                    this.countries = countries;

                    // this is async, therefore you cannot call countries and then categories. You can only do while...
                    this.get_categories();
                }).catch((fail) => {console.log('An error occurred: ' + fail)});
            },
            get_categories: function() {
                fetch('/data/categories/' + this.selected_country + '/').then(response => response.json()).then(categories => {
                    // it's fine to clear the navbar if there are no categories for this country
                    this.categories = categories;
                    vueExport.categories = categories;  // todo: Move this to map? Can't. Figure out.
                });
            },
            set_country: function(country_name) {
                // when changing the country, a new set of categories will appear.
                this.selected_country = country_name;

                // the first category of the country is the default. Load the map and set that one.
                fetch('/data/categories/' + this.selected_country + '/').then(response => response.json()).then(categories => {
                    // yes, there are categories.
                    if (categories.length) {
                        this.categories = categories;
                        this.selected_category = categories[0];
                        vueMap.set_state(this.selected_country, this.selected_category);
                    } else {
                        this.categories = [""];
                        vueMap.set_state(this.selected_country, this.selected_category);
                    }
                });
            },
            set_category: function(category_name){
                this.selected_category = category_name;
                vueMap.set_state(this.selected_country, this.selected_category);
            }
        }
    });

    window.vueReport = new Vue({
        name: "report",
        el: '#report',
        mixins: [state_mixin, report_mixin],

        computed: {
            // load list of organizations from map features
            // todo: this doesn't update when region changes.
            // todo: get map data from somewhere else. This should be placed elsewhere.
            organizations: function () {
                if (vueMap.features != null) {
                    let organizations = vueMap.features.map(function (feature) {
                        return {
                            "id": feature.properties.organization_id,
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
        watch: {
            selected: function () {
                // load selected organization id
                this.load(this.selected);
            }
        }

    });

    window.vueExplains = new Vue({
        name: "comply_or_explain",
        el: '#comply_or_explain',
        mixins: [state_mixin, translation_mixin],
        data: {
            explains: Array(),
            more_explains: Array(),
            more_available: true,
        },

        methods: {
            humanize: function (date) {
                // It's better to show how much time was between the last scan and now. This is easier to understand.
                return moment(date).fromNow();
            },
            load: function() {

             if (!this.country || !this.category)
                return;


                fetch('/data/explained/' + this.country + '/' + this.category + '/').then(response => response.json()).then(explains => {
                    this.more_explains = explains.slice(3);
                    this.explains = explains.slice(0, 3);

                    if (this.more_explains.length === 0)
                        this.more_available = false;

                }).catch((fail) => {
                    console.log('An error occurred: ' + fail)
                });
            },
            showreport(organization_id){
                location.href = '#report';
                vueReport.selected = organization_id;
            },
            showmore(){
                if (this.more_explains.length > 3) {
                    this.explains.push(this.more_explains.shift());
                    this.explains.push(this.more_explains.shift());
                    this.explains.push(this.more_explains.shift());
                } else if (this.more_explains.length > 1) {
                    for (i=0; i<this.more_explains.length; i++){
                        this.explains.push(this.more_explains.shift());
                    }
                    this.more_available = false;
                }
            }
        },
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
        }

    });
    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    // vueMap.load(0);
}
