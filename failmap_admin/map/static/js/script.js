// Currently we're migrating to Vue.
// https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc
// also: reacts patent clause and mandatory jsx syntax ... NO

// Registry Sentry for error reporting
let sentry_token = document.head.querySelector("[name=sentry_token]").getAttribute('content');
let version = document.head.querySelector("[name=version]").getAttribute('content');
if (sentry_token){
    Raven.config(sentry_token, {release: version}).install();
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
    proxy_tiles: true,

    initializemap: function () {
        this.map = L.map('map').setView([52.15, 5.8], 8);
        this.map.scrollWheelZoom.disable();
        let tile_uri_base = 'https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png';
        let tile_uri_params = 'access_token={accessToken}';
        let tile_uri = tile_uri_base + '?' + tile_uri_params;

        // allow tiles to be fetched through a proxy to apply our own caching rules
        // and prevent exhausion of free mapbox account credits
        if (this.proxy_tiles){
            tile_uri = '/proxy/' + tile_uri_base;
        }

        L.tileLayer(tile_uri, {
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

        //
        var currentHash = ""
        $(document).scroll(function () {
            let current_anchor = $('a.jumptonav').filter(function () {
                var top = window.pageYOffset;
                var distance = top - $(this).offset().top;
                var hash = $(this).attr('name');
                // 30 is an arbitrary padding choice,
                // if you want a precise check then use distance===0
                if (distance < 30 && distance > -30 && currentHash != hash) {
                    return true;
                }
            }).first();

            var hash = current_anchor.attr('name');
            if (hash != undefined){
                history.replaceState({}, '', '#' + hash);
                currentHash = hash;
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
            this._div.innerHTML = document.getElementById('fullscreenreport').innerHTML;
            return this._div;
        };

        this.fullscreenreport.addTo(this.map);
    },

    add_searchbar: function () {
        this.searchbar.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            this._div.innerHTML = "<input id='searchbar' type='text' onkeyup='failmap.search(this.value)' placeholder=\"Zoek op gemeente...\"/>";
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
                sometext += "<h4>" + props.organization_name + "</h4>";
                if (props.high || props.medium || props.low) {
                    sometext += '<b>High: </b><span style="color: ' + failmap.getColor(1000) + '">' + props.high + '</span><br />';
                    sometext += '<b>Medium: </b><span style="color: ' + failmap.getColor(500) + '">' + props.medium + '</span><br />';
                    sometext += '<b>Low: </b><span style="color: ' + failmap.getColor(0) + '">' + props.low + '</span><br />';
                } else {
                    sometext += '<b>High: </b><span style="color: ' + failmap.getColor(1000) + '">0</span><br />';
                    sometext += '<b>Medium: </b><span style="color: ' + failmap.getColor(500) + '">0</span><br />';
                    sometext += '<b>Low: </b><span style="color: ' + failmap.getColor(0) + '">0</span><br />';
                }
                vueDomainlist.load(props.organization_id, vueMap.week);
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
                "<table width='100%'><thead>" +
                "<tr><th>Url</th><th width='5%'>H</th><th width='5%'>M</th><th width='5%'>L</th></tr></thead>" +
                "<tr v-for=\"url in urls\">\n" +
                "<td><span v-bind:class=\"colorize(url.high, url.medium, url.low)\">{{ url.url }}</span></td>" +
                "<td><span v-bind:class=\"colorize(url.high, url.medium, url.low)\">{{ url.high }}</span></td>" +
                "<td><span v-bind:class=\"colorize(url.high, url.medium, url.low)\">{{ url.medium }}</span></td>" +
                "<td><span v-bind:class=\"colorize(url.high, url.medium, url.low)\">{{ url.low }}</span></td>\n" +
                "</tr></table>\n" +
                "</div>";
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
        location.hash = "#" + layer.feature.properties['organization_name'];
    },

    isSearchedFor: function(feature){
        x = $('#searchbar').val();
        x = x.toLowerCase();
        if (!x || x === "")
            return false;
        return (feature.properties.organization_name.toLowerCase().indexOf(x) !== -1)
    },

    search: function(query) {
        query = query.toLowerCase();
        if ((query === "") || (!query)){
            // reset
            failmap.geojson.eachLayer(function(layer) {
                if (layer.feature.geometry.type === "MultiPolygon")
                    layer.setStyle(failmap.style(layer.feature))
            });
        } else {
            // text match
            failmap.geojson.eachLayer(function (layer) {
                if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) !== -1) {
                    if (layer.feature.geometry.type === "MultiPolygon")
                        layer.setStyle(failmap.searchResultStyle(layer.feature))
                } else {
                    if (layer.feature.geometry.type === "MultiPolygon")
                        layer.setStyle(failmap.style(layer.feature))
                }
            });
        }

    },

    /* Transition, which is much smoother. */
    loadmap: function (weeknumber) {
        vueMap.loading = true;
        $.getJSON('/data/map/' + weeknumber, function (json) {
            // make map features (organization data) available to other vues
            // do not update this attribute if an empty list is returned as currently
            // the map does not remove organizations for these kind of responses.
            if (json.features.length > 0){
                vueMap.features = json.features;
            }

            // if there is one already, overwrite the attributes...
            if (failmap.geojson) {
                failmap.geojson.eachLayer(function(layer){
                    // overwrite some properties
                    // a for loop is not ideal.
                    for (i = 0; i < json.features.length; i++) {
                        if (layer.feature.properties.organization_name === json.features[i].properties.organization_name){
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
        let organization_id = e.target.feature.properties['organization_id'];
        if (failmap.map.isFullscreen()){
            // var layer = e.target;
            vueFullScreenReport.load(organization_id, vueMap.week);
            vueFullScreenReport.show();

            // Load the report for when you leave fullscreen
            // perhaps this should be in the leave fullscreen event handler
            vueReport.load(organization_id, vueMap.week);
        } else {
            // trigger load of organization data and jump to Report view.
            location.href = '#report';
            vueReport.selected = organization_id;
        }
    }
};

$(document).ready(function () {
    failmap.initializemap();
    lazyload();
    d3stats();

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
            promise: false,
        },
        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        },
        computed: {
            // load list of organizations from map features
            organizations: function(){
                if (vueMap.features != null){
                    let organizations = vueMap.features.map(function(feature){
                        return {
                            "id": feature.properties.organization_id,
                            "name": feature.properties.organization_name,
                        }
                    });
                    return organizations.sort(function(a,b){
                        if (a['name'] > b['name']) return 1;
                        if (a['name'] < b['name']) return -1;
                        return 0;
                    });
                }
            }
        },
        watch: {
            selected: function(){
                // load selected organization id
                this.load(this.selected);
            }
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
            total_awarded_points: function(high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="total_awarded_points_'+ this.colorize(high, medium, low) +'">' + marker + '</span>'
            },
            organization_points: function(high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="total_awarded_points_'+ this.colorize(high, medium, low) +'">' + marker + '</span>'
            },
            awarded_points: function(high, medium, low) {
                var marker = vueReport.make_marker(high, medium, low);
                return '<span class="awarded_points_'+ this.colorize(high, medium, low) +'">+ ' + marker + '</span>'
            },
            make_marker: function(high, medium, low) {
                if (high === 0 && medium === 0 && low === 0)
                    return "perfect";
                else if (high > 0)
                    return "hoog";
                else if (medium > 0)
                    return "midden";
                else
                    return "laag";
            },
            endpoint_type: function (endpoint) {
                return endpoint.protocol + "/" + endpoint.port + " (IPv" + endpoint.ip_version + ")";
            },
            load: function(organization_id, weeks_ago){

                if (!weeks_ago) {
                    weeks_ago = 0;
                }
                vueReport.loading = true;
                vueReport.name = null;
                $.getJSON('/data/report/' + organization_id + '/' + weeks_ago, function (data) {
                    vueReport.loading = false;
                    vueReport.urls = data.calculation["organization"]["urls"];
                    vueReport.points = data.rating;
                    vueReport.high = data.calculation["organization"]["high"];
                    vueReport.medium = data.calculation["organization"]["medium"];
                    vueReport.low = data.calculation["organization"]["low"];
                    vueReport.when = data.when;
                    vueReport.name = data.name;
                    vueReport.twitter_handle = data.twitter_handle;
                    vueReport.promise = data.promise;

                    // include id in anchor to allow url sharing
                    let newHash = 'report-' + organization_id;
                    $('a#report-anchor').attr('name', newHash)
                    history.replaceState({}, '', '#' + newHash);
                });
            },
            show_in_browser: function(){
                // you can only jump once to an anchor, unless you use a dummy
                location.hash = "#loading";
                location.hash = "#report";
            },
            create_twitter_link: function(name, twitter_handle, points){
                if (twitter_handle) {
                    if (points) {
                        return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft ' + points + ' punten op Faalkaart! Bescherm mijn gegevens beter! 🥀&hashtags=' + name + ',faal,faalkaart"><img src="/static/images/twitterwhite.png" width="14" /> Tweet!</a>';
                    } else {
                        return "<a role='button' class='btn btn-xs btn-info' target='_blank' href=\"https://twitter.com/intent/tweet?screen_name=" + twitter_handle + '&text=' + name + ' heeft alles op orde! 🌹&hashtags=' + name + ',win,faalkaart"><img src="/static/images/twitterwhite.png" width="14" /> Tweet!</a>';
                    }
                }
            },
            formatDate: function(date){
                return new Date(date).toISOString().substring(0, 10)
            }
        }
    });

    window.vueFullScreenReport = new Vue({
        el: '#fullscreenreport',
        data: {
            calculation: '',
            rating: 0,
            points: 0,
            high: 0,
            medium: 0,
            low: 0,
            when: 0,
            name: "",
            twitter_handle: '',
            urls: Array,
            visible: false,
            mailto: document.head.querySelector("[name=mailto]").getAttribute('content')
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
            colorize: function (high, medium, low) {
               return vueReport.colorize(high, medium, low);
            },
            colorizebg: function (high, medium, low) {
                return vueReport.colorizebg(high, medium, low);
            },
            idize: function (url) {
                return vueReport.idize(url);
            },
            idizetag: function (url) {
                return vueReport.idizetag(url);
            },
            humanize: function (date) {
                return vueReport.humanize(date);
            },
            create_header: function(rating){
                return vueReport.create_header(rating);
            },
            second_opinion_links: function(rating, url){
                return vueReport.second_opinion_links(rating, url);
            },
            organization_points: function(high, medium, low) {
                return vueReport.organization_points(high, medium, low);
            },
            total_awarded_points: function(high, medium, low) {
                return vueReport.total_awarded_points(high, medium, low);
            },
            endpoint_type: function (endpoint) {
                return vueReport.endpoint_type(endpoint);
            },
            awarded_points: function(high, medium, low) {
                return vueReport.awarded_points(high, medium, low);
            },
            load: function(organization_id, weeks_ago){
                vueMap.selected_organization = organization_id;

                if (!weeks_ago) {
                    weeks_ago = 0;
                }

                $.getJSON('/data/report/' + organization_id + '/' + weeks_ago, function (data) {
                    vueFullScreenReport.urls = data.calculation["organization"]["urls"];
                    vueFullScreenReport.points = data.rating;
                    vueFullScreenReport.high = data.calculation["organization"]["high"];
                    vueFullScreenReport.medium = data.calculation["organization"]["medium"];
                    vueFullScreenReport.low = data.calculation["organization"]["low"];
                    vueFullScreenReport.when = data.when;
                    vueFullScreenReport.name = data.name;
                    vueFullScreenReport.twitter_handle = data.twitter_handle;
                });
            },
            create_twitter_link: function(name, twitter_handle, points) {
                return vueReport.create_twitter_link(name, twitter_handle, points);
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
            showReport: function (organization_id) {
                vueReport.show_in_browser();
                vueReport.load(organization_id, vueMap.week);
                vueDomainlist.load(organization_id, vueMap.week);
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
            showReport: function (organization_id) {
                vueReport.show_in_browser();
                vueReport.load(organization_id, vueMap.week);
                vueDomainlist.load(organization_id, vueMap.week);
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
            showReport: function (organization_id) {
                vueReport.show_in_browser();
                vueReport.load(organization_id, vueMap.week);
                vueDomainlist.load(organization_id, vueMap.week);
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

    // if browser contains report anchor with organization id load that organization
    let match = RegExp('report-([0-9]+)').exec(location.hash);
    if (match){
        let organization_id = match[1];
        location.href = '#report';
        vueReport.selected = organization_id;
    }
});

function d3stats(){
        // bl.ocks.org
    // https://bl.ocks.org/mbostock/3885211
    // https://www.mattlayman.com/2015/d3js-area-chart.html
    // https://github.com/d3/d3/blob/master/API.md
    var tooltip = d3.select("body")
        .append("div")
        .attr("class", "remove")
        .attr("class", "d3_tooltip")
        .style("visibility", "hidden")
        .style("top", "30px")
        .style("left", "55px");


    d3.json("data/vulnstats/0/index.json", function (error, data) {
        stacked_area_chart("tls_qualys", error, data.tls_qualys);
        stacked_area_chart("plain_https", error, data.plain_https);
        stacked_area_chart("security_headers_strict_transport_security", error, data.security_headers_strict_transport_security);
        stacked_area_chart("security_headers_x_frame_options", error, data.security_headers_x_frame_options);
        stacked_area_chart("security_headers_x_content_type_options", error, data.security_headers_x_content_type_options);
        stacked_area_chart("security_headers_x_xss_protection", error, data.security_headers_x_xss_protection);
    });

    // tooltip value.
    // this is declared globally, otherwise the value would be overwritten by the many "gaps" that are automatically
    // filled by SVG (see below)
    pro = 0;

    function stacked_area_chart(element, error, data) {
        // chart layout
        var svg = d3.select("#" + element),
            margin = {top: 20, right: 20, bottom: 30, left: 50},
            width = svg.attr("width") - margin.left - margin.right,
            height = svg.attr("height") - margin.top - margin.bottom;

        var parseDate = d3.timeParse("%Y-%m-%d");

        var x = d3.scaleTime().range([0, width]),
            y = d3.scaleLinear().range([height, 0]),
            z = d3.scaleOrdinal(['yellow', 'orange', 'red']);

        var stack = d3.stack();

        // https://bl.ocks.org/d3noob/ced1b9b18bd8192d2c898884033b5529
        var area = d3.area()
            .x(function (d, i) {
                return x(parseDate(d.data.date));
            })
            .y0(function (d) {
                return y(d[0]);
            })
            .y1(function (d) {
                return y(d[1]);
            })
            .curve(d3.curveMonotoneX);

        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");


        // plotting values on the chart
        if (error) throw error;

        var keys = ["low", "medium", "high"];

        x.domain(d3.extent(data, function (d) {
            return parseDate(d.date);
        }));
        y.domain([0, d3.max(data, function (d) {
            return (d.high + d.medium + d.low);
        })]);

        stack.keys(keys);
        z.domain(keys);

        var layer = g.selectAll(".layer")
            .data(stack(data))
            .enter().append("g")
            .attr("class", "layer");

        layer.append("path")
            .attr("class", "area")
            .style("fill", function (d) {
                return z(d.key);
            })
            .attr("d", area);

        layer.filter(function (d) {
            return d[d.length - 1][1] - d[d.length - 1][0] > 0.01;
        })
            .append("text")
            .attr("x", width - 6)
            .attr("y", function (d) {
                return y((d[d.length - 1][0] + d[d.length - 1][1]) / 2);
            })
            .attr("dy", ".35em")
            .style("font", "10px sans-serif")
            .style("text-anchor", "end")
            .text(function (d) {
                return d.key;
            });

        g.append("g")
            .attr("class", "axis axis--x")
            .attr("transform", "translate(0," + height + ")")
            //.ticks(d3.time.weeks);  Uncaught TypeError: Cannot read property 'weeks' of undefined
            .call(d3.axisBottom(x).ticks(4));

        //
        g.append("g")
            .attr("class", "axis axis--y")
            .call(d3.axisLeft(y).ticks(6));


        // taken from:
        // tooltips http://bl.ocks.org/WillTurman/4631136
        // with various customizations, especially in the hashing function for month + date
        // given: februari 1st = 2 + 1 = 3 and januari second = 1 + 2 = 3. Use isodates as strings and it works.
        var datearray = [];

        svg.selectAll(".layer")
            .attr("opacity", 1)
            .on("mouseover", function (d, i) {
                svg.selectAll(".layer").transition()
                    .duration(250)
                    .attr("opacity", function (d, j) {
                        return j !== i ? 0.6 : 1;
                    })
            })

            // calculating this every time the mouse moves seems a bit excessive.
            .on("mousemove", function (d, i) {
                // console.log("d");
                // console.log(d);
                mouse = d3.mouse(this);
                mousex = mouse[0];
                var invertedx = x.invert(mousex);
                // console.log(invertedx);

                // downsampling to days, using a hash function to find the correct value.
                invertedx = "" + invertedx.getFullYear() + invertedx.getMonth() + invertedx.getDate(); // nr of month day of the month
                // console.log("invertedx");
                // console.log(invertedx);
                var selected = d;
                for (var k = 0; k < selected.length; k++) {
                    // daite = Date(selected[k].data.date);
                    // console.log(daite.toLocaleString());
                    mydate = new Date(selected[k].data.date);
                    datearray[k] = "" + mydate.getFullYear() + mydate.getMonth() + mydate.getDate();
                }

                // invertedx can have any day value, for example; d3js does a fill of dates you don't have.
                // and invertedx can thus have one of those filled days that are not in your dataset.
                // therefore you can't read the data from your dataset and get a typeerror.
                // therefore we check on mousedate.

                // console.log("datearray");
                // console.log(datearray);
                // todo: we could find the date that's "closest by", but in the end the result will remain grainy
                // due to the filled dates.
                mousedate = datearray.indexOf(invertedx);  // returns -1 if not in index


                if (mousedate !== -1) {
                    pro = d[mousedate][1] - d[mousedate][0];
                }

                d3.select(this)
                    .classed("hover", true),
                    // mouse is the location of the mouse on the graph.
                    // v4 has clientx and clienty, which resembles the document.
                    tooltip.html("<p>" + d.key + "<br>" + pro + "</p>")
                        .style("visibility", "visible")
                        .style("top", (window.pageYOffset + d3.event.clientY + 25)+ "px")
                        .style("left", (window.pageXOffset + d3.event.clientX) + "px");



            })
            .on("mouseout", function (d, i) {
                svg.selectAll(".layer")
                    .transition()
                    .duration(550)
                    .attr("opacity", "1");
                d3.select(this)
                    .classed("hover", false)
                    .attr("stroke-width", "0px"),
                    tooltip.html("<p>" + d.key + "<br>" + pro + "</p>")
                        .style("visibility", "hidden");
            });


    }
}