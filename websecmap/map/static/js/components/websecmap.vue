{% verbatim %}
<template type="x-template" id="websecmap_template">

    <!-- :zoom="initial_location(state.country).zoomlevel" -->
    <l-map style="height: calc(100vh - 55px); width: 100%;" ref="lmap"
           :options="{'scrollWheelZoom': false, 'tap': true, 'zoomSnap': 0.2, 'dragging': !L.Browser.mobile, 'touchZoom': true}">

        <l-tile-layer
            :style="'light-v9'"
            :url="this.tile_uri()"
            :token="mapbox_token"
            :max-zoom="18"
            :attribution="'Geography (c) <a href=\'http://openstreetmap.org\'>OpenStreetMap</a> contributors, <a href=\'http://creativecommons.org/licenses/by-sa/2.0/\'>CC-BY-SA</a>, Imagery (c) <a href=\'http://mapbox.com\'>Mapbox</a>, Measurements <a href=\'https://websecuritymap.org/\'>Web Security Map</a> et al <a href=\'http://creativecommons.org/licenses/by-sa/2.0/\'>CC-NC-BY-SA</a>'"
            :visible="true"
            :id="'mapbox.light'"
            :tile-size="512"
            :zoom-offset="-1"
            :options="{'style': 'light-v9', 'accessToken': mapbox_token}"
        ></l-tile-layer>

        <!-- The actual data on the map is manipulated by reference, as there are several complex methods that require
        a lot of thought to rewrite to the new approach. The goal was mainly to have all the controls declarative.
        For example: i have no clue how searching and updating / recoloring and filtering would work otherwise.
        It's probably not too hard, as this entire operation has been a breeze so far. -->
        <!-- <l-geo-json :geojson="polygons"></l-geo-json> -->

        <!-- Including marker-cluster in a 'classic' web project was not easy, and the code doesn't match yet. See above.
         <v-marker-cluster :iconCreateFunction="marker_cluster_iconcreatefunction" :maxClusterRadius="25" ref="clusterRef">
            <v-marker v-for="m in markers" v-if="c.location !== null" :lat-lng="c.latlng">

            </v-marker>
        </v-marker-cluster> -->

        <l-control-scale position="bottomleft" :imperial="true" :metric="true"></l-control-scale>

        <l-control position="topright">
            <div class="info table-light">
                <input id='searchbar' type='text' v-model="searchquery" :placeholder="$t('map.search.placeholder')"/>
            </div>
        </l-control>

        <l-control position="topright">
            <div style="max-width: 300px; overflow:hidden;" class="info table-light">
                <h4>{{ $t("map.history.title") }}</h4>
                <!-- todo: the loader should be placed elsewhere, more visible but not obtrusive, and perhaps WHAT is loading... -->
                <h5>{{ visibleweek }} <span v-if='loading'><div class="loader" style="width: 200px; height: 200px;"></div></span></h5>
                <input id='history' type='range' v-on:change='show_week' :value='state.week' min='0' max='52' step='1' :disabled='loading'/><br />
                <input id='previous_week' type='button' v-on:click='previous_week()' :disabled='loading' :value="'<' + $t('map.history.previous')"/>
                <input id='next_week' type='button' v-on:click='next_week()' :disabled='loading' :value="'>' + $t('map.history.next')"/>
            </div>
        </l-control>

        <l-control position="topright">
            <div style="max-width: 300px; overflow:hidden;" class="info table-light">
                <h4>{{ $t("map.filter.title") }}</h4>
                <template v-if="issues.length > 1">
                    <input type='radio' v-model="displayed_issue" name="displayed_issue" value="" id="clear_filter_option">
                    <label for="clear_filter_option">{{ $t("map.filter.show_everything") }}</label>
                </template>
                <div v-for="issue in issues" style="white-space: nowrap;">
                    <input type='radio' v-model="displayed_issue" name="displayed_issue" :value="issue.name" :id="issue.name">
                    <label :for="issue.name" v-html="translate(issue.name)"></label>
                </div>
            </div>
        </l-control>

        <l-control position="bottomright">
            <div class="info legend table-light">
                <span class='legend_title'>{{ $t("map.legend.title") }}</span><br>
                <i class="map_polygon_good"></i> {{ $t("map.legend.good") }}<br>
                <i class="map_polygon_low"></i> {{ $t("map.legend.low") }}<br>
                <i class="map_polygon_medium"></i> {{ $t("map.legend.mediocre") }}<br>
                <i class="map_polygon_high"></i> {{ $t("map.legend.bad") }}<br>
                <i class="map_polygon_unknown"></i> {{ $t("map.legend.unknown") }}<br>
            </div>
        </l-control>

        <l-control position="topright">
            <div class="info table-light" style='max-width: 300px;' v-if="hover_info.properties.organization_name">

                <div>
                    <h4><a @click="showreport(hover_info.properties.organization_id)">{{ hover_info.properties.organization_name }}</a></h4>
                    <div class="progress">
                        <div class="progress-bar bg-danger" :style="{width:high}"></div>
                        <div class="progress-bar bg-warning" :style="{width:medium}"></div>
                        <div class="progress-bar bg-success" :style="{width:low}"></div>
                        <div class="progress-bar bg-success" :style="{width:perfect}"></div>
                    </div>
                </div>

                <div>
                    <div v-if="domainlist_urls.length > 1">
                        <table width='100%'>
                            <thead>
                                <tr>
                                    <th style='min-width: 20px; width: 20px;'>{{ $t("map.domainlist.high") }}</th>
                                    <th style='min-width: 20px; width: 20px;'>{{ $t("map.domainlist.medium") }}</th>
                                    <th style='min-width: 20px; width: 20px;'>{{ $t("map.domainlist.low") }}</th>
                                    <th>{{ $t("map.domainlist.url") }}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="url in domainlist_urls">
                                    <td><span :class="colorize(url.high, url.medium, url.low)+'_text'">{{ url.high }}</span></td>
                                    <td><span :class="colorize(url.high, url.medium, url.low)+'_text'">{{ url.medium }}</span></td>
                                    <td><span :class="colorize(url.high, url.medium, url.low)+'_text'">{{ url.low }}</span></td>
                                    <td nowrap><span :class="colorize(url.high, url.medium, url.low)+'_text'">{{ url.url }}</span></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>
        </l-control>

        <l-control position="topleft">
            <div>
                <span @click="show_all_map_data()" :title='$t("map.zoombutton")'
                  style='font-size: 1.4em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>🗺️</span>
            </div>
        </l-control>
    </l-map>

