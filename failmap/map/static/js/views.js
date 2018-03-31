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
    return this.getFullYear() + " " + gettext("week") + " " + this.getWeek();
};

var category_mixin = {
    data: {
        category: "municipality"
    },
    watch: {
        category: function (newCategory, oldCategory) {
            // refresh the views :)
            this.load()
        }
    }
};

var country_mixin = {
    data: {
        country: "NL"
    },
    watch: {
        country: function (newCountry, oldCountry) {
            // refresh the views :)
            this.load()
        }
    }
};


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
    // https://vuejs.org/v2/api/#updated
    updated: function () {
      this.$nextTick(function () {
          lazyload()
      })
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
        translate: function(string){
            return gettext(string);
        },
        create_header: function (rating) {
            return this.translate("report_header_" + rating.type);
        },
        // todo: have documentation links for all vulnerabilities for a dozen countries, so to stress the importance
        second_opinion_links: function (rating, url) {
            if (rating.type === "security_headers_strict_transport_security")
                return '<a href="https://en.wikipedia.org/wiki/HTTP_Strict_Transport_Security" target="_blank">' + gettext('Documentation') + ' (wikipedia)</a> - ' +
                    '<a href="https://securityheaders.io/?q=' + url.url + '" target="_blank">' + gettext('Second opinion') + ' (securityheaders.io)</a>';
            if (rating.type === "tls_qualys")
                return '<a href="https://en.wikipedia.org/wiki/Transport_Layer_Security" target="_blank">' + gettext('Documentation') + ' (wikipedia)</a> - ' +
                    '<a href="https://www.ssllabs.com/ssltest/analyze.html?d=' + url.url + '&hideResults=on&latest" target="_blank">' + gettext('Second opinion') + ' (qualys)</a>';
            if (rating.type === "security_headers_x_xss_protection")
                return '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xxxsp" target="_blank">' + gettext('Documentation') + ' (owasp)</a>';
            if (rating.type === "security_headers_x_frame_options")
                return '<a href="https://en.wikipedia.org/wiki/Clickjacking" target="_blank">' + gettext('Documentation') + ' (wikipedia)</a>';
            if (rating.type === "security_headers_x_content_type_options")
                return '<a href="https://www.owasp.org/index.php/OWASP_Secure_Headers_Project#xcto" target="_blank">' + gettext('Documentation') + ' (owasp)</a>';
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
            vueReport.loading = true;
            vueReport.name = null;
            var self = this;
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
                    return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft ' + points + ' punten op Faalkaart! Bescherm mijn gegevens beter! 🥀&hashtags=' + name + ',faal,faalkaart"><img src="/static/images/twitterwhite.png" width="14" />' + this.translate('Tweet') + '</a>';
                } else {
                    return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft alles op orde! 🌹&hashtags=' + name + ',win,faalkaart"><img src="/static/images/twitterwhite.png" width="14" />' + this.translate('Tweet') + '</a>';
                }
            }
        },
        formatDate: function (date) {
            return new Date(date).toISOString().substring(0, 10)
        }
    }
};


// 6 requests is expensive. Could be one with increased complexity.
var latest_mixin = {
    template: '#latest_table',
    mounted: function () {
        this.load()
    },
    methods: {
        load: function(){
            var self = this;
            $.getJSON( this.data_url + this.country + '/' + this.category + '/' + this.scan, function (data) {
                self.scans = data.scans;
            });
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


var translation_mixin = {
    methods: {
        translate: function (string) {
            return gettext(string);
        }
    }
};


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
            $.getJSON(this.$data.data_url + this.country + '/' + this.category + '/' + weeknumber, function (data) {
                self.top = data;
            });
        },
        twitter_message: function (chart, rank){
            message = "https://twitter.com/intent/tweet?screen_name=" + rank.organization_twitter + "&text=";
            if (chart === 'fail') {
                message += rank.organization_twitter + ' ' + gettext("top congratulations") + ' '
                    + rank.organization_name + ' ' + gettext("top position") + ' ' + rank.rank + ' '
                    + gettext("top fail on failmap") + ' 🥀' +
                    '&hashtags=' + rank.organization_name + ',' + gettext("hastag fail") + ',' + gettext("hastag failmap");
            } else {
                message += rank.organization_twitter + ' ' + gettext("top congratulations") + ' '
                    + rank.organization_name + ' ' + gettext("top position") + ' ' + rank.rank + ' '
                    + gettext("top win on failmap") + ' 🌹' +
                    '&hashtags=' + rank.organization_name + ',' + gettext("hastag fail") + ',' + gettext("hastag failmap");
            }
            return message
        }
    }
};


