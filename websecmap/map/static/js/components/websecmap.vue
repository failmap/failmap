{% verbatim %}
<template type="x-template" id="websecmap_template">

    <!-- :zoom="initial_location(state.country).zoomlevel" -->
    <l-map style="height: calc(100vh - 55px); width: 100%;" ref="lmap"
           :options="{'scrollWheelZoom': false, 'tap': true, 'zoomSnap': 0.2, 'dragging': !L.Browser.mobile, 'touchZoom': true}"
            :center="initial_location(this.state.country).coordinates" :zoom="initial_location(this.state.country).zoomlevel">

        <!-- If you supply invalid parameters, the map will wrap around only to show the US etc. -->
        <!-- Todo: tile layer is mapped as 512 instead of 256. Therefore: Will-change memory consumption is too high. Budget limit is the document surface area multiplied by 3 (686699 px).-->
        <l-tile-layer
            :style="'light-v9'"
            :url="this.tile_uri()"
            :token="mapbox_token"
            :attribution="'Geography (c) <a href=\'http://openstreetmap.org\'>OpenStreetMap</a> contributors, <a href=\'http://creativecommons.org/licenses/by-sa/2.0/\'>CC-BY-SA</a>, Imagery (c) <a href=\'http://mapbox.com\'>Mapbox</a>, Measurements <a href=\'https://websecuritymap.org/\'>Web Security Map</a> et al <a href=\'http://creativecommons.org/licenses/by-sa/2.0/\'>CC-NC-BY-SA</a>'"

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
                <h4>{{ $t("map.history.title") }} </h4>
                <!-- todo: the loader should be placed elsewhere, more visible but not obtrusive, and perhaps WHAT is loading... -->
                <h5 v-if="!loading">{{ visibleweek }}</h5>
                <h5 v-if="loading"><span v-if='loading'><div class="loader" style="width: 24px; height: 24px;"></div></span></h5>
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
                <div style="height: 20px"><i class="map_polygon_good"></i> {{ $t("map.legend.good") }}</div>
                <div style="height: 20px"><i class="map_polygon_low"></i> {{ $t("map.legend.low") }}</div>
                <div style="height: 20px"><i class="map_polygon_medium"></i> {{ $t("map.legend.mediocre") }}</div>
                <div style="height: 20px"><i class="map_polygon_high"></i> {{ $t("map.legend.bad") }}</div>
                <div style="height: 20px"><i class="map_polygon_unknown"></i> {{ $t("map.legend.unknown") }}</div>
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
        <l-control position="topleft" v-if="loading">
            <div style='margin-top: 34px; font-size: 1.4em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>
                <span v-if='loading'><div class="loader" style="width: 18px; height: 18px;"></div></span>
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
            markers: null,

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
            },

            // this makes the "initial map data" work:
            load_counter: 0,
        }
    },

    props: {
        issues: Array,
        debug: Boolean,
        mapbox_token: String,

        // Leaflet reference, so we can do things with leaflet directly, as i'm not sure it will be possible differently
        L: Object,

        // the initial data saves a load. This is not very beautiful but it makes the site respond a lot faster.
        initial_map_data: Object,
    },

    mounted: function(){

        // https://codingexplained.com/coding/front-end/vue-js/accessing-dom-refs
        this.$nextTick(() => {
            // The whole view is rendered, so I can safely access or query
            // the DOM. ¯\_(ツ)_/¯
            this.map = this.$refs.lmap.mapObject;

            // now that we have a map, we can create an iconcreatefunction

            this.markers = L.markerClusterGroup(
            {
                maxClusterRadius: 25,

                iconCreateFunction: (cluster) => {
                    let css_class = "unknown";

                    let childmarkers = cluster.getAllChildMarkers();

                    let selected_severity = 0;

                    // doesn't even need to be an array, as it just matters if the text matches somewhere
                    let searchedfor = false;
                    for (let point of childmarkers) {
                        if (point.options.fillOpacity === 0.7)
                            searchedfor = true;


                        // upgrade severity until you find the highest risk issue.
                        if (this.map.possibleIconSeverities.indexOf(point.feature.properties.severity) > selected_severity){
                            selected_severity = this.map.possibleIconSeverities.indexOf(point.feature.properties.severity);
                            css_class = point.feature.properties.severity;
                        }
                    }

                    let classname = searchedfor ? 'marker-cluster marker-cluster-' + css_class : 'marker-cluster marker-cluster-white';

                    return L.divIcon({
                        html: '<div><span>' + cluster.getChildCount() + '</span></div>',
                        className: classname,
                        iconSize: [40, 40] });
                }
            });

            this.load();
        })

    },

    methods: {
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
        show_all_map_data(){
            // do not roll your own min() or max() over the bounds of these markers. It might wrap
            // around.
            let paddingToLeft = 0;
            if (document.documentElement.clientWidth > 768)
                paddingToLeft=320;

            // todo:
            let bounds = this.polygons.getBounds();
            bounds.extend(this.markers.getBounds());

            if (Object.keys(bounds).length !== 0) {
                this.map.fitBounds(bounds, {paddingTopLeft: [0, 0], paddingBottomRight: [paddingToLeft, 0]});
                console.log("Fit bounds on all map data");
            }
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

        load: function () {

            if (this.load_counter === 0 && this.initial_map_data !== undefined){
                this.handle_map_data(this.initial_map_data);
                this.load_counter += 1;
                return;
            }

            this.loading = true;
            let url = `/data/map/${this.state.country}/${this.state.layer}/${this.state.week * 7}/${this.displayed_issue}/`;
            console.log(`Loading websecmap data from: ${url}`);
            fetch(url).then(response => response.json()).then(data => {
                this.handle_map_data(data);
            }).catch((fail) => {
                console.log('A map loading error occurred: ' + fail);
                // allow you to load again:
                this.loading = false;
                throw fail;
            });
        },

        handle_map_data: function(data){

            // Don't need to zoom out when the filters change, only when the layer/country changes.
            let fitBounds = false;
            if (this.previously_loaded_country !== this.state.country || this.previously_loaded_layer !== this.state.layer)
                fitBounds = true;
                // this.locationsuggestion();

            this.plotdata(data, fitBounds);
            this.previously_loaded_country = this.state.country;
            this.previously_loaded_layer = this.state.layer;

            // make map features (organization data) available to other vues
            // do not update this attribute if an empty list is returned as currently
            // the map does not remove organizations for these kind of responses.
            if (data.features.length > 0) {
                this.features = data.features;
            }

            // update organizations for use in select box:
            let organizations = [];
            data.features.forEach((feature) => {
                let props = feature.properties;
                organizations.push({
                    id: props.organization_id,
                    name: props.organization_name,
                    slug: props.organization_slug,
                    high: props.high,
                    medium: props.medium,
                    low: props.low,
                    total_urls: props.total_urls,
                    data_from: props.data_from,
                    severity: props.severity,
                })
            });

            this.loading = false;

            store.commit('change', {organizations: organizations});
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

        locationsuggestion: function (){
            // should be a suggestion like: "you are here", do you want to see the things for [$location] or the region
            // when there are multiple markers...
            // todo: this works best on polygon layers, it does not work on markers,
            // as there might be 100 markers. It DOes however could zoom to where you are...
            console.log("Suggesting location... ");
            this.map.on('locationerror', this.onLocationError);
            this.map.on('locationfound', this.onLocationFound);
            this.map.locate({setView: true, maxZoom: 16});
        },

        onLocationFound: (e) => {
            var radius = e.accuracy;

            // figure out in the geojson where you are...

            L.marker(e.latlng).addTo(map)
                .bindPopup("You are within " + radius + " meters from this point").openPopup();

            L.circle(e.latlng, radius).addTo(map);
        },

        onLocationError: (e) => {
            console.log(e.message);
        },

        show_everything_on_map: function(){
            console.log("Show everything on map.");

            // determine if we need to pad the map to the left due to controls being visible.
            // they are invisible on small viewports (see css)
            let paddingToLeft = 0;
            if (document.documentElement.clientWidth > 768) {
                paddingToLeft = 320;
            }

            let bounds = this.polygons.getBounds();
            bounds.extend(this.markers.getBounds());

            // it could be the map is empty, then there are no bounds, and calling fitbounds would result in an error.
            if (Object.keys(bounds).length !== 0) {
                this.map.fitBounds(bounds, {paddingTopLeft: [0, 0], paddingBottomRight: [paddingToLeft, 0]});
            }
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
            // fullscreen state is not supported for now...
            location.href = '#report';
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
