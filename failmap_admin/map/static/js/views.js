// We've taken some time to determine what would be a non-"all-in" approach to build this software.
// Vue indeed is incrementally adoptable and easy to write and learn.
// Angular was off the table due to bad experiences, React seems to intense, especially given javascripts syntax
// oh, and the react anti-patent clause is a big no.
// // https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc

function debounce(func, wait, immediate) {
    var timeout;
    return function () {
        var context = this, args = arguments;
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

    var multiplicator = Math.pow(10, digits);
    n = parseFloat((n * multiplicator).toFixed(11));
    var test = (Math.round(n) / multiplicator);
    return +(test.toFixed(digits));
}


// support for week numbers in javascript
// https://stackoverflow.com/questions/7765767/show-week-number-with-javascript
Date.prototype.getWeek = function () {
    var onejan = new Date(this.getFullYear(), 0, 1);
    return Math.ceil((((this - onejan) / 86400000) + onejan.getDay() + 1) / 7);
};

// support for an intuitive timestamp
// translation?
Date.prototype.humanTimeStamp = function () {
    return this.getFullYear() + " Week " + this.getWeek();
};



function views() {

// there are some issues with having the map in a Vue. Somehow the map doesn't
// render. So we're currently not using that feature over there.
// It's also hard, since then we have to have themap, historycontrol, fullscreenreport, domainlist
// it's just too much in single vue.
// also: the fullscreen report only loads from something ON the map.
// and all of this for a loading indicator per vue :))
// knowing fullscreen here would be nice...
    window.vueMap = new Vue({
        el: '#historycontrol',
        data: {
            // # historyslider
            weeksback: 0,
            loading: false,
            week: 0,
            selected_organization: -1,
            features: null,
        },
        computed: {
            visibleweek: function () {
                x = new Date();
                x.setDate(x.getDate() - this.weeksback * 7);
                return x.humanTimeStamp();
            }
        },
        methods: {
            load: function (week) {
                failmap.loadmap(week);
            },
            // perhaps make it clear in the gui that it auto-updates? Who wants a stale map for an hour?
            // a stop/play doesn't work, as there is no immediate reaction, countdown perhaps? bar emptying?
            update_hourly: function () {
                setTimeout(vueMap.hourly_update(), 60 * 60 * 1000);
            },
            hourly_update: function () {
                vueMap.load(0);
                vueTopfail.load(0);
                vueTopwin.load(0);
                vueStatistics.load(0);
                vueMap.week = 0;
                setTimeout(vueMap.hourly_update(), 60 * 60 * 1000);
            },
            next_week: function () {
                if (this.week > 0) {
                    this.week = parseInt(this.week) - 1; // 1, 11, 111... glitch.
                    this.show_week();
                }
            },
            previous_week: function () {
                // caused 1, 11, 111 :) lol
                if (this.week < 52) {
                    this.week += 1;
                    this.show_week();
                }
            },
            show_week: debounce(function (e) {
                if (e)
                    this.week = e.target.value;

                // doesn't really work, as everything async.
                vueMap.load(this.week);
                vueTopfail.load(this.week);
                vueTopwin.load(this.week);
                vueTerribleurls.load(this.week);

                if (vueMap.selected_organization > -1) {
                    // todo: requests the "report" page 3x.
                    // due to asyncronous it's hard to just "copy" results.
                    vueReport.load(vueMap.selected_organization, this.week);
                    vueFullScreenReport.load(vueMap.selected_organization, this.week);
                    vueDomainlist.load(vueMap.selected_organization, this.week);
                }

                vueStatistics.load(this.week);
                vueMap.weeksback = this.week;
            }, 100)
        }
    });

    var report_mixin = {
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
        methods: {
            colorize: function (high, medium, low) {
                if (high > 0) return "red";
                if (medium > 0) return "orange";
                return "green";
            },
            colorizebg: function (high, medium, low) {
                if (high > 0) return "#fbeaea";
                if (medium > 0) return "#ffefd3";
                return "#dff9d7";
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
                return new Date(date).humanTimeStamp()
            },
            create_header: function (rating) {
                if (rating.type === "security_headers_strict_transport_security")
                    return "Strict-Transport-Security Header (HSTS)";
                if (rating.type === "tls_qualys")
                    return "Transport Layer Security (TLS)";
                if (rating.type === "plain_https")
                    return "Missing transport security (TLS)";
                if (rating.type === "security_headers_x_xss_protection")
                    return "X-XSS-Protection Header";
                if (rating.type === "security_headers_x_frame_options")
                    return "X-Frame-Options Header (clickjacking)";
                if (rating.type === "security_headers_x_content_type_options")
                    return "X-Content-Type-Options";
            },
            second_opinion_links: function (rating, url) {
                if (rating.type === "security_headers_strict_transport_security")
                    return '<a href="https://en.wikipedia.org/wiki/HTTP_Strict_Transport_Security" target="_blank">Documentation (wikipedia)</a> - ' +
                        '<a href="https://securityheaders.io/?q=' + url.url + '" target="_blank">Second Opinion (securityheaders.io)</a>';
                if (rating.type === "tls_qualys")
                    return '<a href="https://en.wikipedia.org/wiki/Transport_Layer_Security" target="_blank">Documentation (wikipedia)</a> - ' +
                        '<a href="https://www.ssllabs.com/ssltest/analyze.html?d=' + url.url + '&hideResults=on&latest" target="_blank">Second Opinion (Qualys)</a>';
                if (rating.type === "security_headers_x_xss_protection")
                    return '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xxxsp" target="_blank">Documentation (owasp)</a>';
                if (rating.type === "security_headers_x_frame_options")
                    return '<a href="https://en.wikipedia.org/wiki/Clickjacking" target="_blank">Documentation (wikipedia)</a>';
                if (rating.type === "security_headers_x_content_type_options")
                    return '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xcto" target="_blank">Documentation (owasp)</a>';
            },
            total_awarded_points: function (high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="total_awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
            },
            organization_points: function (high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="total_awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
            },
            awarded_points: function (high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="awarded_points_' + this.colorize(high, medium, low) + '">+ ' + marker + '</span>'
            },
            make_marker: function (high, medium, low) {
                if (high === 0 && medium === 0 && low === 0)
                    return "perfect";
                else if (high > 0)
                    return "hoog";
                else if (medium > 0)
                    return "midden";
                else
                    return "laag";
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
                vueReport.loading = true;
                vueReport.name = null;
                self = this;
                $.getJSON('/data/report/' + organization_id + '/' + weeks_ago, function (data) {
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

                    // include id in anchor to allow url sharing
                    let newHash = 'report-' + organization_id;
                    $('a#report-anchor').attr('name', newHash)
                    history.replaceState({}, '', '#' + newHash);
                });
            },
            show_in_browser: function () {
                // you can only jump once to an anchor, unless you use a dummy
                location.hash = "#loading";
                location.hash = "#report";
            },
            create_twitter_link: function (name, twitter_handle, points) {
                if (twitter_handle) {
                    if (points) {
                        return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft ' + points + ' punten op Faalkaart! Bescherm mijn gegevens beter! 🥀&hashtags=' + name + ',faal,faalkaart"><img src="/static/images/twitterwhite.png" width="14" /> Tweet!</a>';
                    } else {
                        return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft alles op orde! 🌹&hashtags=' + name + ',win,faalkaart"><img src="/static/images/twitterwhite.png" width="14" /> Tweet!</a>';
                    }
                }
            },
            formatDate: function (date) {
                return new Date(date).toISOString().substring(0, 10)
            }
        }
    };

    window.vueReport = new Vue({
        el: '#report',
        mixins: [report_mixin],

        computed: {
            // load list of organizations from map features
            organizations: function () {
                if (vueMap.features != null) {
                    let organizations = vueMap.features.map(function (feature) {
                        return {
                            "id": feature.properties.organization_id,
                            "name": feature.properties.organization_name,
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
        },

    });

    window.vueFullScreenReport = new Vue({
        el: '#fullscreenreport',
        mixins: [report_mixin],

        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        },
    });

    window.vueStatistics = new Vue({
        el: '#statistics',
        mounted: function () {
            this.load(0)
        },
        data: {
            data: Array
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
                    var score = 100 -
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
                    var score = 100 -
                        roundTo(this.data.data.now["red_urls"] / this.data.data.now["total_urls"] * 100, 2) -
                        roundTo(this.data.data.now["green_urls"] / this.data.data.now["total_urls"] * 100, 2);
                    return roundTo(score, 2) + "%";
                }
                return 0
            }
        },
        methods: {
            load: function (weeknumber) {
                $.getJSON('/data/stats/' + weeknumber, function (data) {
                    vueStatistics.data = data;
                });
            },
            perc: function (data, amount, total) {
                return (!data) ? "0%" :
                    roundTo(data.now[amount] / data.now[total] * 100, 2) + "%";
            }
        }
    });

    window.vueDomainlist = new Vue({
        el: '#domainlist',
        data: {urls: Array},
        methods: {
            colorize: function (high, medium, low) {
                if (high > 0) return "red";
                if (medium > 0) return "orange";
                return "green";
            },
            load: debounce(function (organization, weeks_back) {
                if (!weeks_back)
                    weeks_back = 0;

                $.getJSON('/data/report/' + organization + '/' + weeks_back, function (data) {
                    vueDomainlist.urls = data.calculation["organization"]["urls"];
                });
            }, 100)
        }
    });

    window.vueFullscreen = new Vue({
        el: '#fullscreen',
        data: {
            fullscreen: "View Full Screen"
        },
        methods: {
            toggleFullScreen: function () {
                failmap.map.toggleFullscreen(failmap.map.options)
                if (vueFullscreen.fullscreen == "View Full Screen") {
                    vueFullscreen.fullscreen = "Exit Full Screen"
                } else {
                    vueFullscreen.fullscreen = "View Full Screen"
                }
            }
        }
    });

    var top_mixin = {
        mounted: function () {
            this.load(0)
        },
        data: {top: Array},
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
                var self = this;
                $.getJSON(this.$data.data_url + weeknumber, function (data) {
                    self.top = data;
                });
            }
        }
    };

    window.vueTopfail = new Vue({
        el: '#topfail',
        data: {data_url: "/data/topfail/"},
        mixins: [top_mixin]
    });

    window.vueTopfail = new Vue({
        el: '#topwin',
        data: {data_url: "/data/topwin/"},
        mixins: [top_mixin]
    });

    window.vueTopfail = new Vue({
        el: '#terrible_urls',
        data: {data_url: "/data/terrible_urls/"},
        mixins: [top_mixin]
    });

// 6 requests is expensive. Could be one with increased complexity.
    var latest_mixin = {
        template: '#latest_table',
        mounted: function () {
            var self = this;
            $.getJSON(this.$data.data_url, function (data) {
                self.scans = data.scans;
            });
        },
        methods: {
            rowcolor: function (scan) {
                if (scan.high === 0 && scan.medium === 0 && scan.low === 0)
                    return "greenrow";
                else if (scan.high > 0)
                    return "redrow";
                else if (scan.medium > 0)
                    return "orangerow";
                else
                    return "yellowrow";
            }
        },
        data: {
            scans: Array,
        }
    };

    // todo: https://css-tricks.com/intro-to-vue-5-animations/
    window.vueLatestTlsQualys = new Vue({
        mixins: [latest_mixin],
        el: '#latest_tls_qualys',
        data: {data_url: "/data/latest_scans/tls_qualys/"}
    });

    window.vueLatestPlainHttps = new Vue({
        mixins: [latest_mixin],
        el: '#latest_plain_https',
        data: {data_url: "/data/latest_scans/plain_https/"}
    });

    window.vueLatestTlsQualys = new Vue({
        mixins: [latest_mixin],
        el: '#latest_security_headers_strict_transport_security',
        data: {data_url: "/data/latest_scans/Strict-Transport-Security/"}
    });

    window.vueLatestPlainHttps = new Vue({
        mixins: [latest_mixin],
        el: '#latest_security_headers_x_frame_options',
        data: {data_url: "/data/latest_scans/X-Content-Type-Options/"}
    });

    window.vueLatestTlsQualys = new Vue({
        mixins: [latest_mixin],
        el: '#latest_security_headers_x_content_type_options',
        data: {data_url: "/data/latest_scans/X-Frame-Options/"}
    });

    window.vueLatestPlainHttps = new Vue({
        mixins: [latest_mixin],
        el: '#latest_security_headers_x_xss_protection',
        data: {data_url: "/data/latest_scans/X-XSS-Protection/"}
    });

    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    vueMap.load(0);
}