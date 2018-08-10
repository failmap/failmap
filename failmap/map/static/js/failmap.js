var failmap = {

    map: null, // map showing geographical regions + markers
    polygons: L.geoJson(),  // geographical regions
    // todo: if you click the group too fast: Marker.js:181 Uncaught TypeError:
    // Cannot read property 'createIcon' of undefined
    markers: L.markerClusterGroup({iconCreateFunction: function(cluster){
        // getAllChildMarkers()
        // if 1 is red, marker is red else if 1 is orange, else green else gray.
        var css_class = "unknown";

        // good, medium, bad
        // todo: if red, break
        cluster.getAllChildMarkers().forEach(function (point){
            if (point.feature.properties.color === "red") {
                css_class = "red";
            }
        });

        return L.divIcon({
            html: '<div><span>' + cluster.getChildCount() + '</span></div>',
            className: 'marker-cluster marker-cluster-' + css_class,
            iconSize: new L.Point(40, 40) });
    }}),
    info: L.control(),
    legend: L.control({position: 'bottomright'}),
    hovered_organization: "",
    proxy_tiles: true,

    PointIcon: L.Icon.extend({
        options: {shadowUrl: '', iconSize: [16, 16], shadowSize: [0, 0], iconAnchor: [8, 8], shadowAnchor: [0, 0],
            popupAnchor: [-3, -76]
        }
    }),

    greenIcon: new L.Icon({iconUrl: 'static/images/green-dot.png'}),
    redIcon: new L.Icon({iconUrl: 'static/images/red-dot.png'}),
    orangeIcon: new L.Icon({iconUrl: 'static/images/orange-dot.png'}),
    grayIcon: new L.Icon({iconUrl: 'static/images/gray-dot.png'}),

    initialize: function (country_code) {
        // don't name this variable location, because that redirects the browser.
        loc = this.initial_location(country_code);
        this.map = L.map('map',
            { dragging: !L.Browser.mobile, touchZoom: true, tap: false}
            ).setView(loc.coordinates, loc.zoomlevel);

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

        // controls in sidepanels
        var html = "<div id=\"fullscreen\">" +
            "<span class='btn btn-success btn-lg btn-block' v-on:click='toggleFullScreen()'>{{fullscreen}}</span>" +
            "</div>";
        this.add_div(html, "info_nobackground", false);
        this.add_div('<div id="historycontrol"></div>', "info", false);
        this.add_div("<input id='searchbar' type='text' onkeyup='failmap.search(this.value)' placeholder=\"" + gettext('Search organization') + "\"/>", "info", true);
        this.add_info();
        this.add_div("<div id=\"domainlist\"></div>", "info", false);
        var labels=[];
        labels.push('<i style="background:' + failmap.getColorCode('green') + '"></i> '+ gettext('Perfect'));
        labels.push('<i style="background:' + failmap.getColorCode('yellow') + '"></i> '+ gettext('Good'));
        labels.push('<i style="background:' + failmap.getColorCode('orange') + '"></i> '+ gettext('Mediocre'));
        labels.push('<i style="background:' + failmap.getColorCode('red') + '"></i> '+ gettext('Bad'));
        labels.push('<i style="background:' + failmap.getColorCode('unknown') + '"></i> '+ gettext('Unknown'));
        this.add_div("<span class='legend_title'>" + gettext('legend_basic_security') + "</span><br />" + labels.join('<br />'), "info legend", false);
        this.add_div(document.getElementById('fullscreenreport').innerHTML, "fullscreenmap", true);
    },

    // To help you get the coordinates;
    // this might help to find new coordinates: http://ahalota.github.io/Leaflet.CountrySelect/demo.html
    // the map will always fit to bounds after loading the dataset, but at least it shows the right country if the
    // data lodas slow.
    initial_location: function(country_shortcode) {
        switch (country_shortcode){
            case "nl": return {"coordinates": [52.15, 5.8], "zoomlevel": 8};
            case "de": return {"coordinates": [51, 11], "zoomlevel": 6};
            default: return {"coordinates": [52.15, 5.8], "zoomlevel": 8}; // nl
        }
    },

    // where you don't need to access the div again with js:
    add_div: function(html, style, clickable) {
        new_div = L.control();
        new_div.onAdd = function () {
            this._div = L.DomUtil.create('div', style);
            this._div.innerHTML = html;
            if (clickable)
                L.DomEvent.disableClickPropagation(this._div);
            return this._div;
        };
        new_div.addTo(this.map);
    },

    add_info: function () {
        this.info.onAdd = function (map) {
            this._div = L.DomUtil.create('div', 'info');
            L.DomEvent.disableClickPropagation(this._div);
            return this._div;
        };

        this.info.update = function (props) {
            var sometext = "";
            if (props) {
                sometext += "<h4>" + props.organization_name + "</h4>";
                if (props.high || props.medium || props.low) {
                    sometext += '<b>' + gettext('High') + ': </b><span style="color: ' + failmap.getColorCode('red') + '">' + props.high + '</span><br />';
                    sometext += '<b>' + gettext('Medium') + ': </b><span style="color: ' + failmap.getColorCode('orange') + '">' + props.medium + '</span><br />';
                    sometext += '<b>' + gettext('Low') + ': </b><span style="color: ' + failmap.getColorCode('green') + '">' + props.low + '</span><br />';
                } else {
                    sometext += '<b>' + gettext('High') + ': </b><span style="color: ' + failmap.getColorCode('red') + '">0</span><br />';
                    sometext += '<b>' + gettext('Medium') + ': </b><span style="color: ' + failmap.getColorCode('orange') + '">0</span><br />';
                    sometext += '<b>' + gettext('Low') + ': </b><span style="color: ' + failmap.getColorCode('green') + '">0</span><br />';
                }
                this._div.innerHTML = sometext;
            }
        };

        this.info.addTo(this.map);
    },

    getColorCode: function (d) {
        return d === "red" ? '#bd383c' : d === "orange" ? '#fc9645' : d === "yellow" ? '#d3fc6a' : d === "green" ? '#62fe69' : '#c1bcbb';
    },

    style: function (feature) {
        return {weight: 1, opacity: 1, color: 'white', dashArray: '0', fillOpacity: 0.7,
            fillColor: failmap.getColorCode(feature.properties.color)
        };
    },

    searchResultStyle: function (feature) {
        return {weight: 1, opacity: 1, color: 'white', dashArray: '0', fillOpacity: 0.1};
    },

    pointToLayer: function (geoJsonPoint, latlng) {
        console.log(latlng);
        switch (geoJsonPoint.properties.color){
            case "red": return L.marker(latlng, {icon: failmap.redIcon});
            case "orange": return L.marker(latlng, {icon: failmap.orangeIcon});
            case "green": return L.marker(latlng, {icon: failmap.greenIcon});
        }
        return L.marker(latlng, {icon: failmap.grayIcon});
    },

    highlightFeature: function (e) {
        var layer = e.target;

        // doesn't work for points, only for polygons and lines
        if (typeof layer.setStyle === "function") {
            layer.setStyle({weight: 1, color: '#ccc', dashArray: '0', fillOpacity: 0.7});
            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                layer.bringToFront();
            }
        }
        failmap.info.update(layer.feature.properties);
        vueDomainlist.load(layer.feature.properties.organization_id, vueMap.week);
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
                e.target.setStyle(failmap.searchResultStyle(e.target.feature));
            if (e.target.feature.geometry.type === "Polygon")
                e.target.setStyle(failmap.searchResultStyle(e.target.feature));
        } else {
            failmap.polygons.resetStyle(e.target);
        }
        failmap.info.update();
    },

    isSearchedFor: function (feature) {
        x = $('#searchbar').val();
        x = x.toLowerCase();
        if (!x || x === "")
            return false;
        return (feature.properties.organization_name.toLowerCase().indexOf(x) === -1)
    },

    search: function (query) {
        query = query.toLowerCase();
        if ((query === "") || (!query)) {
            // reset
            failmap.polygons.eachLayer(function (layer) {
                switch (layer.feature.geometry.type){
                    case "MultiPolygon": layer.setStyle(failmap.style(layer.feature)); break;
                    case "Polygon": layer.setStyle(failmap.style(layer.feature)); break;
                    // no default.
                    // todo: point.
                }
            });
        } else {
            // text match
            failmap.polygons.eachLayer(function (layer) {
                if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) === -1) {
                    switch (layer.feature.geometry.type){
                        case "MultiPolygon": layer.setStyle(failmap.searchResultStyle(layer.feature)); break;
                        case "Polygon": layer.setStyle(failmap.searchResultStyle(layer.feature)); break;
                        // no default.
                        // todo: point.
                    }
                } else {
                    switch (layer.feature.geometry.type) {
                        case "MultiPolygon": layer.setStyle(failmap.style(layer.feature)); break;
                        case "Polygon": layer.setStyle(failmap.style(layer.feature)); break;
                        // no default.
                        // todo: point.
                    }
                }
            });
        }
    },

    plotdata: function (mapdata) {
        // mapdata is a mix of polygons and multipolygons, and whatever other geojson types.
        regions = [];
        points = [];

        // the data is plotted on two separate layers which both have special properties.
        // both layers have a different way of searching, clicking behaviour and so forth.
        for(var i=0; i<mapdata.features.length; i++){
            switch (mapdata.features[i].geometry.type){
                case "Polygon":
                case "MultiPolygon":
                    regions.push(mapdata.features[i]);
                break;
                case "Point":
                    points.push(mapdata.features[i]);
                break;
            }
        }

        // if there is one already, overwrite the attributes...
        if (failmap.polygons) {
            // add all features that are not part of the current map at all
            // and delete the ones that are not in the current set
            failmap.clean_map(regions);

            // update existing layers (and add ones with the same name)
            failmap.polygons.eachLayer(function (layer) {failmap.recolormap(regions, layer)});
        } else {
            // add regions
            failmap.polygons = L.geoJson(regions, {
                style: failmap.style,
                pointToLayer: failmap.pointToLayer,
                onEachFeature: failmap.onEachFeature
            }).addTo(failmap.map); // only if singleton, its somewhat dirty.

            // and points
            points.forEach(function(point){
                console.log(point);
                pointlayer = failmap.pointToLayer(point, L.latLng(point.geometry.coordinates.reverse()));

                pointlayer.on({
                    mouseover: failmap.highlightFeature,
                    mouseout: failmap.resetHighlight,
                    click: failmap.showreport
                });

                // allow opening of reports and such in the old way.
                pointlayer.feature = {"properties": point.properties};
                console.log(pointlayer);

                failmap.markers.addLayer(pointlayer);
            });
            failmap.map.addLayer(failmap.markers);

            // fit the map automatically, regardless of the initial positions
            failmap.map.fitBounds(failmap.polygons.getBounds());
        }
    },

    clean_map: function(mapdata) {
        // add layers to the map that are only in the new dataset (new)
        for (var i = 0; i < mapdata.features.length; i++) {
            var found = false;
            failmap.polygons.eachLayer(function bla(layer){
                if (layer.feature.properties.organization_name === mapdata.features[i].properties.organization_name) {
                    found = true;
                }
            });
            //console.log("To add. Found: " + !found + " " + mapdata.features[i].properties.organization_name);
            if (!found) {
                // console.log("Going to add an organization named " + mapdata.features[i].properties.organization_name);
                failmap.polygons.addData(mapdata.features[i]);
            }
        }

        // remove existing layers that are not in the new dataset
        failmap.polygons.eachLayer(function bla(layer){
            var found = false;
            for (var i = 0; i < mapdata.features.length; i++) {
                if (layer.feature.properties.organization_name === mapdata.features[i].properties.organization_name) {
                    found = true;
                }
            }
            // console.log("To remove. Found: " + !found + " " + layer.feature.properties.organization_name);
            if (!found){
                failmap.polygons.removeLayer(layer);
                // failmap.deleteLayerByName(mapdata.features[i].properties.organization_name);
            }

        });
    },

    deleteLayerByName: function (name) {
        console.log("Deleting layer named: " + name);
        failmap.polygons.eachLayer(function bla(layer) {
            if (layer.feature.properties.organization_name === name) {
                failmap.polygons.removeLayer(layer);
            }
        })
    },

    // overwrite some properties
    recolormap: function (mapdata, layer) {
        var existing_feature = layer.feature;

        // mapdata.onEachFeature(function (new_feature){ doesn;'t work

        mapdata.features.forEach(function (new_feature){


        });

        for (i = 0; i < mapdata.features.length; i++) {
            new_feature = mapdata.features[i];
            if (existing_feature.properties.organization_name === new_feature.properties.organization_name) {

                // No simple array comparison in JS
                // So new_feature.geometry.coordinates !== existing_feature.geometry.coordinates will not work.
                // https://stackoverflow.com/questions/7837456/how-to-compare-arrays-in-javascript#19746771
                if (JSON.stringify(new_feature.geometry.coordinates) !== JSON.stringify(existing_feature.geometry.coordinates)){
                    // Geometry changed, updating shape. Will not fade.
                    // It seems not possible to update the geometry of a shape, too bad.
                    failmap.polygons.removeLayer(layer);
                    failmap.polygons.addData(new_feature);

                } else {
                    // colors changed, shapes / points on the map stay the same.
                    existing_feature.properties.Overall = new_feature.properties.Overall;
                    existing_feature.properties.color = new_feature.properties.color;
                    // make the transition
                    switch(existing_feature.geometry.type){
                        case "Polygon":
                        case "MultiPolygon":
                            layer.setStyle(failmap.style(layer.feature)); break;
                        case "Point":
                            switch(layer.feature.properties.color) {
                                case "red": layer.setIcon(failmap.redIcon); break;
                                case "orange": layer.setIcon(failmap.orangeIcon); break;
                                case "green": layer.setIcon(failmap.greenIcon); break;
                                default: layer.setIcon(failmap.grayIcon);
                            }
                            break;
                    }
                }
            }
        }

    },

    showreport: function (e) {
        console.log(e);

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