</template>
{% endverbatim %}

<script>
Vue.component('websecmap', {
    store,

    name: "websecmap",
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                map: {
                    search: {
                        placeholder: "Search",
                    },
                    history:{
                        title: "Moment",
                        next: '+1 week',
                        previous: '-1 week',
                    },

                    filter: {
                        title: "Filter on issue",
                        show_everything: 'Show all data',
                    },

                    legend: {
                        title: "Legend",
                        good: "Good",
                        low: "Low",
                        mediocre: "Mediocre",
                        bad: "Bad",
                        unknown: "No data available",
                    },

                    domainlist: {
                        high: "H",
                        medium: "M",
                        low: "L",
                        url: "Url",
                    },

                    zoombutton: "Zoom to show all data on this map.",

                }
            },
            nl: {
                map: {

                }
            }
        },
    },
    template: "#websecmap_template",
    mixins: [new_state_mixin, translation_mixin],

    data: function () {
        return {
            // # historyslider
            loading: false,
            week: 0,
            selected_organization: -1,
            features: null,
            proxy_tiles: true,

            // keep track if we need to show everything, or can stay zoomed in:
            previously_loaded_country: null,
            previously_loaded_layer: null,

            displayed_issue: "",

            // things that get rendered on the map
            polygons: L.geoJson(),

            // leafletmarkercluster is not supported for 'old school' approaches like this
            markers: L.markerClusterGroup(
            {
                maxClusterRadius: 25,

                iconCreateFunction: function(cluster){
                    let css_class = "unknown";

                    let childmarkers = cluster.getAllChildMarkers();

                    let selected_severity = 0;

                    // doesn't even need to be an array, as it just matters if the text matches somewhere
                    let searchedfor = false;
                    for (let point of childmarkers) {
                        if (point.options.fillOpacity === 0.7)
                            searchedfor = true;


                        // upgrade severity until you find the highest risk issue.
                        if (map.possibleIconSeverities.indexOf(point.feature.properties.severity) > selected_severity){
                            selected_severity = map.possibleIconSeverities.indexOf(point.feature.properties.severity);
                            css_class = point.feature.properties.severity;
                        }
                    }

                    let classname = searchedfor ? 'marker-cluster marker-cluster-' + css_class : 'marker-cluster marker-cluster-white';

                    return L.divIcon({
                        html: '<div><span>' + cluster.getChildCount() + '</span></div>',
                        className: classname,
                        iconSize: [40, 40] });
                }
            }
        ),

        // domainlist:
        domainlist_urls: [],

        // direct refrence to the leaflet map that is being used to display data.
        // this.$refs.lmap.mapObject
        map: this.$refs,

        possibleIconSeverities: ["unknown", "good", "low", "medium", "high"],

        // search functionality:
        searchquery: "",

        // only show information when the mouse is more than 0.1 second.
        timer: 0,

        // hover_info:
        hover_info: {
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
        }
        }
    },

    props: {
        issues: Array,
        debug: Number,
        mapbox_token: String,

        // Leaflet reference, so we can do things with leaflet directly, as i'm not sure it will be possible differently
        L: Object,
    },

    mounted: function(){

        // https://codingexplained.com/coding/front-end/vue-js/accessing-dom-refs
        this.$nextTick(() => {
            // The whole view is rendered, so I can safely access or query
            // the DOM. ¯\_(ツ)_/¯
            this.map = this.$refs.lmap.mapObject;
            this.load();
        })

    },

    methods: {
        show_all_map_data(){
            // do not roll your own min() or max() over the bounds of these markers. It might wrap
            // around.
            let paddingToLeft = 0;
            if (document.documentElement.clientWidth > 768)
                paddingToLeft=320;

            // todo:
            let bounds = this.polygons.getBounds();
            bounds.extend(this.markers.getBounds());

            if (Object.keys(bounds).length !== 0)
                this.map.fitBounds(bounds, {paddingTopLeft: [0,0], paddingBottomRight: [paddingToLeft, 0]})
        },

        tile_uri: function() {
            // osm: http://{s}.tile.osm.org/{z}/{x}/{y}.png
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
        clear_filter: function (){
            this.displayed_issue = "";
        },
        // slowly moving the map into a vue. NOPE. denied.
        load: function () {
            // todo: make sure that when the app loads, the correct state is available in the app, to reduce complexity
            // we also then don't need a map_default call.

            let url = `/data/map/${this.state.country}/${this.state.layer}/${this.state.week * 7}/${this.displayed_issue}/`;
            fetch(url).then(response => response.json()).then(data => {
                console.log(`Loading websecmap data from: ${url}`);
                this.loading = true;

                // Don't need to zoom out when the filters change, only when the layer/country changes.
                let fitBounds = false;
                if (this.previously_loaded_country !== this.state.country || this.previously_loaded_layer !== this.state.layer)
                    fitBounds = true;

                this.plotdata(data, fitBounds);
                this.previously_loaded_country = this.state.country;
                this.previously_loaded_layer = this.state.layer;

                // make map features (organization data) available to other vues
                // do not update this attribute if an empty list is returned as currently
                // the map does not remove organizations for these kind of responses.
                if (data.features.length > 0) {
                    this.features = data.features;
                }
                this.loading = false;
            }).catch((fail) => {
                console.log('A map loading error occurred: ' + fail);
                // allow you to load again:
                this.loading = false;
            });
        },
        plotdata: function (mapdata, fitbounds=true) {
            let geodata = this.split_point_and_polygons(mapdata);

            // if there is one already, overwrite the attributes...
            if (this.polygons.getLayers().length || this.markers.getLayers().length) {
                // add all features that are not part of the current map at all
                // and delete the ones that are not in the current set
                // the brutal way would be like this, which would not allow transitions:
                // map.markers.clearLayers();
                // map.add_points(points);
                this.add_new_layers_remove_non_used(geodata.points, this.markers, "markers");
                this.add_new_layers_remove_non_used(geodata.polygons, this.polygons, "polygons");

                // update existing layers (and add ones with the same name)
                this.polygons.eachLayer((layer) => {this.recolormap(mapdata.features, layer)});
                this.markers.eachLayer((layer) => {this.recolormap(mapdata.features, layer)});

                // colors could have changed
                this.markers.refreshClusters();
            } else {
                this.add_polygons_to_map(geodata.polygons);
                this.add_points_to_map(geodata.points);
            }

            if (fitbounds)
                this.show_everything_on_map();
        },
        show_everything_on_map: function(){
            // determine if we need to pad the map to the left due to controls being visible.
            // they are invisible on small viewports (see css)
            let paddingToLeft = 0;
            if (document.documentElement.clientWidth > 768)
                paddingToLeft=320;

            let bounds = this.polygons.getBounds();
            bounds.extend(this.markers.getBounds());

            // it could be the map is empty, then there are no bounds, and calling fitbounds would result in an error.
            if (Object.keys(bounds).length !== 0)
                this.map.fitBounds(bounds, {paddingTopLeft: [0,0], paddingBottomRight: [paddingToLeft, 0]});
        },
        recolormap: function (features, layer) {
            let existing_feature = layer.feature;

            features.forEach((new_feature) => {

                if (existing_feature.properties.organization_name !== new_feature.properties.organization_name) {
                    return;
                }
                //if (JSON.stringify(new_feature.geometry.coordinates) !== JSON.stringify(existing_feature.geometry.coordinates)) {
                //if (map.evil_json_compare(new_feature.geometry.coordinates, existing_feature.geometry.coordinates)) {
                if (new_feature.geometry.coordinate_id !== existing_feature.geometry.coordinate_id) {
                    // Geometry changed, updating shape. Will not fade.
                    // It seems not possible to update the geometry of a shape, too bad.
                    this.polygons.removeLayer(layer);
                    this.polygons.addData(new_feature);
                } else {
                    // colors changed, shapes / points on the map stay the same.
                    existing_feature.properties.severity = new_feature.properties.severity;
                    // make the transition
                    layer.setStyle(this.style(layer.feature));
                }
            });
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
        add_new_layers_remove_non_used: function(shapeset, target, layer_type){
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
            shapeset.forEach((shape) => {
                // polygons has addData, but MarkedCluster doesn't. You can't blindly do addlayer on points.
                if (!target_names.includes(shape.properties.organization_name)){
                    if (layer_type === "polygons") {
                        target.addData(shape);
                    } else {
                        this.add_points_to_map([shape]);
                    }
                }

            });

            // remove existing layers that are not in the new dataset, both support removeLayer.
            target.eachLayer(function (layer){
                if (!shape_names.includes(layer.feature.properties.organization_name))
                    target.removeLayer(layer);
            });
        },
        next_week: function () {
            if (this.state.week > 0) {
                store.commit('change', {week: this.state.week -= 1});
            }
        },
        previous_week: function () {
            if (this.state.week <= 52) {
                store.commit('change', {week: this.state.week += 1});
            }
        },
        show_week: function (e) {
            if (e) {
                store.commit('change', {week: parseInt(e.target.value)});
            }

            // nobody understands that when you drag the map slider, the rest
            // of the site and all reports are also old.
            // so don't. Add matching UI elsewhere...

            // todo: this should be state. It also affects reports...
            // if (this.selected_organization > -1) {
            //     this.load_domains(this.selected_organization, this.week);
            // }
        },
        colorize: function (high, medium, low) {
            if (high > 0) return "high";
            if (medium > 0) return "medium";
            return "good";
        },

        highlightFeature: function (e) {
            this.timer = setTimeout(() => {
                let layer = e.target;

                layer.setStyle({weight: 1, color: '#ccc', dashArray: '0', fillOpacity: 0.7});
                if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                    layer.bringToFront();
                }

                this.hover_info.properties = layer.feature.properties;

                url = `/data/report/${this.state.country}/${this.state.layer}/${layer.feature.properties.organization_id}/${this.state.week}`;
                fetch(url).then(response => response.json()).then(data => {
                    this.domainlist_urls = data.calculation["organization"]["urls"];
                }).catch((fail) => {console.log('A domainlist loading error occurred: ' + fail);});

            }, 300);
        },

        // from hover info
        perc: function (amount, total) {
            return (!amount || !total) ? "0%" : this.roundTo(amount / total * 100, 2) + "%";
        },
        // from hover info
        showreport: function(e) {
            // give both name and id as separate identifiers.
            store.commit('change', {reported_organization: {
                id: e.target.feature.properties['organization_id'],
                name: e.target.feature.properties['organization_name'],
            }});
            this.showreport_direct();
        },
        showreport_direct: function () {
            if (this.map.isFullscreen()) {
                console.log("Not yet implemented");
                // var layer = e.target;
                // todo: fix fullscreen view, or drop it completely.
                //vueFullScreenReport.load(organization_id, vueMap.week);
                //vueFullScreenReport.show();

                // Load the report for when you leave fullscreen
                // perhaps this should be in the leave fullscreen event handler
                //vueReport.load(organization_id, vueMap.week);
            } else {
                // trigger load of organization data and jump to Report view.
                // the app should take care about fullscreen things
                location.href = '#report';
            }
        },
        pointToLayer: function (geoJsonPoint, latlng) {
            return L.circleMarker(latlng, this.style(geoJsonPoint));
        },
        add_points_to_map: function(points) {
            // Geojson causes confetti to appear, which is great, but doesn't work with multiple organization on the same
            // location. You need something that can show multiple things at once place, such as MarkerCluster.
            // map.markers = L.geoJson(points, {
            //     style: map.style,
            //     pointToLayer: map.pointToLayer,
            //     onEachFeature: map.onEachFeature
            // }).addTo(map.map);
            self = this;
            points.forEach((point) => {
                // points in geojson are stored in lng,lat. Leaflet wants to show it the other way around.
                // https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem
                let pointlayer = this.pointToLayer(point, L.latLng(point.geometry.coordinates.reverse()));

                pointlayer.on({
                    mouseover: this.highlightFeature,
                    mouseout: this.resetHighlight,
                    click: this.showreport
                });

                // allow opening of reports and such in the old way.
                pointlayer.feature = {"properties": point.properties, "geometry": point.geometry};

                self.markers.addLayer(pointlayer);
            });
            this.map.addLayer(this.markers);
        },
        add_polygons_to_map: function(polygons){
            this.polygons = L.geoJson(polygons, {
                style: this.style,
                pointToLayer: this.pointToLayer,
                onEachFeature: this.onEachFeature
            }).addTo(this.map);
        },
        onEachFeature: function (feature, layer) {
            layer.on({
                mouseover: this.highlightFeature,
                mouseout: this.resetHighlight,
                click: this.showreport
            });
        },
        style: function (feature) {
            return {weight: 1, opacity: 1, color: 'white', dashArray: '0', fillOpacity: 0.7,
                fillColor: this.getColorCode(feature.properties.severity),
                // className: map.a_function_that_makes_the_classname(feature.properties.severity)
            };
        },

        // todo: make dynamic. Get this from the color palette...
        getColorCode: function(d){
            return d === "high" ? '#bd383c' : d === "medium" ? '#fc9645' : d === "low" ? '#d3fc6a' : d === "good" ? '#62fe69' : '#c1bcbb';
        },
        resetHighlight: function (e) {
            clearTimeout(this.timer);

            if (this.isSearchedFor(e.target.feature))
                e.target.setStyle(this.searchResultStyle(e.target.feature));
            else
                e.target.setStyle(this.style(e.target.feature));
        },
        searchResultStyle: function (feature) {
            return {weight: 1, opacity: 1, color: 'white', dashArray: '0', fillOpacity: 0.1};
        },
        isSearchedFor: function (feature) {
            let x = document.getElementById('searchbar').value;
            x = x.toLowerCase();
            if (!x || x === "")
                return false;
            return (feature.properties.organization_name.toLowerCase().indexOf(x) === -1)
        },

        search: function () {
            query = this.searchquery.toLowerCase();
            if ((query === "") || (!query)) {
                // reset
                this.polygons.eachLayer((layer) => {
                    layer.setStyle(this.style(layer.feature));
                });
                this.markers.eachLayer((layer) => {
                    layer.setStyle(this.style(layer.feature));
                });
                this.markers.refreshClusters();
            } else {
                // text match
                // todo: is there a faster, native search option?
                this.polygons.eachLayer((layer) => {
                    if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) === -1) {
                        layer.setStyle(this.searchResultStyle(layer.feature));
                    } else {
                        layer.setStyle(this.style(layer.feature));
                    }
                });
                this.markers.eachLayer((layer) => {
                    if (layer.feature.properties.organization_name.toLowerCase().indexOf(query) === -1) {
                        layer.setStyle(this.searchResultStyle(layer.feature));
                    } else {
                        layer.setStyle(this.style(layer.feature));
                    }
                });

                // check in the clusters if there are any searched for. Is done based on style.
                this.markers.refreshClusters();
            }
        },
        // https://stackoverflow.com/questions/15762768/javascript-math-round-to-two-decimal-places
        roundTo: function(n, digits) {
            if (digits === undefined) {
                digits = 0;
            }

            let multiplicator = Math.pow(10, digits);
            n = parseFloat((n * multiplicator).toFixed(11));
            let test = (Math.round(n) / multiplicator);
            return +(test.toFixed(digits));
        }
    },
    computed: {
        visibleweek: function () {
            let x = new Date();
            x.setDate(x.getDate() - this.week * 7);
            return x.humanTimeStamp();
        },
        high: function () {
            return this.perc(this.hover_info.properties.high_urls, this.hover_info.properties.total_urls);
        },
        medium: function () {
            return this.perc(this.hover_info.properties.medium_urls, this.hover_info.properties.total_urls);
        },
        low: function () {
            return this.perc(this.hover_info.properties.low_urls, this.hover_info.properties.total_urls);
        },
        perfect: function () {
            return this.perc(this.hover_info.properties.total_urls -
                (this.hover_info.properties.low_urls + this.hover_info.properties.medium_urls + this.hover_info.properties.high_urls),
                this.hover_info.properties.total_urls);
        },
        unknown: function () {
            return 0;
        },
        total: function(){
            return this.hover_info.properties.high + this.hover_info.properties.medium + this.hover_info.properties.low;
        },
        organizations: function () {
            if (this.features != null) {
                let organizations = this.features.map(function (feature) {
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
    watch: {
        displayed_issue: function(newsetting, oldsetting){
            this.load(this.week)
        },
        searchquery: function() {
            this.search();
        },
    },
});
</script>
