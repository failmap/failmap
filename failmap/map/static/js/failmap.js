var failmap = {

    // the map will automatically scale to bounds of whatever you throw at it, so it will look "fair" on any device.
    // This is just a set of starting positons.

    // To help you get the coordinates;
    // this might help: http://ahalota.github.io/Leaflet.CountrySelect/demo.html
    // and add this after fitbounds:
    // console.log("if (country_name === \"" + e.feature.properties.name + "\")");
    // console.log("    return {\"coordinates\": [" + map.getCenter().lat + ", " + map.getCenter().lng+ "], \"zoomlevel\": " + map.getZoom() + "}");
    initial_location: function(country_shortcode) {
        if (country_shortcode === "nl")  // the netherlands
            return {"coordinates": [52.15, 5.8], "zoomlevel": 8};
        if (country_shortcode === "de")  // germany
            return {"coordinates": [51, 11], "zoomlevel": 6};

        return {"coordinates": [52.15, 5.8], "zoomlevel": 8};
    },


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

    initializemap: function (country_code) {
        // don't name this variable location, because that redirects the browser.
        loc = this.initial_location(country_code);
        this.map = L.map('map').setView(loc.coordinates, loc.zoomlevel);

        this.map.scrollWheelZoom.disable();
        let tile_uri_base = 'https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png';
        let tile_uri_params = 'access_token={accessToken}';
        let tile_uri = tile_uri_base + '?' + tile_uri_params;

        // allow tiles to be fetched through a proxy to apply our own caching rules
        // and prevent exhausion of free mapbox account credits
        if (this.proxy_tiles) {
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
                vueFullscreen.fullscreen = gettext("View Full Screen")  // ugly fix :)
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
            if (hash != undefined) {
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
            this._div.innerHTML = "<input id='searchbar' type='text' onkeyup='failmap.search(this.value)' placeholder=\"" + gettext('Search organization') + "\"/>";
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
                    sometext += '<b>' + gettext('High') + ': </b><span style="color: ' + failmap.getColor(1000) + '">' + props.high + '</span><br />';
                    sometext += '<b>' + gettext('Medium') + ': </b><span style="color: ' + failmap.getColor(500) + '">' + props.medium + '</span><br />';
                    sometext += '<b>' + gettext('Low') + ': </b><span style="color: ' + failmap.getColor(0) + '">' + props.low + '</span><br />';
                } else {
                    sometext += '<b>' + gettext('High') + ': </b><span style="color: ' + failmap.getColor(1000) + '">0</span><br />';
                    sometext += '<b>' + gettext('Medium') + ': </b><span style="color: ' + failmap.getColor(500) + '">0</span><br />';
                    sometext += '<b>' + gettext('Low') + ': </b><span style="color: ' + failmap.getColor(0) + '">0</span><br />';
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
                "    <h4>{{ visibleweek }}<span v-if='loading'> (" + gettext('Loading') + "...)</span></h4>" +
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
                "<tr><th>" + gettext('Url') + "</th>" +
                "<th width='5%'>" + gettext('H') + "</th>" +
                "<th width='5%'>" + gettext('M') + "</th>" +
                "<th width='5%'>" + gettext('L') + "</th></tr></thead>" +
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

            labels.push('<i style="background:' + failmap.getColor(199) + '"></i> '+ gettext('Good'));
            labels.push('<i style="background:' + failmap.getColor(999) + '"></i> '+ gettext('Mediocre'));
            labels.push('<i style="background:' + failmap.getColor(1000) + '"></i> '+ gettext('Bad'));
            labels.push('<i style="background:' + failmap.getColor(-1) + '"></i> '+ gettext('Unknown'));

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
        if (failmap.isSearchedFor(e.target.feature)) {
            if (e.target.feature.geometry.type === "MultiPolygon")
                e.target.setStyle(failmap.searchResultStyle(e.target.feature))
        } else {
            failmap.geojson.resetStyle(e.target);
        }
        failmap.info.update();
    },

    isSearchedFor: function (feature) {
        x = $('#searchbar').val();
        x = x.toLowerCase();
        if (!x || x === "")
            return false;
        return (feature.properties.organization_name.toLowerCase().indexOf(x) !== -1)
    },

    search: function (query) {
        query = query.toLowerCase();
        if ((query === "") || (!query)) {
            // reset
            failmap.geojson.eachLayer(function (layer) {
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
            if (json.features.length > 0) {
                vueMap.features = json.features;
            }

            // if there is one already, overwrite the attributes...
            if (failmap.geojson) {
                failmap.geojson.eachLayer(function (layer) {failmap.recolormap(json, layer)});
                vueMap.loading = false;
            } else {
                failmap.geojson = L.geoJson(json, {
                    style: failmap.style,
                    pointToLayer: failmap.pointToLayer,
                    onEachFeature: failmap.onEachFeature
                }).addTo(failmap.map); // only if singleton, its somewhat dirty.
                // fit the map automatically, regardless of the initial positions
                failmap.map.fitBounds(failmap.geojson.getBounds());
                vueMap.loading = false;
            }
        });
    },

    recolormap: function (json, layer) {
        // overwrite some properties
        // a for loop is not ideal.

        var existing_feature = layer.feature;
        console.log("existing layer");
        console.log(layer);


        for (i = 0; i < json.features.length; i++) {
            var new_feature = json.features[i];

            if (existing_feature.properties.organization_name === new_feature.properties.organization_name) {

                if (new_feature.geometry.coordinates !== existing_feature.geometry.coordinates){
                    console.log("changed");
                    console.log("old");
                    console.log(existing_feature.geometry.coordinates);
                    console.log("new");
                    console.log(new_feature.geometry.coordinates);

                    // it is not possible to change the shape of a layer :(
                    // therefore we have to remove this layer and replace it with the new one.
                    // removing doesn't work: you will still get the old layer(!)
                    layer.removeFrom(failmap.map);
                    layer.remove();
                    failmap.map.removeLayer(layer);
                    // failmap.geojson.removelayer(layer);
                    failmap.geojson.removeLayer(layer);

                    // the new item already has the color we need.
                    var asdasd = L.geoJson(new_feature, {
                        style: failmap.style,
                        pointToLayer: failmap.pointToLayer,
                        onEachFeature: failmap.onEachFeature
                    }).addTo(failmap.map);

                    // we should not manipulate anything else.
                    continue;
                }

                // only color changed
                // console.log(layer);
                existing_feature.properties.Overall = new_feature.properties.Overall;
                existing_feature.properties.color = new_feature.properties.color;
                // make the transition
                if (existing_feature.geometry.type === "MultiPolygon")
                    layer.setStyle(failmap.style(layer.feature));
                if (existing_feature.geometry.type === "Point") {
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
    },

    showreport: function (e) {
        let organization_id = e.target.feature.properties['organization_id'];
        if (failmap.map.isFullscreen()) {
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