function extracrunchycyber(){
    vueCountryNavbar.countries = ["NL", "DE"];
}


function extra() {
    vueCountryNavbar.countries = ["NL", "DE", "SE"];
    vueCategoryNavbar.categories = ["municipality", "cyber", "unknown"];
}


function germany() {
    vueCountryNavbar.countries = ["NL", "DE"];
    vueCategoryNavbar.categories = ["bundesland", "regierungsbezirk", "landkreis_kreis_kreisfreie_stadt",
    "samtgemeinde_verwaltungsgemeinschaft"];
    // too big to import, too detailed?
    // "stadt_gemeinde", "stadtbezirk_gemeindeteil_mit_selbstverwaltung",
    // "stadtbezirk_gemeindeteil_mit_selbstverwaltung", "stadtteil_gemeindeteil_ohne_selbstverwaltung"
}


function views() {

    // You can try with:
    // vueCategoryNavbar.categories = ["municipality", "cyber", "unknown"]
    window.vueCategoryNavbar = new Vue({
        mixins: [translation_mixin],

        el: '#categorynavbar',

        data: {
            categories: ["municipality"],
            selected: "municipality"
        },

        methods: {
            set_category: function (category_name) {
                // all validation is done server side, all parameters are optional and have fallbacks.
                vueMap.category = category_name;
                this.selected = category_name;
            }
        }
    });

    // test with:
    // vueCountryNavbar.countries = ["NL", "DE", "SE"]
    window.vueCountryNavbar = new Vue({
        mixins: [translation_mixin],

        el: '#countrynavbar',

        data: {
            countries: ["NL"],
            selected: "NL"
        },

        methods: {
            set_country: function (country) {
                // all validation is done server side, all parameters are optional and have fallbacks.
                vueMap.country = country;
                this.selected = country;

                // update the cateogories bar for this country, todo: load a default category when a country
                // is selected

                this.load_categories()
            },
            load_categories: function() {
                var self = this;
                $.getJSON('/data/categories/' + this.selected + '/', function (categories) {
                    // it's fine to clear the navbar if there are no categories for this country
                    vueCategoryNavbar.categories = categories;

                    // but then don't clear the current category, so it's easier to go back
                    if (categories.length) {
                        vueCategoryNavbar.set_category(categories[0])
                    }

                })
            }
        }
    });

    window.vueGraphs = new Vue({
        mixins: [category_mixin, country_mixin],

        // the mixin requires data to exist, otherwise massive warnings.
        data: {
            nothing: "",
            d3stats: d3stats
        },

        el: '#graphs',

        mounted: function() {
            this.load(0)
        },

        methods: {
            load: function () {
                var self = this;
                d3.json("data/vulnstats/" + this.country + '/' + this.category + "/0/index.json", function (error, data) {
                    d3stats();
                    self.d3stats.stacked_area_chart("tls_qualys", error, data.tls_qualys);
                    self.d3stats.stacked_area_chart("plain_https", error, data.plain_https);
                    self.d3stats.stacked_area_chart("security_headers_strict_transport_security", error, data.security_headers_strict_transport_security);
                    self.d3stats.stacked_area_chart("security_headers_x_frame_options", error, data.security_headers_x_frame_options);
                    self.d3stats.stacked_area_chart("security_headers_x_content_type_options", error, data.security_headers_x_content_type_options);
                    self.d3stats.stacked_area_chart("security_headers_x_xss_protection", error, data.security_headers_x_xss_protection);
                });
            }
        }
    });

    window.vueStatistics = new Vue({
        mixins: [category_mixin, country_mixin],
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
                var self = this;
                $.getJSON('/data/stats/' + this.country + '/' + this.category + '/' + weeknumber, function (data) {
                    self.data = data;
                });
            },
            perc: function (data, amount, total) {
                return (!data) ? "0%" :
                    roundTo(data.now[amount] / data.now[total] * 100, 2) + "%";
            },
            // we can't do gettext
            translate: function(string){
                return gettext(string);
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
            }, 42)
        }
    });

    window.vueFullscreen = new Vue({
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
        el: '#topfail',
        data: {data_url: "/data/topfail/"},
        mixins: [top_mixin, category_mixin, country_mixin]
    });

    window.vueTopwin = new Vue({
        el: '#topwin',
        data: {data_url: "/data/topwin/"},
        mixins: [top_mixin, category_mixin, country_mixin]
    });

    window.vueTerribleurls = new Vue({
        el: '#terrible_urls',
        data: {data_url: "/data/terrible_urls/"},
        mixins: [top_mixin, category_mixin, country_mixin]
    });


    // todo: https://css-tricks.com/intro-to-vue-5-animations/
    window.vueLatestTlsQualys = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_tls_qualys',
        data: {scan: "tls_qualys"}
    });

    window.vueLatestPlainHttps = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_plain_https',
        data: {scan: "plain_https"}
    });

    window.vueLatestHSTS = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_security_headers_strict_transport_security',
        data: {scan: "Strict-Transport-Security"}
    });

    window.vueLatestXContentTypeOptions = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_security_headers_x_frame_options',
        data: {scan: "X-Content-Type-Options"}
    });

    window.vueLatestXFrameOptions = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_security_headers_x_content_type_options',
        data: {scan: "X-Frame-Options"}
    });

    window.vueLatestXXSSProtection = new Vue({
        mixins: [latest_mixin, category_mixin, country_mixin],
        el: '#latest_security_headers_x_xss_protection',
        data: {scan: "X-XSS-Protection"}
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
        mounted: function () {
            this.load(this.category, this.week)
        },
        mixins: [category_mixin, country_mixin],

        el: '#historycontrol',
        data: {
            // # historyslider
            loading: false,
            week: 0,
            selected_organization: -1,
            features: null,
        },
        computed: {
            visibleweek: function () {
                var x = new Date();
                x.setDate(x.getDate() - this.week * 7);
                return x.humanTimeStamp();
            }
        },
        watch: {
            category: function (newCategory, oldCategory) {
                // refresh the views :)
                vueMap.show_week();

                // unfortunately(?) we can't set the mixin to trigger updates everywhere.
                // ... subclass everything?
                vueTopfail.category = newCategory;
                vueTopwin.category = newCategory;
                vueTerribleurls.category = newCategory;
                vueStatistics.category = newCategory;
                vueLatestPlainHttps.category = newCategory;
                vueLatestTlsQualys.category = newCategory;
                vueLatestXContentTypeOptions.category = newCategory;
                vueLatestHSTS.category = newCategory;
                vueLatestXFrameOptions.category = newCategory;
                vueLatestXXSSProtection.category = newCategory;
                vueGraphs.category = newCategory;
                vueImprovements.category = newCategory;
            },
            country: function (newCountry, oldCountry) {
                // retoggle map focus in an ugly way,
                // it was never meant to work with multiple countries, so cutting corners here...
                failmap.geojson.clearLayers();
                failmap.geojson = null;

                vueTopfail.country = newCountry;
                vueTopwin.country = newCountry;
                vueTerribleurls.country = newCountry;
                vueStatistics.country = newCountry;
                vueLatestPlainHttps.country = newCountry;
                vueLatestTlsQualys.country = newCountry;
                vueLatestXContentTypeOptions.country = newCountry;
                vueLatestHSTS.country = newCountry;
                vueLatestXFrameOptions.country = newCountry;
                vueLatestXXSSProtection.country = newCountry;
                vueGraphs.country = newCountry;
                vueImprovements.country = newCountry;
            }
        },
        methods: {
            // slowly moving the failmap into a vue.
            load: function (week) {
                var self = this;
                self.loading = true;
                $.getJSON('/data/map/' + this.country + '/' + this.category + '/' + week, function (mapdata) {
                    self.loading = true;
                    // if there is one already, overwrite the attributes...
                    if (failmap.geojson) {
                        // here we add all features that are not part of the current map at all
                        // and delete the ones that are not in the current set
                        failmap.clean_map(mapdata);

                        // here we can update existing layers (and add ones with the same name)
                        failmap.geojson.eachLayer(function (layer) {failmap.recolormap(mapdata, layer)});
                    } else {
                        // first time load.
                        failmap.geojson = L.geoJson(mapdata, {
                            style: failmap.style,
                            pointToLayer: failmap.pointToLayer,
                            onEachFeature: failmap.onEachFeature
                        }).addTo(failmap.map); // only if singleton, its somewhat dirty.
                        // fit the map automatically, regardless of the initial positions

                        if (mapdata.features.length > 0) {
                            failmap.map.fitBounds(failmap.geojson.getBounds());
                        }
                    }

                    // make map features (organization data) available to other vues
                    // do not update this attribute if an empty list is returned as currently
                    // the map does not remove organizations for these kind of responses.
                    if (mapdata.features.length > 0) {
                        self.features = mapdata.features;
                    }
                    self.loading = false;
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
                // vueTopfail.load(this.week);
                // vueTopwin.load(this.week);
                // vueTerribleurls.load(this.week);


                if (this.selected_organization > -1) {
                    console.log(selected_organization);
                    // todo: requests the "report" page 3x.
                    // due to asyncronous it's hard to just "copy" results.
                    // vueReport.load(vueMap.selected_organization, this.week);
                    // vueFullScreenReport.load(vueMap.selected_organization, this.week);
                    vueDomainlist.load(this.selected_organization, this.week);
                }
            }
        }
    });


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
                            "name": feature.properties.organization_name
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
        el: '#issue_improvements',
        mixins: [category_mixin, country_mixin],

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
            overall: {high: 0, medium:0, low: 0}
        },

        methods: {
            load: function (weeks_ago) {

                if (!weeks_ago) {
                    weeks_ago = 0;
                }

                var self = this;
                $.getJSON('/data/improvements/' + this.country + '/' + this.category + '/' + weeks_ago + '/0', function (data) {
                    if ($.isEmptyObject(data)) {
                        self.data = null,
                        self.tls_qualys = {high: 0, medium:0, low: 0},
                        self.security_headers_strict_transport_security = {high: 0, medium:0, low: 0},
                        self.security_headers_x_content_type_options = {high: 0, medium:0, low: 0},
                        self.security_headers_x_xss_protection = {high: 0, medium:0, low: 0},
                        self.security_headers_x_frame_options = {high: 0, medium:0, low: 0},
                        self.plain_https = {high: 0, medium:0, low: 0},
                        self.overall = {high: 0, medium:0, low: 0}
                    } else {
                        self.data = data;
                        self.tls_qualys = data.tls_qualys.improvements;
                        self.security_headers_strict_transport_security = data.security_headers_strict_transport_security.improvements;
                        self.security_headers_x_content_type_options = data.security_headers_x_content_type_options.improvements;
                        self.security_headers_x_xss_protection = data.security_headers_x_xss_protection.improvements;
                        self.security_headers_x_frame_options = data.security_headers_x_frame_options.improvements;
                        self.plain_https = data.plain_https.improvements;
                        self.overall = data.overall.improvements;
                    }
                });
            },
            goodbad: function (value) {
                if (value > -1)
                    return "improvements_good";
                return "improvements_bad"
            }
        }
    });

    window.vueFullScreenReport = new Vue({
        el: '#fullscreenreport',
        mixins: [report_mixin],

        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        }
    });
    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    // vueMap.load(0);
}