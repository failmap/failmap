{% verbatim %}
<style>
    .map_loading {
        opacity: 60%;
        cursor: wait !important;
    }

    .websecmap a:hover, .websecmap a:active, .websecmap a:visited  {
        text-decoration: none;
        color: black;
    }

</style>
<template type="x-template" id="websecmap_template">
    <div :class="loading ? 'websecmap map_loading' : 'websecmap'" >
        <!-- these settings made the map unusable on mobile devices -->
        <!-- scrollWheelZoom: false, tap: true, zoomSnap: 0.2, dragging: !L.Browser.mobile, touchZoom: true, -->
        <l-map style="height: 100vh; width: 100%;" ref="lmap"
               :options="{
                scrollWheelZoom: false,
                zoomSnap: 0.1,
                contextmenu: true,
                contextmenuWidth: 140,

                // two finger dragging on mobile.
                // see: https://stackoverflow.com/questions/41622980/how-to-customize-touch-interaction-on-leaflet-maps
                dragging: !this.L.Browser.mobile,

                contextmenuItems: [
                {
                    text: 'Show coordinates',
                    callback: this.showCoordinates
                },
                {
                    text: 'Center map here',
                    callback: this.centerMap
                },
                '-',
                {
                    text: 'Zoom in',
                    icon: 'static/images/zoom-in.png',
                    callback: this.zoomIn
                }, {
                    text: 'Zoom out',
                    icon: 'static/images/zoom-out.png',
                    callback: this.zoomOut
                }, {
                    text: 'Show everything',
                    callback: this.show_all_map_data,
                }
                ]}">

            <!-- If you supply invalid parameters, the map will wrap around only to show the US etc. -->
            <!-- Todo: tile layer is mapped as 512 instead of 256. Therefore: Will-change memory consumption is too high. Budget limit is the document surface area multiplied by 3 (686699 px).-->
            <!-- replaced the mapbox gray layer with a colored one, :url="this.tile_uri()", which instantly fixes the tile size bug -->
            <l-tile-layer
                :style="'light-v9'"
                :url="'https://{s}.tile.osm.org/{z}/{x}/{y}.png'"

                :token="mapbox_token"
                :attribution="'Geography and Imagery(c) <a href=\'https://openstreetmap.org\'>OpenStreetMap</a> contributors, <a href=\'http://creativecommons.org/licenses/by-sa/2.0/\'>CC-BY-SA</a>, Map data created with <a href=\'https://websecuritymap.org/\'>Web Security Map</a>.'"

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


            <l-control position="topright" class="search-on-map">
                <div class="info table-light">
                    <input id='searchbar' type='text' v-model="searchquery" :placeholder="$t('map.search.placeholder')"/>
                </div>
            </l-control>


            <!--
            <l-control position="topright" class="hide_on_small_screens">
                <div style="max-width: 300px; overflow:hidden;" class="info table-light">
                    <h4>{{ $t("map.history.title") }} </h4>

                    <template v-if="!loading">
                        <button :disabled='state.week === 52' style='float: left' class='btn btn-small btn-secondary' @click='previous_week' :disabled='loading'>- 1</button>
                        {{ visibleweek }}
                        <button :disabled='state.week === 0' style='float: right' class='btn btn-small btn-secondary' @click='next_week' :disabled='loading'>+1</button>
                        <br>
                        <input id='history' class='slider' type='range' v-on:change='show_week' v-on:input="update_visible_week" :value='state.week' min='0' max='52' step='1' :disabled='loading'/>
                    </template>
                </div>
            </l-control>
            -->

            <l-control position="topright"  v-if="issues.length > 1" class="hide_on_small_screens">
                <div style="max-width: 300px; overflow:hidden;" class="info table-light">
                    <button class="btn btn-secondary btn-small" style='width: 100%' type="button" data-toggle="collapse" data-target="#collapseFilters" aria-expanded="false" aria-controls="collapseExample">
                        <template v-if="['clear_filter_option', ''].includes(displayed_issue)">{{ $t("map.filter.title") }}</template>
                        <template v-if="displayed_issue !== 'clear_filter_option'">
                            <span v-if='loading'><div class="loader" style="width: 24px; height: 24px; float: left;"></div></span>
                            {{ $t(displayed_issue) }}
                        </template>
                    </button>

                    <div class="collapse" id="collapseFilters" style="margin-top:10px;">
                        <template>
                            <input type='radio' v-model="displayed_issue" name="displayed_issue" value="" id="clear_filter_option">
                            <label for="clear_filter_option">{{ $t("map.filter.show_everything") }}</label>
                        </template>
                        <div v-for="issue in issues" style="white-space: nowrap;">
                            <input type='radio' v-model="displayed_issue" name="displayed_issue" :value="issue.name" :id="issue.name">
                            <label :for="issue.name" v-html="translate(issue.name)"></label>
                        </div>
                    </div>
                </div>
            </l-control>

            <l-control position="topright" class="hide_on_small_screens">
                <div class="info table-light" style='max-width: 300px;' v-if="hover_info.properties.organization_name">

                    <div>
                        <h4><router-link :to="'/report/' + hover_info.properties.organization_id">{{ hover_info.properties.organization_name }}</router-link></h4>
                        <router-link :to="'/report/' + hover_info.properties.organization_id">🔍 {{ $t("view_report") }}</router-link><br><br>
                        <div class="progress">
                            <div class="progress-bar bg-danger" :style="{width:high}"></div>
                            <div class="progress-bar bg-warning" :style="{width:medium}"></div>
                            <div class="progress-bar bg-success" :style="{width:low}"></div>
                            <div class="progress-bar bg-success" :style="{width:perfect}"></div>
                        </div>
                    </div>

                    <div>
                        <div v-if="domainlist_urls.length > 0">
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


            <l-control position="bottomright" class="hide_on_small_screens" v-if="simplestats">
                <div style="max-width: 300px; overflow:hidden;" class="info table-light">
                    <!-- Only if there are stats -->
                    <template v-if="simplestats[this.state.country][this.state.layer] !== undefined">
                        <!-- if there are multiple countries -->
                        <template v-if="Object.keys(simplestats).length > 2">
                            <h4><img :src="simplestats[this.state.country][this.state.layer].country_flag" />{{simplestats[this.state.country][this.state.layer].country_name}}, {{ $t($store.state.layer) }}</h4>
                        </template>
                        <template v-else>
                            <h4>{{ $t($store.state.layer) }}</h4>
                        </template>
                        {{simplestats[this.state.country][this.state.layer].organizations}} {{$t('organizations')}}<br>
                        {{simplestats[this.state.country][this.state.layer].urls}} {{$t('internet_adresses')}}<br>
                        {{simplestats[this.state.country][this.state.layer].services}} {{$t('services')}}<br>
                    </template>
                </div>
            </l-control>


            <l-control position="bottomright" class="hide_on_small_screens">
                <div class="info legend table-light">
                    <span class='legend_title'>{{ $t("map.legend.title") }}</span><br>
                    <div style="height: 20px"><i class="map_polygon_good"></i> {{ $t("map.legend.good") }}</div>
                    <div style="height: 20px"><i class="map_polygon_medium"></i> {{ $t("map.legend.mediocre") }}</div>
                    <div style="height: 20px"><i class="map_polygon_high"></i> {{ $t("map.legend.bad") }}</div>
                    <div style="height: 20px"><i class="map_polygon_unknown"></i> {{ $t("map.legend.unknown") }}</div>
                </div>
            </l-control>

            <l-control position="topleft">
                <div>
                    <span @click="show_all_map_data()" :title='$t("map.zoombutton")'
                      style='font-size: 1.4em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>🗺️</span>
                </div>
            </l-control>

            <l-control position="topleft">
                <div>
                    <span @click='start_showing_map_health()' style='margin-top: 34px; font-size: 1.2em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>
                        <template v-if="map_health">
                            <template v-if="map_health['percentage_up_to_date'] === 0">❌</template>
                            <template v-if="map_health['percentage_up_to_date'] > 0 && map_health['percentage_up_to_date'] < 55">🔴</template>
                            <template v-if="map_health['percentage_up_to_date'] > 54 && map_health['percentage_up_to_date'] < 90">🟠</template>
                            <template v-if="map_health['percentage_up_to_date'] > 89 && map_health['percentage_up_to_date'] < 100">🟢</template>
                            <template v-if="map_health['percentage_up_to_date'] === 100">🌈</template>
                        </template>
                    </span>
                </div>
            </l-control>

            <l-control position="topleft" v-if="loading">
                <div style='margin-top: 34px; font-size: 1.4em; background-color: white; border: 2px solid rgba(0,0,0,0.35); border-radius: 4px; padding: 6px; height: 34px; position: absolute; width: 34px; text-align: center; line-height: 1.2;'>
                    <span v-if='loading'><div class="loader" style="width: 18px; height: 18px;"></div></span>
                </div>
            </l-control>
        </l-map>

        <modal v-if="show_map_health" @close="stop_showing_map_health()">
            <h3 slot="header">Map Transparency</h3>

            <div slot="body">
                <p>Map transparency gives insight into how up to date this map is and if there are pending scans scheduled. Data is considered out of date after {{map_health['outdate_period_in_hours']}} hours. Scans of the past 7 days are shown.</p>
                <div class="container">
                  <div class="row">
                    <div class="col-sm">
                        <h4 style="font-size: 1.4em;">Map Health</h4>
                        <table style="width: 100%">
                            <tr><td>Verdict:</td><td>
                                <template v-if="map_health['percentage_up_to_date'] === 0">❌ Obsolete</template>
                                <template v-if="map_health['percentage_up_to_date'] > 0 && map_health['percentage_up_to_date'] < 55">🔴 Outdated</template>
                                <template v-if="map_health['percentage_up_to_date'] > 54 && map_health['percentage_up_to_date'] < 90">🟠 Workable</template>
                                <template v-if="map_health['percentage_up_to_date'] > 89 && map_health['percentage_up_to_date'] < 100">🟢 Usable</template>
                                <template v-if="map_health['percentage_up_to_date'] === 100">🌈 Up to date</template>
                            </td></tr>
                            <tr><td>Up to date:</td><td>{{map_health['percentage_up_to_date']}}% ({{map_health['amount_up_to_date']}})</td></tr>
                            <tr><td>Out of date:</td><td>{{map_health['percentage_out_of_date']}}% ({{map_health['amount_out_of_date']}})</td></tr>
                        </table>

                        <table style="width: 100%">
                            <template v-for="scan in map_health['per_scan']">
                                <tr><td colspan="2"><small>{{ $t(scan['scan_type']) }}</small></td></tr>
                                <tr><td><small>Up to date:</small></td><td><small>{{scan['percentage_up_to_date']}}% ({{scan['amount_up_to_date']}})</small></td></tr>
                                <tr><td><small>Out of date:</small></td><td><small>{{scan['percentage_out_of_date']}}% ({{scan['amount_out_of_date']}})</small></td></tr>
                                <tr></tr>
                            </template>
                        </table>
                    </div>
                    <div class="col-sm">
                      <h4 style="font-size: 1.4em;">Scan Monitor</h4>

                        <table width="100%;">
                        <template v-for="(scanner_value, scanner) in planned_scan_progress">
                            <tr>
                                <td colspan="2"><b>{{ $t(scanner) }}</b></td>
                            </tr>
                            <template v-for="(metrics, scanner_task) in scanner_value">
                                <tr>
                                    <td style="width: 30%;">
                                        <i>{{scanner_task}}</i>
                                    </td><td style="width: 80%;">
                                        <div style="width: 100%; background-color: gray; height: 15px;">
                                            <template v-for="(value, metric) in metrics">
                                                <div v-if='metric === "finished"' :style="'width: ' + Math.floor((value / metrics['total']) * 100) + '%; background-color: darkgreen; color: white; float: left; text-align: center; vertical-align: middle; height: 15px; font-size: 0.7em;'">{{value}}</div>
                                                <div v-if='metric === "requested"' :style="'width: ' + Math.floor((value / metrics['total']) * 100) + '%; background-color: lightgreen; color: white; float: left; text-align: center; vertical-align: middle;  height: 15px;  font-size: 0.7em;'">{{value}}</div>
                                                <div v-if='metric === "picked_up"' :style="'width: ' + Math.floor((value / metrics['total']) * 100) + '%; background-color: orange; color: white; float: left; text-align: center; vertical-align: middle;  height: 15px; font-size: 0.7em;'">{{value}}</div>
                                            </template>
                                        </div>
                                    </td>
                                </tr>
                            </template>
                        </template>
                        </table>

                        <table>
                            <tr><td><div style="height: 15px; width:15px; background-color: darkgreen;">&nbsp;</div></td><td>Scan finished</td></tr>
                            <tr><td><div style="height: 15px; width:15px; background-color: lightgreen;">&nbsp;</div></td><td>Planned</td></tr>
                            <tr><td><div style="height: 15px; width:15px; background-color: orange;">&nbsp;</div></td><td>In progress</td></tr>
                            <tr><td><div style="height: 15px; width:15px; background-color: gray;">&nbsp;</div></td><td>Other (errors, timeouts)</td></tr>
                        </table>

                        <template v-if="authenticated">
                            <button @click="get_planned_scan_progress()">Refresh</button>
                        </template>

                    </div>
                  </div>
                </div>


            </div>
            <div slot="footer">
                <button class="btn btn-primary" @click="stop_showing_map_health()">OK</button>
            </div>
        </modal>

        <modal v-if="show_add_domains" @close="stop_adding_domains()">
            <h3 slot="header">Add Domains...</h3>

            <div slot="body">
                <p>Adding urls to {{clicked_map_object.feature.properties['organization_name']}}.</p>
                <p><i>Note: the urls will be onboarded and scanned afterwards. It will be only be visible when endpoints are found that we understand. The url will only be visible after a new report has been created with aforementioned data. This can take a day.</i></p>
                <server-response :response="add_domains_server_response"></server-response>
                <h4>New domains</h4>
                <textarea style="width: 100%; height: 140px" v-model="new_domains" placeholder="example.com, test.nl, Every domain on a new line, or separated with comma's."></textarea>
            </div>
            <div slot="footer">
                <button type="button" class="btn btn-secondary" @click="stop_adding_domains()">Close</button>
                <button class="btn btn-primary" @click="add_domains()">Add</button>
            </div>
        </modal>
    </div>

