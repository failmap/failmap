// Currently we're migrating to Vue.
// https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc
// also: reacts patent clause and mandatory jsx syntax ... NO


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


var failmap = {
    map: null,
    geojson: "",
    internetadresses: L.control(),
    fullscreenreport: L.control(),
    fullscreenhint: L.control(),
    searchbar: L.control(),
    dataslider: L.control(),
    info: L.control(),
    legend: L.control({position: 'bottomright'}),

    initializemap: function () {
        this.map = L.map('map').setView([52.15, 5.8], 8);
        this.map.scrollWheelZoom.disable();

        L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token={accessToken}', {
            maxZoom: 18,
            attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
            '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
            'Imagery © <a href="http://mapbox.com">Mapbox</a>, ' +
            'Ratings &copy; <a href="http://faalkaart.nl/">Fail Map</a> <a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-NC-BY-SA</a>',
            id: 'mapbox.light',
            accessToken: 'pk.eyJ1IjoibXJmYWlsIiwiYSI6ImNqMHRlNXloczAwMWQyd3FxY3JkMnUxb3EifQ.9nJBaedxrry91O1d90wfuw',
        }).addTo(this.map);

        // we have our own fullscreen control
        // L.control.fullscreen().addTo(this.map);

        // console.log(this.map.isFullscreen());

        this.map.on('fullscreenchange', function () {
            if (failmap.map.isFullscreen()) {
                console.log('entered fullscreen');
            } else {
                vueFullScreenReport.hide();
                vueFullscreen.fullscreen = "View Full Screen"  // ugly fix :)
            }
        });

        this.add_fullscreen_hint();
        this.add_dataslider();
        this.add_searchbar();
        this.add_info();
        this.add_internetadresses();
        this.addlegend();
        this.add_fullscreenreport();
    },

    add_fullscreenreport: function () {
        this.fullscreenreport.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'fullscreenmap');
            L.DomEvent.disableClickPropagation(this._div);
            this._div.innerHTML = '<div class="page-header" id="fullscreenreport" v-if="visible">\n' +
                '                <div v-if="name" class="fullscreenlayout">\n' +
                '                    <h1>{{ name }}</h1>\n' +
                '                    <p class="closebutton" onclick="vueFullScreenReport.hide()">X</p>\n' +
                '                    <div>\n' +
                '                        Gegevens van: {{ humanize(when) }}<br />\n' +
                '                        Score: {{ points }}, congratulations!<br />\n' +
                '                        <br />\n' +
                '                        <div v-for="url in urls" class="perurl" v-bind:style="\'background: linear-gradient(\' + colorizebg(url.points) + \', rgba(255, 255, 255,.5));\'">\n' +
                '                            <div class="screenshotlist">\n' +
                '                                <div v-for="endpoint in url.endpoints" class="servicelink">\n' +
            '                                        <!-- There is no support for different ip\'s/ipv6 in endpoint, only for protocols. -->\n' +
            '                                        <a v-bind:href="endpoint.protocol + \'://\' + url.url + \':\' + endpoint.port" target="_blank"\n' +
            '                                        v-bind:title="\'Visit \' + endpoint.protocol + \'://\' + url.url + \':\' + endpoint.port">\n' +
            '                                            <div class="imagediv" v-bind:style="\'background-image: url(\\\'/static/images/screenshots/\'+ endpoint.protocol + idize(url.url) + endpoint.port + \'_latest.png\\\');\'"></div>\n' +
            '                                            <span v-html="\'Bezoek adres van type: \' +  create_type(endpoint) "> </span>\n' +
            '                                        </a>\n' +
                '                                </div>\n' +
                '                            </div>\n' +
                '                            <div class="reportlist">\n' +
                '                                <span v-html="total_awarded_points(url.points)"> </span>\n' +
                '                                <span class="faildomain" v-bind:class="colorize(url.points)" v-bind:data-tooltip-content="idizetag(url.url)" >\n' +
                '                                            {{ url.url }}</span><br />\n' +
                '                                <div v-for="endpoint in url.endpoints"><br />\n' +
                '                                        &nbsp; Adres: {{ endpoint.ip }}:{{ endpoint.port }}\n' +
                '                                        <div v-for="rating in endpoint.ratings">\n' +
                '                                            <h3>&nbsp; {{ create_header(rating) }}</h3>\n' +
                '                                                &nbsp; &nbsp; <span v-html="awarded_points(rating.points)"></span> {{ rating.explanation }}<br />\n' +
                '                                                &nbsp; &nbsp; Sinds: {{ humanize(rating.since) }}, Last Check: {{ humanize(rating.last_scan) }} <br />\n' +
                '                                                &nbsp; &nbsp; <span v-html="second_opinion_links(rating, url)"> </span>\n' +
                '                                                <br />\n' +
                '                                    </div>\n' +
                '                                </div>\n' +
                '                            </div>\n' +
                '                        </div>\n' +
                '                    </div>\n' +
                '                </div>\n' +
                '            </div>';
            return this._div;
        };

        this.fullscreenreport.addTo(this.map);
    },

    add_searchbar: function () {
        this.searchbar.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            this._div.innerHTML = "<input id='searchbar' type='text' onkeyup='failmap.search(this.value)' />";
            L.DomEvent.disableClickPropagation(this._div);
            return this._div;
        };

        this.searchbar.addTo(this.map);
    },

    add_info: function () {
        this.info.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            L.DomEvent.disableClickPropagation(this._div);
            // this.update();
            return this._div;
        };

        this.info.update = function (props) {
            var sometext = "";
            if (props) {
                sometext += "<h4>" + props.OrganizationName + "</h4>";
                if (props.Overall > 1)
                    sometext += '<b>Score: </b><span style="color: ' + failmap.getColor(props.Overall) + '">' + props.Overall + ' points</span>';
                else
                    sometext += '<b>Score: </b><span style="color: ' + failmap.getColor(props.Overall) + '">- points</span>';
                vueDomainlist.load(props.OrganizationID, vueMap.week);
                this._div.innerHTML = sometext;
            }
        };

        this.info.addTo(this.map);
    },

    add_fullscreen_hint: function () {
        this.fullscreenhint.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            html = "<div id=\"fullscreen\">" +
            "   <span class='btn btn-success btn-lg btn-block' v-on:click='toggleFullScreen()'>{{fullscreen}}</span>" +
            "</div>";

            this._div.innerHTML = html;
            return this._div;
        };
        this.fullscreenhint.addTo(this.map);
    },

    add_dataslider: function () {
        this.dataslider.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            L.DomEvent.disableClickPropagation(this._div);
            dataslider_control = " <div id=\"historycontrol\">" +
            "    <h4>{{ visibleweek }}<span v-if='loading'> (loading...)</span></h4>" +
            "    <input id='history' type='range' v-on:change='show_week' :value='week' min='0' max='52' step='1' :disabled='loading'/>" +
            "    <input id='previous_week' type='button' v-on:click='previous_week()' :disabled='loading' value='&lt;&lt;&lt;'/>" +
            "    <input id='next_week' type='button' v-on:click='next_week()' :disabled='loading' value='&gt;&gt;&gt;'/>" +
            "</div>";

            this._div.innerHTML = dataslider_control;
            return this._div;
        };
        this.dataslider.addTo(this.map);
    },

    add_internetadresses: function () {
        this.internetadresses.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            L.DomEvent.disableClickPropagation(this._div);
            this._div.innerHTML = "<div id=\"domainlist\" v-if=\"urls\">\n" +
                "                    <div v-for=\"url in urls\">\n" +
                "                        <span v-bind:class=\"colorize(url.points)\">\n" +
                "                            {{ url.url }}\n" +
                "                        </span>\n" +
                "                    </div>\n" +
                "                    <br />\n" +
                "                </div>";
            return this._div;
        };

        this.internetadresses.addTo(this.map);
    },

    addlegend: function () {
        this.legend.onAdd = function (map) {

            var div = L.DomUtil.create('div', 'info legend'), labels = [];

            labels.push('<i style="background:' + failmap.getColor(199) + '"></i> Good');
            labels.push('<i style="background:' + failmap.getColor(999) + '"></i> Average');
            labels.push('<i style="background:' + failmap.getColor(1000) + '"></i> Bad');
            labels.push('<i style="background:' + failmap.getColor(-1) + '"></i> Unknown');

            div.innerHTML = labels.join('<br>');
            return div;
        };

        this.legend.addTo(this.map);
    },

    PointIcon: L.Icon.extend({
        options: {
            shadowUrl: '',
            iconSize: [16, 16],
            shadowSize: [0, 0],
            iconAnchor: [8, 8],
            shadowAnchor: [0, 0],
            popupAnchor: [-3, -76]
        }
    }),

    greenIcon: new L.Icon({iconUrl: 'static/images/green-dot.png'}),
    redIcon: new L.Icon({iconUrl: 'static/images/red-dot.png'}),
    orangeIcon: new L.Icon({iconUrl: 'static/images/orange-dot.png'}),
    grayIcon: new L.Icon({iconUrl: 'static/images/gray-dot.png'}),

    // get color depending on population density value
    getColor: function (d) {
        return d > 999 ? '#bd383c' :
            d > 199 ? '#fc9645' :
                d >= 0 ? '#62fe69' :
                    '#c1bcbb';
    },

    getColorCode: function (d) {
        return d === "red" ? '#bd383c' :
            d === "orange" ? '#fc9645' :
                d === "green" ? '#62fe69' :
                    '#c1bcbb';
    },

    style: function (feature) {
        return {
            weight: 1,
            opacity: 1,
            color: 'white',
            dashArray: '0',
            fillOpacity: 0.7,
            fillColor: failmap.getColorCode(feature.properties.color)
        };
    },

    searchResultStyle: function (feature) {
        return {
            weight: 1,
            opacity: 1,
            color: 'white',
            dashArray: '0',
            fillOpacity: 0.7,
            fillColor: 'lightblue'
        };
    },

    pointToLayer: function (geoJsonPoint, latlng) {
        if (geoJsonPoint.properties.color === "red")
            return L.marker(latlng, {icon: failmap.redIcon});
        if (geoJsonPoint.properties.color === "orange")
            return L.marker(latlng, {icon: failmap.orangeIcon});
        if (geoJsonPoint.properties.color === "green")
            return L.marker(latlng, {icon: failmap.greenIcon});
        return L.marker(latlng, {icon: failmap.grayIcon});
    },

    highlightFeature: function (e) {
        var layer = e.target;

        // doesn't work for points, only for polygons and lines
        if (typeof layer.setStyle === "function") {
            layer.setStyle({
                weight: 1,
                color: '#ccc',
                dashArray: '0',
                fillOpacity: 0.7
            });
            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                layer.bringToFront();
            }
        }
        failmap.info.update(layer.feature.properties);
    },

    onEachFeature: function (feature, layer) {
        layer.on({
            mouseover: failmap.highlightFeature,
            mouseout: failmap.resetHighlight,
            click: failmap.showreport
        });
    },

    resetHighlight: function (e) {
        // todo: add search for points
        // todo: make this type of thing cleaner.
        if (failmap.isSearchedFor(e.target.feature)){
            if (e.target.feature.geometry.type === "MultiPolygon")
                e.target.setStyle(failmap.searchResultStyle(e.target.feature))
        } else {
            failmap.geojson.resetStyle(e.target);
        }
        failmap.info.update();
    },

    zoomToFeature: function (e) {
        this.map.fitBounds(e.target.getBounds());
    },

    gotoLink: function (e) {
        var layer = e.target;
        location.hash = "#" + layer.feature.properties['OrganizationName'];
    },

    isSearchedFor: function(feature){
        x = $('#searchbar').val();
        x = x.toLowerCase();
        if (!x || x === "")
            return false;
        return (feature.properties.OrganizationName.toLowerCase().indexOf(x) !== -1)
    },

    search: function(query) {
        query = query.toLowerCase();
        if ((query === "") || (!query)){
            // reset
            failmap.geojson.eachLayer(function(layer) {
                if (layer.feature.geometry.type === "MultiPolygon")
                    layer.setStyle(failmap.style(layer.feature))

                }
            )
        } else {
            // text match
            failmap.geojson.eachLayer(function (layer) {
                    if (layer.feature.properties.OrganizationName.toLowerCase().indexOf(query) !== -1) {
                        if (layer.feature.geometry.type === "MultiPolygon")
                            layer.setStyle(failmap.searchResultStyle(layer.feature))
                    } else {
                        if (layer.feature.geometry.type === "MultiPolygon")
                            layer.setStyle(failmap.style(layer.feature))
                    }
                }
            )
        }

    },

    /* Transition, which is much smoother. */
    loadmap: function (weeknumber) {
        vueMap.loading = true;
        $.getJSON('/data/map/' + weeknumber, function (json) {
            // if there is one already, overwrite the attributes...
            if (failmap.geojson) {
                failmap.geojson.eachLayer(function(layer){
                    // overwrite some properties
                    // a for loop is not ideal.
                    for (i = 0; i < json.features.length; i++) {
                        if (layer.feature.properties.OrganizationName === json.features[i].properties.OrganizationName){
                            // console.log(layer);
                            layer.feature.properties.Overall = json.features[i].properties.Overall;
                            layer.feature.properties.color = json.features[i].properties.color;
                            // make the transition
                            if (layer.feature.geometry.type === "MultiPolygon")
                                layer.setStyle(failmap.style(layer.feature));
                            if (layer.feature.geometry.type === "Point") {
                                if (layer.feature.properties.color === "red")
                                    layer.setIcon(failmap.redIcon);
                                if (layer.feature.properties.color === "orange")
                                    layer.setIcon(failmap.orangeIcon);
                                if (layer.feature.properties.color === "green")
                                    layer.setIcon(failmap.greenIcon);
                                if (layer.feature.properties.color === "gray")
                                    layer.setIcon(failmap.grayIcon);
                            }
                        }
                    }
                });
                vueMap.loading = false;
            } else {
                failmap.geojson = L.geoJson(json, {
                    style: failmap.style,
                    pointToLayer: failmap.pointToLayer,
                    onEachFeature: failmap.onEachFeature
                }).addTo(failmap.map); // only if singleton, its somewhat dirty.
                vueMap.loading = false;
            }
        });
    },

    // legacy function that force-overwrites the layer, helpful during development if you're
    // experimenting and need a clean set of layers.
    loadmap_overwrite: function (weeknumber) {
        vueMap.loading = true;
        $.getJSON('/data/map/' + weeknumber, function (json) {
            if (failmap.geojson) { // if there already was data present
                failmap.geojson.clearLayers(); // prevent overlapping polygons
                failmap.map.removeLayer(failmap.geojson);
            }

            failmap.geojson = L.geoJson(json, {
                style: failmap.style,
                pointToLayer: failmap.pointToLayer,
                onEachFeature: failmap.onEachFeature
            }).addTo(failmap.map); // only if singleton, its somewhat dirty.
            vueMap.loading = false;
        });
    },

    showreport: function(e) {
        if (failmap.map.isFullscreen()){
            // var layer = e.target;
            vueFullScreenReport.load(e.target.feature.properties['OrganizationID'], vueMap.week);
            vueFullScreenReport.show();

            // Load the report for when you leave fullscreen
            // perhaps this should be in the leave fullscreen event handler
            vueReport.load(e.target.feature.properties['OrganizationID'], vueMap.week);
        } else {
            vueReport.show_in_browser();
            vueReport.load(e.target.feature.properties['OrganizationID'], vueMap.week);
        }
    }
};

