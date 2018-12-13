const failmap = {

    map: null, // map showing geographical regions + markers
    mapbox_token: '',
    proxy_tiles: true,

    polygons: L.geoJson(),  // geographical regions

    markers: L.markerClusterGroup(
        {
            iconCreateFunction: function(cluster){
            // if 1 is red, marker is red else if 1 is orange, else green else gray.
            let css_class = "unknown";

            // good, medium, bad
            // todo: if red, break
            // you can't break a forEach, therefore we're using an old school for loop here
            let childmarkers = cluster.getAllChildMarkers();
            let colors = ["unknown", "green", "yellow", "orange"];
            let selected_color = 0;

            for (let point of childmarkers) {
                if (point.feature.properties.color === "red") {
                    css_class = "red"; break;
                }

                if (colors.indexOf(point.feature.properties.color) > selected_color){
                    selected_color = colors.indexOf(point.feature.properties.color);
                    css_class = point.feature.properties.color;
                }
            }

            return L.divIcon({
                html: '<div><span>' + cluster.getChildCount() + '</span></div>',
                className: 'marker-cluster marker-cluster-' + css_class,
                // title: 'SWAG',  // properties.organization_name
                iconSize: [40, 40] });  // why a new L.Point? new L.Point(40, 40)
            }
        }

    ),

    initialize: function (mapbox_token, country_code, debug, show_filters=true) {
        this.mapbox_token = mapbox_token;

        // don't name this variable location, because that redirects the browser.
        loc = this.initial_location(country_code);
        this.map = L.map('map',
            { dragging: !L.Browser.mobile, touchZoom: true, tap: false, zoomSnap: 0.2}
            ).setView(loc.coordinates, loc.zoomlevel);

        this.map.scrollWheelZoom.disable();

        this.map.on('fullscreenchange', function () {
            if (failmap.map.isFullscreen()) {
                console.log('entered fullscreen');
            } else {
                vueFullScreenReport.hide();
                vueFullscreen.fullscreen = gettext("View Full Screen")  // ugly fix :)
            }
        });

        //
        let currentHash = "";
        $(document).scroll(function () {
            let current_anchor = $('a.jumptonav').filter(function () {
                let top = window.pageYOffset;
                let distance = top - $(this).offset().top;
                let hash = $(this).attr('name');
                // 30 is an arbitrary padding choice,
                // if you want a precise check then use distance===0
                if (distance < 30 && distance > -30 && currentHash !== hash) {
                    return true;
                }
            }).first();

            let hash = current_anchor.attr('name');
            if (hash !== undefined) {
                history.replaceState({}, '', '#' + hash);
                currentHash = hash;
            }
        });

        // controls in sidepanels
        let html = "<div id=\"fullscreen\">" +
            "<span class='btn btn-success btn-lg btn-block' v-on:click='toggleFullScreen()'>{{fullscreen}}</span>" +
            "</div>";

        this.add_div(html, "info_nobackground", false);

        if (show_filters)
            this.add_div('<div id="historycontrol"></div>', "info table-light", true);

        this.add_div("<input id='searchbar' type='text' onkeyup='failmap.search(this.value)' placeholder=\"" + gettext('Search organization') + "\"/>", "info table-light", true);
        this.add_div("<div><div id='infobox'></div><br /><br /><div id='domainlist'></div></div>", "info table-light", true);
        let labels=[];
        labels.push('<i style="background:' + failmap.getColorCode('green') + '"></i> '+ gettext('Perfect'));
        labels.push('<i style="background:' + failmap.getColorCode('yellow') + '"></i> '+ gettext('Good'));
        labels.push('<i style="background:' + failmap.getColorCode('orange') + '"></i> '+ gettext('Mediocre'));
        labels.push('<i style="background:' + failmap.getColorCode('red') + '"></i> '+ gettext('Bad'));
        labels.push('<i style="background:' + failmap.getColorCode('unknown') + '"></i> '+ gettext('Unknown'));
        this.add_div("<span class='legend_title'>" + gettext('legend_basic_security') + "</span><br />" + labels.join('<br />'), "info legend table-light", false, {position: 'bottomright'});
        this.add_div(document.getElementById('fullscreenreport').innerHTML, "fullscreenmap", true);

        // scale
        L.control.scale().addTo(this.map);

        // show whole map:
        // https://gist.github.com/stefanocudini/a5cde3c11c9b1f277368
        (function() {
            var control = new L.Control({position:'topleft'});
            control.onAdd = function(map) {
                    var azoom = L.DomUtil.create('a','resetzoom');
                    azoom.innerHTML = "<span title='Show all data on map.' style='font-size: 1.4em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>🗺️</span>";
                    L.DomEvent
                        .disableClickPropagation(azoom)
                        .addListener(azoom, 'click', function() {
                            // do not roll your own min() or max() over the bounds of these markers. It might wrap
                            // around.
                            let paddingToLeft = 0;
                            if (document.documentElement.clientWidth > 768)
                                paddingToLeft=320;

                            let bounds = failmap.polygons.getBounds();
                            bounds.extend(failmap.markers.getBounds());

                            map.fitBounds(bounds,
                                {paddingTopLeft: [0,0], paddingBottomRight: [paddingToLeft, 0]})
                        }, azoom);
                    return azoom;
                };
            return control;
        }())
        .addTo(this.map);

        this.light_map = new L.tileLayer(this.tile_uri(), {
            maxZoom: 18,
            attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
            '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
            'Imagery © <a href="http://mapbox.com">Mapbox</a>, ' +
            'Data &copy; <a href="http://failmap.org/">Fail Map</a> <a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-NC-BY-SA</a>',
            id: 'mapbox.light',
            accessToken: this.mapbox_token,
            style: 'light-v9',
            tileSize: 512,
            zoomOffset: -1
        });

        this.dark_map = new L.tileLayer(this.tile_uri(), {
            maxZoom: 18,
            attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
            '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
            'Imagery © <a href="http://mapbox.com">Mapbox</a>, ' +
            'Data &copy; <a href="http://failmap.org/">Fail Map</a> <a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-NC-BY-SA</a>',
            id: 'mapbox.light',
            accessToken: this.mapbox_token,
            style: 'dark-v9',
            tileSize: 512,
            zoomOffset: -1
        });

        if (debug)
            this.emptyTiles();
        else
            this.loadTiles();
    },

    tile_uri: function() {
        let tile_uri_base = 'https://api.mapbox.com/styles/v1/mapbox/{style}/tiles/{z}/{x}/{y}/';
        let tile_uri_params = 'access_token={accessToken}';
        let tile_uri = tile_uri_base + '?' + tile_uri_params;

        // allow tiles to be fetched through a proxy to apply our own caching rules
        // and prevent exhausion of free mapbox account credits
        if (this.proxy_tiles) {
            tile_uri = '/proxy/' + tile_uri_base;
        }

        return tile_uri;
    },

    set_theme: function(theme_name) {
        this.map.removeLayer(this.active_layer);

        if (theme_name === "light")
            this.active_layer = this.light_map;

        if (theme_name === "dark")
            this.active_layer = this.dark_map;

        this.map.addLayer(this.active_layer);
    },

    light_map: null,
    dark_map: null,
    active_layer: null,

    loadTiles: function(){
        // given tiles are proxies, the amount of connections might be maxed. Loading this last creates a bit more
        // faster design.
        this.active_layer = this.light_map;
        this.active_layer.addTo(this.map);
    },

    // this is an empty tiles layer to make sure markers load. This can be useful for testing so things load faster.
    emptyTiles: function(){
        L.tileLayer("",{}).addTo(this.map);
    },

    // To help you get the coordinates;
    // this might help to find new coordinates: http://ahalota.github.io/Leaflet.CountrySelect/demo.html
    // the map will always fit to bounds after loading the dataset, but at least it shows the right country if the
    // data lodas slow.
    initial_location: function(country_code) {
        // you might want to set the zoomlevel
        // data from: https://worldmap.harvard.edu/data/geonode:country_centroids_az8
        let startpositions = {
                'AD':{"coordinates": [42.54229102, 1.56054378], "zoomlevel":6},
                'AE':{"coordinates": [23.90528188, 54.3001671], "zoomlevel":6},
                'AF':{"coordinates": [33.83523073, 66.00473366], "zoomlevel":6},
                'AG':{"coordinates": [17.2774996, -61.79469343], "zoomlevel":6},
                'AI':{"coordinates": [18.2239595, -63.06498927], "zoomlevel":6},
                'AL':{"coordinates": [41.14244989, 20.04983396], "zoomlevel":6},
                'AM':{"coordinates": [40.28952569, 44.92993276], "zoomlevel":6},
                'AO':{"coordinates": [-12.29336054, 17.53736768], "zoomlevel":6},
                'AQ':{"coordinates": [-80.50857913, 19.92108951], "zoomlevel":6},
                'AR':{"coordinates": [-35.3813488, -65.17980692], "zoomlevel":6},
                'AS':{"coordinates": [-14.30445997, -170.7180258], "zoomlevel":6},
                'AT':{"coordinates": [47.58549439, 14.1264761], "zoomlevel":6},
                'AU':{"coordinates": [-25.73288704, 134.4910001], "zoomlevel":6},
                'AW':{"coordinates": [12.52088038, -69.98267711], "zoomlevel":6},
                'AX':{"coordinates": [60.21488688, 19.95328768], "zoomlevel":6},
                'AZ':{"coordinates": [40.28827235, 47.54599879], "zoomlevel":6},
                'BA':{"coordinates": [44.17450125, 17.76876733], "zoomlevel":6},
                'BB':{"coordinates": [13.18145428, -59.559797], "zoomlevel":6},
                'BD':{"coordinates": [23.86731158, 90.23812743], "zoomlevel":6},
                'BE':{"coordinates": [50.63981576, 4.64065114], "zoomlevel":6},
                'BF':{"coordinates": [12.26953846, -1.75456601], "zoomlevel":6},
                'BG':{"coordinates": [42.76890318, 25.21552909], "zoomlevel":6},
                'BH':{"coordinates": [26.04205135, 50.54196932], "zoomlevel":6},
                'BI':{"coordinates": [-3.35939666, 29.87512156], "zoomlevel":6},
                'BJ':{"coordinates": [9.6417597, 2.32785254], "zoomlevel":6},
                'BL':{"coordinates": [17.89880451, -62.84067779], "zoomlevel":6},
                'BM':{"coordinates": [32.31367802, -64.7545589], "zoomlevel":6},
                'BN':{"coordinates": [4.51968958, 114.7220304], "zoomlevel":6},
                'BO':{"coordinates": [-16.70814787, -64.68538645], "zoomlevel":6},
                'BR':{"coordinates": [-10.78777702, -53.09783113], "zoomlevel":6},
                'BS':{"coordinates": [24.29036702, -76.62843038], "zoomlevel":6},
                'BT':{"coordinates": [27.41106589, 90.40188155], "zoomlevel":6},
                'BW':{"coordinates": [-22.18403213, 23.79853368], "zoomlevel":6},
                'BY':{"coordinates": [53.53131377, 28.03209307], "zoomlevel":6},
                'BZ':{"coordinates": [17.20027509, -88.71010486], "zoomlevel":6},
                'CA':{"coordinates": [61.36206324, -98.30777028], "zoomlevel":6},
                'CD':{"coordinates": [-2.87746289, 23.64396107], "zoomlevel":6},
                'CF':{"coordinates": [6.56823297, 20.46826831], "zoomlevel":6},
                'CG':{"coordinates": [-0.83787463, 15.21965762], "zoomlevel":6},
                'CH':{"coordinates": [46.79785878, 8.20867471], "zoomlevel":6},
                'CI':{"coordinates": [7.6284262, -5.5692157], "zoomlevel":6},
                'CK':{"coordinates": [-21.21927288, -159.7872422], "zoomlevel":6},
                'CL':{"coordinates": [-37.73070989, -71.38256213], "zoomlevel":6},
                'CM':{"coordinates": [5.69109849, 12.73964156], "zoomlevel":6},
                'CN':{"coordinates": [36.56176546, 103.8190735], "zoomlevel":6},
                'CO':{"coordinates": [3.91383431, -73.08114582], "zoomlevel":6},
                'CR':{"coordinates": [9.97634464, -84.19208768], "zoomlevel":6},
                'CU':{"coordinates": [21.62289528, -79.01605384], "zoomlevel":6},
                'CV':{"coordinates": [15.95523324, -23.9598882], "zoomlevel":6},
                'CW':{"coordinates": [12.19551675, -68.97119369], "zoomlevel":6},
                'CY':{"coordinates": [34.91667211, 33.0060022], "zoomlevel":6},
                'CZ':{"coordinates": [49.73341233, 15.31240163], "zoomlevel":6},
                'DE':{"coordinates": [51.10698181, 10.38578051], "zoomlevel":6},
                'DJ':{"coordinates": [11.74871806, 42.5606754], "zoomlevel":6},
                'DK':{"coordinates": [55.98125296, 10.02800992], "zoomlevel":6},
                'DM':{"coordinates": [15.4394702, -61.357726], "zoomlevel":6},
                'DO':{"coordinates": [18.89433082, -70.50568896], "zoomlevel":6},
                'DZ':{"coordinates": [28.15893849, 2.61732301], "zoomlevel":6},
                'EC':{"coordinates": [-1.42381612, -78.75201922], "zoomlevel":6},
                'EE':{"coordinates": [58.67192972, 25.54248537], "zoomlevel":6},
                'EG':{"coordinates": [26.49593311, 29.86190099], "zoomlevel":6},
                'EH':{"coordinates": [24.22956739, -12.21982755], "zoomlevel":6},
                'ER':{"coordinates": [15.36186618, 38.84617011], "zoomlevel":6},
                'ES':{"coordinates": [40.24448698, -3.64755047], "zoomlevel":6},
                'ET':{"coordinates": [8.62278679, 39.60080098], "zoomlevel":6},
                'FI':{"coordinates": [64.49884603, 26.2746656], "zoomlevel":6},
                'FJ':{"coordinates": [-17.42858032, 165.4519543], "zoomlevel":6},
                'FK':{"coordinates": [-51.74483954, -59.35238956], "zoomlevel":6},
                'FM':{"coordinates": [7.45246814, 153.2394379], "zoomlevel":6},
                'FO':{"coordinates": [62.05385403, -6.88095423], "zoomlevel":6},
                'FR':{"coordinates": [42.17344011, -2.76172945], "zoomlevel":6},
                'GA':{"coordinates": [-0.58660025, 11.7886287], "zoomlevel":6},
                'GB':{"coordinates": [54.12387156, -2.86563164], "zoomlevel":6},
                'GD':{"coordinates": [12.11725044, -61.68220189], "zoomlevel":6},
                'GE':{"coordinates": [42.16855755, 43.50780252], "zoomlevel":6},
                'GG':{"coordinates": [49.46809761, -2.57239064], "zoomlevel":6},
                'GH':{"coordinates": [7.95345644, -1.21676566], "zoomlevel":6},
                'GL':{"coordinates": [74.71051289, -41.34191127], "zoomlevel":6},
                'GM':{"coordinates": [13.44965244, -15.39601295], "zoomlevel":6},
                'GN':{"coordinates": [10.43621593, -10.94066612], "zoomlevel":6},
                'GQ':{"coordinates": [1.70555135, 10.34137924], "zoomlevel":6},
                'GR':{"coordinates": [39.07469623, 22.95555794], "zoomlevel":6},
                'GS':{"coordinates": [-54.46488248, -36.43318388], "zoomlevel":6},
                'GT':{"coordinates": [15.69403664, -90.36482009], "zoomlevel":6},
                'GU':{"coordinates": [13.44165626, 144.7679102], "zoomlevel":6},
                'GW':{"coordinates": [12.04744948, -14.94972445], "zoomlevel":6},
                'GY':{"coordinates": [4.79378034, -58.98202459], "zoomlevel":6},
                'HK':{"coordinates": [22.39827737, 114.1138045], "zoomlevel":6},
                'HM':{"coordinates": [-53.08724656, 73.5205171], "zoomlevel":6},
                'HN':{"coordinates": [14.82688165, -86.6151661], "zoomlevel":6},
                'HR':{"coordinates": [45.08047631, 16.40412899], "zoomlevel":6},
                'HT':{"coordinates": [18.93502563, -72.68527509], "zoomlevel":6},
                'HU':{"coordinates": [47.16277506, 19.39559116], "zoomlevel":6},
                'ID':{"coordinates": [-2.21505456, 117.2401137], "zoomlevel":6},
                'IE':{"coordinates": [53.1754487, -8.13793569], "zoomlevel":6},
                'IL':{"coordinates": [31.46110101, 35.00444693], "zoomlevel":6},
                'IM':{"coordinates": [54.22418911, -4.53873952], "zoomlevel":6},
                'IN':{"coordinates": [22.88578212, 79.6119761], "zoomlevel":6},
                'IO':{"coordinates": [-7.33059751, 72.44541229], "zoomlevel":6},
                'IQ':{"coordinates": [33.03970582, 43.74353149], "zoomlevel":6},
                'IR':{"coordinates": [32.57503292, 54.27407004], "zoomlevel":6},
                'IS':{"coordinates": [64.99575386, -18.57396167], "zoomlevel":6},
                'IT':{"coordinates": [42.79662641, 12.07001339], "zoomlevel":6},
                'JE':{"coordinates": [49.21837377, -2.12689938], "zoomlevel":6},
                'JM':{"coordinates": [18.15694878, -77.31482593], "zoomlevel":6},
                'JO':{"coordinates": [31.24579091, 36.77136104], "zoomlevel":6},
                'JP':{"coordinates": [37.59230135, 138.0308956], "zoomlevel":6},
                'KE':{"coordinates": [0.59988022, 37.79593973], "zoomlevel":6},
                'KG':{"coordinates": [41.46221943, 74.54165513], "zoomlevel":6},
                'KH':{"coordinates": [12.72004786, 104.9069433], "zoomlevel":6},
                'KI':{"coordinates": [0.86001503, -45.61110513], "zoomlevel":6},
                'KM':{"coordinates": [-11.87783444, 43.68253968], "zoomlevel":6},
                'KN':{"coordinates": [17.2645995, -62.68755265], "zoomlevel":6},
                'KP':{"coordinates": [40.15350311, 127.1924797], "zoomlevel":6},
                'KR':{"coordinates": [36.38523983, 127.8391609], "zoomlevel":6},
                'KW':{"coordinates": [29.33431262, 47.58700459], "zoomlevel":6},
                'KY':{"coordinates": [19.42896497, -80.91213321], "zoomlevel":6},
                'KZ':{"coordinates": [48.15688067, 67.29149357], "zoomlevel":6},
                'LA':{"coordinates": [18.50217433, 103.7377241], "zoomlevel":6},
                'LB':{"coordinates": [33.92306631, 35.88016072], "zoomlevel":6},
                'LC':{"coordinates": [13.89479481, -60.96969923], "zoomlevel":6},
                'LI':{"coordinates": [47.13665835, 9.53574312], "zoomlevel":6},
                'LK':{"coordinates": [7.61266509, 80.70108238], "zoomlevel":6},
                'LR':{"coordinates": [6.45278492, -9.32207573], "zoomlevel":6},
                'LS':{"coordinates": [-29.58003188, 28.22723131], "zoomlevel":6},
                'LT':{"coordinates": [55.32610984, 23.88719355], "zoomlevel":6},
                'LU':{"coordinates": [49.76725361, 6.07182201], "zoomlevel":6},
                'LV':{"coordinates": [56.85085163, 24.91235983], "zoomlevel":6},
                'LY':{"coordinates": [27.03094495, 18.00866169], "zoomlevel":6},
                'MA':{"coordinates": [29.83762955, -8.45615795], "zoomlevel":6},
                'MC':{"coordinates": [43.75274627, 7.40627677], "zoomlevel":6},
                'MD':{"coordinates": [47.19498804, 28.45673372], "zoomlevel":6},
                'ME':{"coordinates": [42.78890259, 19.23883939], "zoomlevel":6},
                'MF':{"coordinates": [18.08888611, -63.05972851], "zoomlevel":6},
                'MG':{"coordinates": [-19.37189587, 46.70473674], "zoomlevel":6},
                'MH':{"coordinates": [7.00376358, 170.3397612], "zoomlevel":6},
                'MK':{"coordinates": [41.59530893, 21.68211346], "zoomlevel":6},
                'ML':{"coordinates": [17.34581581, -3.54269065], "zoomlevel":6},
                'MM':{"coordinates": [21.18566599, 96.48843321], "zoomlevel":6},
                'MN':{"coordinates": [46.82681544, 103.0529977], "zoomlevel":6},
                'MV':{"coordinates": [3.7287092, 73.45713004], "zoomlevel":6},
                'MO':{"coordinates": [22.22311688, 113.5093212], "zoomlevel":6},
                'MP':{"coordinates": [15.82927563, 145.6196965], "zoomlevel":6},
                'MR':{"coordinates": [20.25736706, -10.34779815], "zoomlevel":6},
                'MS':{"coordinates": [16.73941406, -62.18518546], "zoomlevel":6},
                'MT':{"coordinates": [35.92149632, 14.40523316], "zoomlevel":6},
                'MU':{"coordinates": [-20.27768704, 57.57120551], "zoomlevel":6},
                'MW':{"coordinates": [-13.21808088, 34.28935599], "zoomlevel":6},
                'MX':{"coordinates": [23.94753724, -102.5234517], "zoomlevel":6},
                'MY':{"coordinates": [3.78986846, 109.6976228], "zoomlevel":6},
                'MZ':{"coordinates": [-17.27381643, 35.53367543], "zoomlevel":6},
                'NA':{"coordinates": [-22.13032568, 17.20963567], "zoomlevel":6},
                'NC':{"coordinates": [-21.29991806, 165.6849237], "zoomlevel":6},
                'NE':{"coordinates": [17.41912493, 9.38545882], "zoomlevel":6},
                'NF':{"coordinates": [-29.0514609, 167.9492168], "zoomlevel":6},
                'NG':{"coordinates": [9.59411452, 8.08943895], "zoomlevel":6},
                'NI':{"coordinates": [12.84709429, -85.0305297], "zoomlevel":6},
                'NL':{"coordinates": [52.1007899, 5.28144793], "zoomlevel":8},
                'NO':{"coordinates": [68.75015572, 15.34834656], "zoomlevel":6},
                'NP':{"coordinates": [28.24891365, 83.9158264], "zoomlevel":6},
                'NR':{"coordinates": [-0.51912639, 166.9325682], "zoomlevel":6},
                'NU':{"coordinates": [-19.04945708, -169.8699468], "zoomlevel":6},
                'NZ':{"coordinates": [-41.81113557, 171.4849235], "zoomlevel":6},
                'OM':{"coordinates": [20.60515333, 56.09166155], "zoomlevel":6},
                'PA':{"coordinates": [8.51750797, -80.11915156], "zoomlevel":6},
                'PE':{"coordinates": [-9.15280381, -74.38242685], "zoomlevel":6},
                'PF':{"coordinates": [-14.72227409, -144.9049439], "zoomlevel":6},
                'PG':{"coordinates": [-6.46416646, 145.2074475], "zoomlevel":6},
                'PH':{"coordinates": [11.77536778, 122.8839325], "zoomlevel":6},
                'PK':{"coordinates": [29.9497515, 69.33957937], "zoomlevel":6},
                'PL':{"coordinates": [52.12759564, 19.39012835], "zoomlevel":6},
                'PM':{"coordinates": [46.91918789, -56.30319779], "zoomlevel":6},
                'PN':{"coordinates": [-24.36500535, -128.317042], "zoomlevel":6},
                'PR':{"coordinates": [18.22813055, -66.47307604], "zoomlevel":6},
                'PS':{"coordinates": [31.91613893, 35.19628705], "zoomlevel":6},
                'PT':{"coordinates": [39.59550671, -8.50104361], "zoomlevel":6},
                'PW':{"coordinates": [7.28742784, 134.4080797], "zoomlevel":6},
                'PY':{"coordinates": [-23.22823913, -58.40013703], "zoomlevel":6},
                'QA':{"coordinates": [25.30601188, 51.18479632], "zoomlevel":6},
                'RO':{"coordinates": [45.85243127, 24.97293039], "zoomlevel":6},
                'RS':{"coordinates": [44.2215032, 20.78958334], "zoomlevel":6},
                'RU':{"coordinates": [61.98052209, 96.68656112], "zoomlevel":6},
                'RW':{"coordinates": [-1.99033832, 29.91988515], "zoomlevel":6},
                'SA':{"coordinates": [24.12245841, 44.53686271], "zoomlevel":6},
                'SB':{"coordinates": [-8.92178022, 159.6328767], "zoomlevel":6},
                'SC':{"coordinates": [-4.66099094, 55.47603279], "zoomlevel":6},
                'SD':{"coordinates": [15.99035669, 29.94046812], "zoomlevel":6},
                'SE':{"coordinates": [62.77966519, 16.74558049], "zoomlevel":6},
                'SG':{"coordinates": [1.35876087, 103.8172559], "zoomlevel":6},
                'SH':{"coordinates": [-12.40355951, -9.54779416], "zoomlevel":6},
                'SI':{"coordinates": [46.11554772, 14.80444238], "zoomlevel":6},
                'SK':{"coordinates": [48.70547528, 19.47905218], "zoomlevel":6},
                'SL':{"coordinates": [8.56329593, -11.79271247], "zoomlevel":6},
                'SM':{"coordinates": [43.94186747, 12.45922334], "zoomlevel":6},
                'SN':{"coordinates": [14.36624173, -14.4734924], "zoomlevel":6},
                'SO':{"coordinates": [4.75062876, 45.70714487], "zoomlevel":6},
                'SR':{"coordinates": [4.13055413, -55.9123457], "zoomlevel":6},
                'SS':{"coordinates": [7.30877945, 30.24790002], "zoomlevel":6},
                'ST':{"coordinates": [0.44391445, 6.72429658], "zoomlevel":6},
                'SV':{"coordinates": [13.73943744, -88.87164469], "zoomlevel":6},
                'SX':{"coordinates": [18.05081728, -63.05713363], "zoomlevel":6},
                'SY':{"coordinates": [35.02547389, 38.50788204], "zoomlevel":6},
                'SZ':{"coordinates": [-26.55843045, 31.4819369], "zoomlevel":6},
                'TC':{"coordinates": [21.83047572, -71.97387881], "zoomlevel":6},
                'TD':{"coordinates": [15.33333758, 18.64492513], "zoomlevel":6},
                'TF':{"coordinates": [-49.24895485, 69.22666758], "zoomlevel":6},
                'TG':{"coordinates": [8.52531356, 0.96232845], "zoomlevel":6},
                'TH':{"coordinates": [15.11815794, 101.0028813], "zoomlevel":6},
                'TJ':{"coordinates": [38.5304539, 71.01362631], "zoomlevel":6},
                'TL':{"coordinates": [-8.82889162, 125.8443898], "zoomlevel":6},
                'TM':{"coordinates": [39.11554137, 59.37100021], "zoomlevel":6},
                'TN':{"coordinates": [34.11956246, 9.55288359], "zoomlevel":6},
                'TO':{"coordinates": [-20.42843174, -174.8098734], "zoomlevel":6},
                'TR':{"coordinates": [39.0616029, 35.16895346], "zoomlevel":6},
                'TT':{"coordinates": [10.45733408, -61.26567923], "zoomlevel":6},
                'TW':{"coordinates": [23.7539928, 120.9542728], "zoomlevel":6},
                'TZ':{"coordinates": [-6.27565408, 34.81309981], "zoomlevel":6},
                'UA':{"coordinates": [48.99656673, 31.38326469], "zoomlevel":6},
                'UG':{"coordinates": [1.27469299, 32.36907971], "zoomlevel":6},
                'US':{"coordinates": [45.6795472, -112.4616737], "zoomlevel":6},
                'UY':{"coordinates": [-32.79951534, -56.01807053], "zoomlevel":6},
                'UZ':{"coordinates": [41.75554225, 63.14001528], "zoomlevel":6},
                'VA':{"coordinates": [41.90174985, 12.43387177], "zoomlevel":6},
                'WF':{"coordinates": [-13.88737039, -177.3483483], "zoomlevel":6},
                'WS':{"coordinates": [-13.75324346, -172.1648506], "zoomlevel":6},
                'YE':{"coordinates": [15.90928005, 47.58676189], "zoomlevel":6},
                'ZA':{"coordinates": [-29.00034095, 25.08390093], "zoomlevel":6},
                'ZM':{"coordinates": [-13.45824152, 27.77475946], "zoomlevel":6},
                'ZW':{"coordinates": [-19.00420419, 29.8514412], "zoomlevel":6},
                'VC':{"coordinates": [13.22472269, -61.20129695], "zoomlevel":6},
                'VE':{"coordinates": [7.12422421, -66.18184123], "zoomlevel":6},
                'VG':{"coordinates": [18.52585755, -64.47146992], "zoomlevel":6},
                'VI':{"coordinates": [17.95500624, -64.80301538], "zoomlevel":6},
                'VN':{"coordinates": [16.6460167, 106.299147], "zoomlevel":6},
                'VU':{"coordinates": [-16.22640909, 167.6864464], "zoomlevel":6},
            };

        return startpositions[country_code];
    },

    // where you don't need to access the div again with js:
    add_div: function(html, style, clickable, control_options) {
        new_div = L.control(control_options);
        new_div.onAdd = function () {
            this._div = L.DomUtil.create('div', style);
            this._div.innerHTML = html;
            if (clickable)
                L.DomEvent.disableClickPropagation(this._div);
            return this._div;
        };
        new_div.addTo(this.map);
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
        // console.log(latlng);
        switch (geoJsonPoint.properties.color){
            case "red": return L.circleMarker(latlng, failmap.style(geoJsonPoint));
            case "orange": return L.circleMarker(latlng, failmap.style(geoJsonPoint));
            case "green": return L.circleMarker(latlng, failmap.style(geoJsonPoint));
            case "yellow": return L.circleMarker(latlng, failmap.style(geoJsonPoint));
        }
        return L.circleMarker(latlng, failmap.style(geoJsonPoint));
    },

    highlightFeature: function (e) {
        let layer = e.target;

        // doesn't work for points, only for polygons and lines
        if (typeof layer.setStyle === "function") {
            layer.setStyle({weight: 1, color: '#ccc', dashArray: '0', fillOpacity: 0.7});
            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                layer.bringToFront();
            }
        }
        vueInfo.properties = layer.feature.properties;
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
        if (failmap.isSearchedFor(e.target.feature))
            e.target.setStyle(failmap.searchResultStyle(e.target.feature));
        else
            e.target.setStyle(failmap.style(e.target.feature));
    },

    isSearchedFor: function (feature) {
        x = document.getElementById('searchbar').value;
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
                layer.setStyle(failmap.style(layer.feature));
            });
        } else {
            // text match
            // todo: is there a faster, native search option?
            // todo: how to search in MarkedCluster / give that a different style?
            failmap.polygons.eachLayer(function (layer) {
                if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) === -1) {
                    layer.setStyle(failmap.searchResultStyle(layer.feature));
                } else {
                    layer.setStyle(failmap.style(layer.feature));
                }
            });
            failmap.markers.eachLayer(function (layer) {
                if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) === -1) {
                    layer.setStyle(failmap.searchResultStyle(layer.feature));
                } else {
                    layer.setStyle(failmap.style(layer.feature));
                }
            });
        }
    },

    plotdata: function (mapdata, fitbounds=true) {
        let geodata = failmap.split_point_and_polygons(mapdata);

        // if there is one already, overwrite the attributes...
        if (failmap.polygons.getLayers().length || failmap.markers.getLayers().length) {
            // add all features that are not part of the current map at all
            // and delete the ones that are not in the current set
            failmap.clean_map(geodata.polygons, geodata.points);

            // update existing layers (and add ones with the same name)
            failmap.polygons.eachLayer(function (layer) {failmap.recolormap(mapdata.features, layer)});
            failmap.markers.eachLayer(function (layer) {failmap.recolormap(mapdata.features, layer)});
        } else {
            failmap.add_polygons(geodata.polygons);
            failmap.add_points(geodata.points);
        }

        if (fitbounds)
            failmap.show_everything_on_map();
    },

    show_everything_on_map: function(){
        // determine if we need to pad the map to the left due to controls being visible.
        // they are invisible on small viewports (see css)
        let paddingToLeft = 0;
        if (document.documentElement.clientWidth > 768)
            paddingToLeft=320;

        let bounds = failmap.polygons.getBounds();
        bounds.extend(failmap.markers.getBounds());
        failmap.map.fitBounds(bounds, {paddingTopLeft: [0,0], paddingBottomRight: [paddingToLeft, 0]});
    },

    split_point_and_polygons: function(mapdata){
        // needed because MarkedCluster can only work well with points in our case.

        // mapdata is a mix of polygons and multipolygons, and whatever other geojson types.
        let regions = []; // to polygons
        let points = []; // to markers

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

        return {'polygons': regions, 'points': points}
    },


    add_polygons: function(polygons){
        failmap.polygons = L.geoJson(polygons, {
            style: failmap.style,
            pointToLayer: failmap.pointToLayer,
            onEachFeature: failmap.onEachFeature
        }).addTo(failmap.map);
    },

    add_points: function(points) {
        // Geojson causes confetti to appear, which is great, but doesn't work with multiple organization on the same
        // location. You need something that can show multiple things at once place, such as MarkerCluster.
        // failmap.markers = L.geoJson(points, {
        //     style: failmap.style,
        //     pointToLayer: failmap.pointToLayer,
        //     onEachFeature: failmap.onEachFeature
        // }).addTo(failmap.map);

        points.forEach(function(point){
            // console.log(point);
            pointlayer = failmap.pointToLayer(point, L.latLng(point.geometry.coordinates.reverse()));

            // which of one of these three triggers the bug?
            pointlayer.on({
                mouseover: failmap.highlightFeature,
                mouseout: failmap.resetHighlight,
                click: failmap.showreport
            });

            // allow opening of reports and such in the old way.
            pointlayer.feature = {"properties": point.properties, "geometry": point.geometry};

            failmap.markers.addLayer(pointlayer);
        });
        failmap.map.addLayer(failmap.markers);
    },

    clean_map: function(regions, points) {
        // first version: just delete all points and add them again.
        // we can use the same logic for points and regions now.
        // failmap.markers.clearLayers();
        // failmap.add_points(points);

        failmap.add_new_layers_remove_non_used(points, failmap.markers);
        failmap.add_new_layers_remove_non_used(regions, failmap.polygons);
    },

    add_new_layers_remove_non_used: function(shapeset, target){
        // when there is no data at all, we're done quickly
        if (!shapeset.length) {
            target.clearLayers();
            return;
        }

        // Here we optimize the number of loops if we make a a few simple arrays. We can then do Contains,
        // which is MUCH more optimized than a nested foreach loop. It might even be faster with intersect.
        let shape_names = [];
        let target_names = [];
        shapeset.forEach(function (shape){
            shape_names.push(shape.properties.organization_name)
        });
        target.eachLayer(function (layer){
           target_names.push(layer.feature.properties.organization_name)
        });

        // add layers to the map that are only in the new dataset (new)
        shapeset.forEach(function (shape){
            if (!target_names.includes(shape.properties.organization_name))
                target.addData(shape);
        });

        // remove existing layers that are not in the new dataset
        target.eachLayer(function (layer){
            if (!shape_names.includes(layer.feature.properties.organization_name))
                target.removeLayer(layer);
        });
    },

    // overwrite some properties
    recolormap: function (features, layer) {
        let existing_feature = layer.feature;

        features.forEach(function (new_feature){

            if (existing_feature.properties.organization_name !== new_feature.properties.organization_name) {
                return;
            }
            //if (JSON.stringify(new_feature.geometry.coordinates) !== JSON.stringify(existing_feature.geometry.coordinates)) {
            //if (failmap.evil_json_compare(new_feature.geometry.coordinates, existing_feature.geometry.coordinates)) {
            if (new_feature.geometry.coordinate_id !== existing_feature.geometry.coordinate_id) {
                // Geometry changed, updating shape. Will not fade.
                // It seems not possible to update the geometry of a shape, too bad.
                failmap.polygons.removeLayer(layer);
                failmap.polygons.addData(new_feature);
            } else {
                // colors changed, shapes / points on the map stay the same.
                existing_feature.properties.Overall = new_feature.properties.Overall;
                existing_feature.properties.color = new_feature.properties.color;
                // make the transition
                layer.setStyle(failmap.style(layer.feature));
            }
        });
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