</template>
{% endverbatim %}

<script>
const WebSecMap = Vue.component('websecmap', {
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
                        next: '+1',
                        previous: '-1',
                    },

                    filter: {
                        title: "Filter: Show Everything",
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

                    popup: {
                        view_report: "View report",
                        urls: "Urls",
                        services: "Services",
                    }

                }
            },
            nl: {
                map: {
                    search: {
                        placeholder: "Zoeken",
                    },
                    history:{
                        title: "Gegevens van:",
                        next: '+1',
                        previous: '-1',
                    },

                    filter: {
                        title: "Filter: Toon alles",
                        show_everything: 'Toon alles',
                    },

                    legend: {
                        title: "Legenda",
                        good: "Goed",
                        low: "Kleine issues",
                        mediocre: "Matig",
                        bad: "Slecht",
                        unknown: "Geen gegevens beschikbaar",
                    },

                    domainlist: {
                        high: "H",
                        medium: "M",
                        low: "L",
                        url: "Url",
                    },

                    zoombutton: "Toon de hele kaart",

                    popup: {
                        view_report: "Bekijk rapport",
                        urls: "Adressen",
                        services: "Diensten",
                    }
                }
            }
        },
    },
    template: "#websecmap_template",
    mixins: [new_state_mixin, translation_mixin, http_mixin],

    data: function () {
        return {
            // The information shown at the top of the map, live updates when changing the slider.
            visibleweek: "",

            // # adding domains, should be it's own component...
            show_add_domains: false,
            add_domains_server_response: "",
            new_domains: "",

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
                // this better matches the shape of a country
                maxClusterRadius: 25,

                iconCreateFunction: (cluster) => {
                    let css_class = "unknown";

                    let childmarkers = cluster.getAllChildMarkers();

                    let selected_severity = 0;

                    // doesn't even need to be an array, as it just matters if the text matches somewhere
                    let search_active = false;
                    for (let point of childmarkers) {
                        // we can figure this out another way.
                        if (point.options.fillOpacity === 0.7) {
                            search_active = true;
                        }
                    }
                    for (let point of childmarkers) {
                        // upgrade severity until you find the highest risk issue.
                        if (search_active) {
                            // filter down only on items that are actually seached for...
                            if (point.options.fillOpacity === 0.7) {
                                if (this.possibleIconSeverities.indexOf(point.feature.properties.severity) > selected_severity) {
                                    selected_severity = this.possibleIconSeverities.indexOf(point.feature.properties.severity);
                                    css_class = point.feature.properties.severity;
                                }
                            }
                        } else {
                            // do not take in account the possible difference in search results.
                            if (this.possibleIconSeverities.indexOf(point.feature.properties.severity) > selected_severity) {
                                selected_severity = this.possibleIconSeverities.indexOf(point.feature.properties.severity);
                                css_class = point.feature.properties.severity;
                            }
                        }
                    }

                    let classname = search_active ? 'marker-cluster marker-cluster-' + css_class : 'marker-cluster marker-cluster-white';

                    return L.divIcon({
                        html: '<div><span>' + cluster.getChildCount() + '</span></div>',
                        className: classname,
                        iconSize: [40, 40] });
                }
            }),

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

            clicked_map_object: null,

            simplestats: null,

            planned_scan_progress: null,
            planned_scan_progress_interval: null,

            map_health: null,
            show_map_health: false,
        }
    },

    props: {
        issues: Array,
        debug: Boolean,
        mapbox_token: String,
        authenticated: Boolean,

        // Leaflet reference, so we can do things with leaflet directly, as i'm not sure it will be possible differently
        L: Object,

        // the initial data saves a load. This is not very beautiful but it makes the site respond a lot faster.
        initial_map_data: Object,
        initial_layer: String,
        initial_country: String,
    },

    mounted: function(){

        // https://codingexplained.com/coding/front-end/vue-js/accessing-dom-refs
        this.$nextTick(() => {
            // The whole view is rendered, so I can safely access or query
            // the DOM. ¯\_(ツ)_/¯
            this.map = this.$refs.lmap.mapObject;

            // https://github.com/aratcliffe/Leaflet.contextmenu/issues/32
            this.map.on('contextmenu.show', (event) => {
                // alert('swag'); Gets fired twice, once with null...
                if (event.relatedTarget !== undefined)
                    this.clicked_map_object = event.relatedTarget;
            });

            this.load();
            this.update_visible_week();

            this.get_simplestats();
            this.get_planned_scan_progress();
            this.get_map_health();
            this.timer = setInterval(this.get_planned_scan_progress, 30*60*1000)
        })
    },
    beforeDestroy () {
      clearInterval(this.planned_scan_progress_interval)
    },


    methods: {

        start_showing_map_health: function(){
            this.show_map_health = true;
        },

        stop_showing_map_health: function(){
            this.show_map_health = false;
        },

        start_adding_domains: function(){
            this.new_domains = "";
            this.show_add_domains = true;
        },

        stop_adding_domains: function(){
            this.show_add_domains = false;
            this.new_domains = "";
        },

        add_domains: function(){

            let data = {
                organization_id: this.clicked_map_object.feature.properties['organization_id'],
                urls: this.new_domains,
            };

            this.asynchronous_json_post(
                `/data/admin/urls/add/`, data, (server_response) => {
                this.add_domains_server_response = server_response;

                if (server_response.data){
                    this.new_domains = server_response.data.invalid_domains.join(", ");
                }
            });
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
            this.loading = true;

            if (this.initial_layer === this.state.layer && this.initial_country === this.state.country && this.state.week === 0 && this.displayed_issue === ""){
                this.handle_map_data(this.initial_map_data);
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

        get_simplestats: function() {
            fetch(`/data/short_and_simple_stats/${this.state.week}/`).then(response => response.json()).then(data => {
                this.simplestats = data;
            }).catch((fail) => {console.log('A simplestat loading error occurred: ' + fail)});
        },

        get_map_health: function() {
            fetch(`/data/map_health/${this.state.country}/${this.state.layer}/`).then(response => response.json()).then(data => {
                this.map_health = data;
            }).catch((fail) => {console.log('A simplestat loading error occurred: ' + fail)});
        },

        get_planned_scan_progress: function() {

            fetch(`/data/planned_scan_progress/`).then(response => response.json()).then(data => {
                let progress = {}

                // row = {"scanner": "ftp", "activity": "discover", "state": "finished", "amount": 201}
                data.forEach((row) => {
                    if (progress[row['scanner']] === undefined) {
                        progress[row['scanner']] = {}
                    }
                    if (progress[row['scanner']][row['activity']] === undefined) {
                        progress[row['scanner']][row['activity']] = {}
                        progress[row['scanner']][row['activity']]['total'] = 0
                    }
                    if (progress[row['scanner']][row['activity']][row['state']] === undefined) {
                        progress[row['scanner']][row['activity']][row['state']] = {}
                    }


                    progress[row['scanner']][row['activity']][row['state']] = row['amount']
                    progress[row['scanner']][row['activity']]['total'] += row['amount']
                })

                this.planned_scan_progress = progress;
            }).catch((fail) => {console.log('A planned scan process loading error occurred: ' + fail)});
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

            // apply the current search criteria to the new plot
            this.search();

            if (fitbounds)
                this.show_all_map_data();
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

        show_all_map_data(){
            let paddingToLeft = 50;
            if (document.documentElement.clientWidth > 768)
                paddingToLeft=320;

            let bounds = this.polygons.getBounds();
            bounds.extend(this.markers.getBounds());

            if (Object.keys(bounds).length === 0)
                return;

            this.map.fitBounds(bounds, {paddingTopLeft: [50, 50], paddingBottomRight: [paddingToLeft, 50]});
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

                layer.openPopup();

                layer.setStyle({weight: 1, color: '#ccc', dashArray: '0', fillOpacity: 0.7});

                // because of the "bring to front" the timer of this feature is called again. Thus, again after timeout
                // a new timer is started and then again requests a report. It's not really clear why this code is
                // here in the first place. Disabled it until further notice. We don't have overlapping polygons...
                //if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
                //    layer.bringToFront();
                //}

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
            this.set_and_navigate_to_report(
                e.target.feature.properties['organization_id'],
                e.target.feature.properties['organization_name']
            );
        },

        showreportfromcontextmenu: function(e) {
            this.set_and_navigate_to_report(
                this.clicked_map_object.feature.properties['organization_id'],
                this.clicked_map_object.feature.properties['organization_name']
            );
        },

        set_and_navigate_to_report: function(organization_id, organization_name) {
            store.commit('change', {reported_organization: {
                id: organization_id,
                name: organization_name,
            }});
            router.push({ path: '/report' })
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
                let pointlayer = this.pointToLayer(point, L.latLng(point.geometry.coordinates));

                let menuItems = [{
                            text: point.properties['organization_name'],
                            index: 0
                        },
                        {
                            text: "Show report",
                            callback: this.showreportfromcontextmenu,
                            index: 1,
                        }];
                if (this.authenticated){
                    menuItems.push(
                        {
                            separator: true,
                            index: 2
                        },
                        {
                            text: "Add url(s)",
                            callback: this.start_adding_domains,
                            index: 3
                        },
                        {
                            text: "Switch Latitude & Longitude",
                            callback: this.switch_lattitude_and_longitude,
                            index: 4
                        },
                        {
                            separator: true,
                            index: 5
                        })
                } else {
                    menuItems.push({
                            separator: true,
                            index: 2
                        })
                }

                // see geojson data: https://github.com/aratcliffe/Leaflet.contextmenu
                pointlayer.bindContextMenu({
                    contextmenu: true,
                    contextmenuItems: menuItems
                });

                let props = point.properties;

                let popup = L.popup({minWidth: 200});
                popup.setContent(`
                <a onClick="document.app.direct_navigation_to_report(${props.organization_id}, '${props.organization_name}')">
                    <b>${this.determine_book_color(props['percentages'])} ${props['organization_name']}</b><br>
                    🔍 ${ i18n.t("view_report") }
                <br>
                <div class="progress">
                    <div class="progress-bar bg-danger" style="width:${props['percentages']['high_urls']}%"></div>
                    <div class="progress-bar bg-warning" style="width:${props['percentages']['medium_urls']}%"></div>
                    <div class="progress-bar bg-success" style="width:${props['percentages']['low_urls']}%"></div>
                    <div class="progress-bar bg-success" style="width:${props['percentages']['good_urls']}%"></div>
                </div>
                </a>
            `);


                pointlayer.bindPopup(popup).openPopup();

                pointlayer.on({
                    mouseover: this.highlightFeature,
                    mouseout: this.resetHighlight,
                    click: this.highlightFeature,
                    dblclick: this.showreport,
                });

                // allow opening of reports and such in the old way.
                pointlayer.feature = {"properties": point.properties, "geometry": point.geometry};

                self.markers.addLayer(pointlayer);
            });
            this.map.addLayer(this.markers);
        },
        add_polygons_to_map: function(polygons){
            console.log("Adding polygons to map");
            this.polygons = L.geoJson(polygons, {
                style: this.style,
                pointToLayer: this.pointToLayer,
                onEachFeature: this.onEachFeature,
            }).addTo(this.map);
        },
        onEachFeature: function (feature, layer) {

            let menuItems = [{
                        text: layer.feature.properties['organization_name'],
                        index: 0
                    },
                    {
                        text: "Show report",
                        callback: this.showreportfromcontextmenu,
                        index: 1,
                    }];
            if (this.authenticated){
                menuItems.push({
                        text: "Add url(s)",
                        callback: this.start_adding_domains,
                        index: 2
                    },
                    {
                        separator: true,
                        index: 3
                    })
            } else {
                menuItems.push({
                        separator: true,
                        index: 2
                    })
            }

            // see geojson data: https://github.com/aratcliffe/Leaflet.contextmenu
            layer.bindContextMenu({
                contextmenu: true,
                contextmenuItems: menuItems
            });

            let props = layer.feature.properties;

            let popup = L.popup({minWidth: 200});

            popup.setContent(`
                <a onClick="document.app.direct_navigation_to_report(${props.organization_id}, '${props.organization_name}')">
                    <b>${this.determine_book_color(props['percentages'])} ${props['organization_name']}</b><br>
                    🔍 ${ i18n.t("view_report") }
                <br>
                <div class="progress">
                    <div class="progress-bar bg-danger" style="width:${props['percentages']['high_urls']}%"></div>
                    <div class="progress-bar bg-warning" style="width:${props['percentages']['medium_urls']}%"></div>
                    <div class="progress-bar bg-success" style="width:${props['percentages']['low_urls']}%"></div>
                    <div class="progress-bar bg-success" style="width:${props['percentages']['good_urls']}%"></div>
                </div>
                </a>
            `);


            // ${props['total_urls']} ${this.$t('map.popup.urls')}<br>
            // <a onclick="showreport_frompopup(${props['organization_id']}, '${props['organization_name']}')">${this.$t('map.popup.view_report')}</a><br>
            layer.bindPopup(popup).openPopup();

            layer.on({
                mouseover: this.highlightFeature,
                mouseout: this.resetHighlight,
                click: this.highlightFeature,
                dblclick: this.showreport,
            });
        },

        determine_book_color: function(percentages){
            if (percentages['high_urls']) return "📕";
            if (percentages['medium_urls']) return "📙";
            if (percentages['low_urls']) return "📗";
            if (percentages['good_urls']) return "📗";
            return "📓";
        },

        showCoordinates: function(e) {
            alert(e.latlng);
        },
        centerMap:function (e) {
            this.map.panTo(e.latlng);
        },
         zoomIn:function (e) {
            this.map.zoomIn();
        },
        zoomOut: function (e) {
            this.map.zoomOut();
        },

        switch_lattitude_and_longitude: function(){
            let url = `/data/admin/map/switch_lat_lng/${this.clicked_map_object.feature.properties['organization_id']}/`;
            fetch(url).then(response => response.json()).then(data => {
                alert(data.message)
            }).catch((fail) => {
                console.log('A lat long switching error occurred: ' + fail);
                throw fail;
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
            return d === "high" ? '#bd383c' : d === "medium" ? '#fc9645' : d === "low" ? '#62fe69' : d === "good" ? '#62fe69' : '#aaaeae';
        },
        resetHighlight: function (e) {
            clearTimeout(this.timer);

            let query = document.getElementById('searchbar').value;
            if (this.isSearchedFor(e.target.feature, query.toLowerCase()))
                e.target.setStyle(this.searchResultStyle(e.target.feature));
            else
                e.target.setStyle(this.style(e.target.feature));
        },
        searchResultStyle: function (feature) {
            return {weight: 1, opacity: 1, color: 'white', dashArray: '0', fillOpacity: 0.1};
        },
        isSearchedFor: function (feature, query) {
            if (!query || query === "")
                return false;

            if (query.length < 3)
                return (feature.properties.organization_name_lowercase.indexOf(query) === -1);

            return (feature.properties.organization_name_lowercase.indexOf(query) === -1 &&
                    feature.properties.additional_keywords.indexOf(query) === -1);
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
                this.polygons.eachLayer((layer) => {this.handleSearchQuery(layer, query)});
                this.markers.eachLayer((layer) => {this.handleSearchQuery(layer, query)});
                // check in the clusters if there are any searched for. Is done based on style.
                this.markers.refreshClusters();
            }
        },

        handleSearchQuery(layer, query){
            // organization names require one letter, additional properties three: to speed up searching
            if (query.length < 3) {
                if (layer.feature.properties.organization_name_lowercase.indexOf(query) === -1)
                    layer.setStyle(this.searchResultStyle(layer.feature));
                else
                    layer.setStyle(this.style(layer.feature));
            } else {

                if (layer.feature.properties.organization_name_lowercase.indexOf(query) === -1 &&
                    layer.feature.properties.additional_keywords.indexOf(query) === -1)
                    layer.setStyle(this.searchResultStyle(layer.feature));
                else
                    layer.setStyle(this.style(layer.feature));
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
        },

        update_visible_week: function(e){
            let show_week = 0;
            if (!e) {
                show_week = this.state.week;
            } else {
                show_week = parseInt(e.target.value);
            }
            console.log("updating week...");
            let x = new Date();
            x.setDate(x.getDate() - show_week * 7);
            this.visibleweek = x.humanTimeStamp();
        },
    },
    computed: {
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