$(document).ready(function () {
    failmap.initializemap();
    lazyload();

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
        },
        computed: {
            visibleweek: function () {
                x = new Date();
                x.setDate(x.getDate() - this.weeksback * 7);
                return x.humanTimeStamp();
            }
        },
        methods: {
            load: function(week){
                failmap.loadmap(week);
            },
            // perhaps make it clear in the gui that it auto-updates? Who wants a stale map for an hour?
            // a stop/play doesn't work, as there is no immediate reaction, countdown perhaps? bar emptying?
            update_hourly: function(){
                setTimeout(vueMap.hourly_update(), 60 * 60 * 1000);
            },
            hourly_update: function() {
                vueMap.load(0);
                vueTopfail.load(0);
                vueTopwin.load(0);
                vueStatistics.load(0);
                vueMap.week = 0;
                setTimeout(vueMap.hourly_update(), 60 * 60 * 1000);
            },
            next_week: function(){
                if (this.week > 0) {
                    this.week = parseInt(this.week) - 1; // 1, 11, 111... glitch.
                    this.show_week();
                }
            },
            previous_week: function (){
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

    window.vueReport = new Vue({
        el: '#report',
        data: {
            calculation: '',
            rating: 0,
            when: 0,
            name: "",
            urls: Array
        },
        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        },
        methods: {
            colorize: function (points) {
                if (points < 199) return "green";
                if (points < 1000) return "orange";
                if (points > 999) return "red";
            },
            colorizebg: function (points) {
                if (points < 199) return "#dff9d7";
                if (points < 1000) return "#ffefd3";
                if (points > 999) return "#fbeaea";
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
            create_header: function(rating){
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
            second_opinion_links: function(rating, url){
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
            total_awarded_points: function(points) {
                if (points === 0)
                    marker = "✓ perfect";
                else
                    marker = points;
                return '<span class="total_awarded_points_'+ this.colorize(points) +'">' + marker + '</span>'
            },
            awarded_points: function(points) {
                if (points === 0)
                    marker = "✓ perfect";
                else
                    marker = points;
                return '<span class="awarded_points_'+ this.colorize(points) +'">+ ' + marker + '</span>'
            },
            create_type: function (endpoint) {
                if (endpoint.v4 === "True")
                    return endpoint.protocol + "/" + endpoint.port + " (IPv4)";
                return endpoint.protocol + "/" + endpoint.port + " (IPv6)";
            },
            load: function(OrganizationID, weeks_ago){

                if (!weeks_ago) {
                    weeks_ago = 0;
                }

                $.getJSON('/data/report/' + OrganizationID + '/' + weeks_ago, function (data) {
                    vueReport.urls = data.calculation["organization"]["urls"];
                    vueReport.points = data.rating;
                    vueReport.when = data.when;
                    vueReport.name = data.name;
                });
            },
            show_in_browser: function(){
                // you can only jump once to an anchor, unless you use a dummy
                location.hash = "#loading";
                location.hash = "#report";
            }
        }
    });

    window.vueFullScreenReport = new Vue({
        el: '#fullscreenreport',
        data: {
            calculation: '',
            rating: 0,
            when: 0,
            name: "",
            urls: Array,
            visible: false
        },
        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        },
        methods: {
            show: function(){
              this.visible = true;
            },
            hide: function(){
              this.visible = false;
            },
            colorize: function (points) {
                if (points < 199) return "green";
                if (points < 1000) return "orange";
                if (points > 999) return "red";
            },
            colorizebg: function (points) {
                if (points < 199) return "#dff9d7";
                if (points < 1000) return "#ffefd3";
                if (points > 999) return "#fbeaea";
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
            create_header: function(rating){
                return vueReport.create_header(rating);
            },
            second_opinion_links: function(rating, url){
                return vueReport.second_opinion_links(rating, url);
            },
            total_awarded_points: function(points) {
                if (points === 0)
                    marker = "✓ perfect";
                else
                    marker = points;
                return '<span class="total_awarded_points_'+ this.colorize(points) +'">' + marker + '</span>'
            },
            create_type: function (endpoint) {
                return vueReport.create_type(endpoint);
            },
            awarded_points: function(points) {
                if (points === 0)
                    marker = "✓ perfect";
                else
                    marker = points;
                return '<span class="awarded_points_'+ this.colorize(points) +'">+ ' + marker + '</span>'
            },
            load: function(OrganizationID, weeks_ago){
                vueMap.selected_organization = OrganizationID;

                if (!weeks_ago) {
                    weeks_ago = 0;
                }

                $.getJSON('/data/report/' + OrganizationID + '/' + weeks_ago, function (data) {
                    vueFullScreenReport.urls = data.calculation["organization"]["urls"];
                    vueFullScreenReport.points = data.rating;
                    vueFullScreenReport.when = data.when;
                    vueFullScreenReport.name = data.name;
                });
            }
        }
    });

    window.vueStatistics = new Vue({
        el: '#statistics',
        data: {
            data: Array
        },
        computed: {
            greenpercentage: function () {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["green"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
            },

            redpercentage: function () {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["red"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
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
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["no_rating"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
            },
            greenurlpercentage: function () {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["green_urls"] / this.data.data.now["total_urls"] * 100, 2) + "%";
            },

            redurlpercentage: function () {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["red_urls"] / this.data.data.now["total_urls"] * 100, 2) + "%";
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
            load: function(weeknumber) {
                $.getJSON('/data/stats/' + weeknumber, function (data) {
                    vueStatistics.data = data;
                });
            }
        }
    });

    window.vueDomainlist = new Vue({
        el: '#domainlist',
        data: {urls: Array},
        methods: {
            colorize: function (points) {
                if (points < 199) return "green";
                if (points < 1000) return "orange";
                if (points > 999) return "red";
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
                if (vueFullscreen.fullscreen == "View Full Screen"){
                    vueFullscreen.fullscreen = "Exit Full Screen"
                } else {
                    vueFullscreen.fullscreen = "View Full Screen"
                }
            }
        }
    });


    window.vueTopfail = new Vue({
        el: '#topfail',
        data: {top: Array},
        methods: {
            showReport: function (OrganizationID) {
                vueReport.show_in_browser();
                vueReport.load(OrganizationID, vueMap.week);
                vueDomainlist.load(OrganizationID, vueMap.week);
            },
            humanize: function (date) {
                return new Date(date).humanTimeStamp()
            },
            load: function(weeknumber) {
                $.getJSON('/data/topfail/' + weeknumber, function (data) {
                    vueTopfail.top = data;
                });
            }
        }
    });

    window.vueTopwin = new Vue({
        el: '#topwin',
        data: {top: Array},
        methods: {
            showReport: function (OrganizationID) {
                vueReport.show_in_browser();
                vueReport.load(OrganizationID, vueMap.week);
                vueDomainlist.load(OrganizationID, vueMap.week);
            },
            humanize: function (date) {
                return new Date(date).humanTimeStamp()
            },
            load: function (weeknumber) {
                $.getJSON('/data/topwin/' + weeknumber, function (data) {
                    vueTopwin.top = data;
                });
            }
        }
    });

    window.vueTerribleurls = new Vue({
        el: '#terrible_urls',
        data: {top: Array},
        methods: {
            showReport: function (OrganizationID) {
                vueReport.show_in_browser();
                vueReport.load(OrganizationID, vueMap.week);
                vueDomainlist.load(OrganizationID, vueMap.week);
            },
            humanize: function (date) {
                return new Date(date).humanTimeStamp()
            },
            load: function(weeknumber) {
                $.getJSON('/data/terrible_urls/' + weeknumber, function (data) {
                    vueTerribleurls.top = data;
                });
            }
        }
    });

    // vueMap.update_hourly(); // loops forever, something wrong with vue + settimeout?
    vueMap.load(0);
    vueTopwin.load(0);
    vueTopfail.load(0);
    vueStatistics.load(0);
    vueTerribleurls.load(0);
});

