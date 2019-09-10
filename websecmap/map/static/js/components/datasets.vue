{% verbatim %}
<template type="x-template" id="datasets_template">
    <div>
        <div class="page-header">
            <a href="#" class="backtomap">{{ $t("back_to_map") }} ↑</a>
            <a name="datasets" class="jumptonav"></a>
            <h2>
                <svg class="svg-inline--fa fa-download fa-w-16" aria-hidden="true" data-prefix="fas" data-icon="download" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M216 0h80c13.3 0 24 10.7 24 24v168h87.7c17.8 0 26.7 21.5 14.1 34.1L269.7 378.3c-7.5 7.5-19.8 7.5-27.3 0L90.1 226.1c-12.6-12.6-3.7-34.1 14.1-34.1H192V24c0-13.3 10.7-24 24-24zm296 376v112c0 13.3-10.7 24-24 24H24c-13.3 0-24-10.7-24-24V376c0-13.3 10.7-24 24-24h146.7l49 49c20.1 20.1 52.5 20.1 72.6 0l49-49H488c13.3 0 24 10.7 24 24zm-124 88c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20zm64 0c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20z"></path></svg>
                {{ $t("datasets.title") }}</h2>

            <p>{{ $t("datasets.intro") }}</p>
        </div>
        <div class="row">
            <div class="col-md-4" v-for="layer in $store.state.layers">
                <table style="width:100%" class="table table-striped" v-if="supported_formats">
                    <thead>
                        <tr>
                            <th colspan="2"><h3>
                                <svg aria-hidden="true" data-prefix="fas" data-icon="chart-pie" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" data-fa-i2svg="" class="svg-inline--fa fa-chart-pie fa-w-18"><path fill="currentColor" d="M288 12.3V240h227.7c6.9 0 12.3-5.8 12-12.7-6.4-122.4-104.5-220.6-227-227-6.9-.3-12.7 5.1-12.7 12zM552.7 288c6.9 0 12.3 5.8 12 12.7-2.8 53.2-23.2 105.6-61.2 147.8-4.6 5.1-12.6 5.4-17.5.5L325 288h227.7zM401 433c4.8 4.8 4.7 12.8-.4 17.3-42.6 38.4-99 61.7-160.8 61.7C107.6 511.9-.2 403.8 0 271.5.2 143.4 100.8 38.9 227.3 32.3c6.9-.4 12.7 5.1 12.7 12V272l161 161z"></path></svg>
                                {{ translate(layer) }}</h3></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <th>
                                <svg aria-hidden="true" data-prefix="fas" data-icon="list-ul" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg="" class="svg-inline--fa fa-list-ul fa-w-16"><path fill="currentColor" d="M96 96c0 26.51-21.49 48-48 48S0 122.51 0 96s21.49-48 48-48 48 21.49 48 48zM48 208c-26.51 0-48 21.49-48 48s21.49 48 48 48 48-21.49 48-48-21.49-48-48-48zm0 160c-26.51 0-48 21.49-48 48s21.49 48 48 48 48-21.49 48-48-21.49-48-48-48zm96-236h352c8.837 0 16-7.163 16-16V76c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16zm0 160h352c8.837 0 16-7.163 16-16v-40c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16zm0 160h352c8.837 0 16-7.163 16-16v-40c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16z"></path></svg>
                                {{ $t("datasets.only_urls") }}</th>
                            <td>⬇️
                                <span v-for="format in supported_formats">
                                    <a :href="create_link(layer, 'urls_only', format)">{{ format }}</a>,
                                </span>
                            </td>
                        </tr><tr>
                            <th>
                                <svg aria-hidden="true" data-prefix="fas" data-icon="list-ul" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg="" class="svg-inline--fa fa-list-ul fa-w-16"><path fill="currentColor" d="M96 96c0 26.51-21.49 48-48 48S0 122.51 0 96s21.49-48 48-48 48 21.49 48 48zM48 208c-26.51 0-48 21.49-48 48s21.49 48 48 48 48-21.49 48-48-21.49-48-48-48zm0 160c-26.51 0-48 21.49-48 48s21.49 48 48 48 48-21.49 48-48-21.49-48-48-48zm96-236h352c8.837 0 16-7.163 16-16V76c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16zm0 160h352c8.837 0 16-7.163 16-16v-40c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16zm0 160h352c8.837 0 16-7.163 16-16v-40c0-8.837-7.163-16-16-16H144c-8.837 0-16 7.163-16 16v40c0 8.837 7.163 16 16 16z"></path></svg>
                                {{ $t("datasets.organization_types") }}*</th>
                            <td>⬇️
                                <span v-for="format in supported_formats">
                                    <a :href="create_link(layer, 'organization_types', format)">{{ format }}</a>,
                                </span>
                            </td>
                        </tr><tr>
                            <th>
                                <svg aria-hidden="true" data-prefix="fas" data-icon="building" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" data-fa-i2svg="" class="svg-inline--fa fa-building fa-w-14"><path fill="currentColor" d="M436 480h-20V24c0-13.255-10.745-24-24-24H56C42.745 0 32 10.745 32 24v456H12c-6.627 0-12 5.373-12 12v20h448v-20c0-6.627-5.373-12-12-12zM128 76c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40c0 6.627-5.373 12-12 12h-40c-6.627 0-12-5.373-12-12V76zm0 96c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40c0 6.627-5.373 12-12 12h-40c-6.627 0-12-5.373-12-12v-40zm52 148h-40c-6.627 0-12-5.373-12-12v-40c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40c0 6.627-5.373 12-12 12zm76 160h-64v-84c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v84zm64-172c0 6.627-5.373 12-12 12h-40c-6.627 0-12-5.373-12-12v-40c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40zm0-96c0 6.627-5.373 12-12 12h-40c-6.627 0-12-5.373-12-12v-40c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40zm0-96c0 6.627-5.373 12-12 12h-40c-6.627 0-12-5.373-12-12V76c0-6.627 5.373-12 12-12h40c6.627 0 12 5.373 12 12v40z"></path></svg>
                                {{ $t("datasets.organizations") }}*</th>
                            <td>⬇️
                                <span v-for="format in supported_formats">
                                    <a :href="create_link(layer, 'organizations', format)">{{ format }}</a>,
                                </span>
                            </td>
                        </tr><tr>
                            <th>
                                <svg class="svg-inline--fa fa-map-marker-alt fa-w-12" aria-hidden="true" data-prefix="fas" data-icon="map-marker-alt" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" data-fa-i2svg=""><path fill="currentColor" d="M172.268 501.67C26.97 291.031 0 269.413 0 192 0 85.961 85.961 0 192 0s192 85.961 192 192c0 77.413-26.97 99.031-172.268 309.67-9.535 13.774-29.93 13.773-39.464 0zM192 272c44.183 0 80-35.817 80-80s-35.817-80-80-80-80 35.817-80 80 35.817 80 80 80z"></path></svg>
                                {{ $t("datasets.map_data") }}*</th>
                            <td>⬇️
                                <span v-for="format in supported_formats">
                                    <a :href="create_link(layer, 'coordinates', format)">{{ format }}</a>,
                                </span>
                        </tr><tr>
                            <th>
                                <svg aria-hidden="true" data-prefix="far" data-icon="compass" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg="" class="svg-inline--fa fa-compass fa-w-16"><path fill="currentColor" d="M256 8C119.033 8 8 119.033 8 256s111.033 248 248 248 248-111.033 248-248S392.967 8 256 8zm0 448c-110.532 0-200-89.451-200-200 0-110.531 89.451-200 200-200 110.532 0 200 89.451 200 200 0 110.532-89.451 200-200 200zm91.326-312.131l-33.359 137.779a24.005 24.005 0 0 1-6.772 11.729l-102.64 97.779c-17.104 16.293-45.56.434-39.88-23.024l33.359-137.779a23.997 23.997 0 0 1 6.772-11.729l102.642-97.779c17.285-16.47 45.494-.175 39.878 23.024zM256 224c-17.673 0-32 14.327-32 32s14.327 32 32 32 32-14.327 32-32-14.327-32-32-32z"></path></svg>
                                {{ $t("datasets.urls") }}*</th>
                            <td>⬇️
                                <span v-for="format in supported_formats">
                                    <a :href="create_link(layer, 'urls', format)">{{ format }}</a>,
                                </span>
                        </tr>

                        <tr v-if="show_comply_or_explain">
                            <th><svg class="svg-inline--fa fa-comments fa-w-18" aria-hidden="true" data-prefix="fas" data-icon="comments" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" data-fa-i2svg=""><path fill="currentColor" d="M416 192c0-88.4-93.1-160-208-160S0 103.6 0 192c0 34.3 14.1 65.9 38 92-13.4 30.2-35.5 54.2-35.8 54.5-2.2 2.3-2.8 5.7-1.5 8.7S4.8 352 8 352c36.6 0 66.9-12.3 88.7-25 32.2 15.7 70.3 25 111.3 25 114.9 0 208-71.6 208-160zm122 220c23.9-26 38-57.7 38-92 0-66.9-53.5-124.2-129.3-148.1.9 6.6 1.3 13.3 1.3 20.1 0 105.9-107.7 192-240 192-10.8 0-21.3-.8-31.7-1.9C207.8 439.6 281.8 480 368 480c41 0 79.1-9.2 111.3-25 21.8 12.7 52.1 25 88.7 25 3.2 0 6.1-1.9 7.3-4.8 1.3-2.9.7-6.3-1.5-8.7-.3-.3-22.4-24.2-35.8-54.5z"></path></svg>
                                {{ $t("datasets.explanations") }}</th>
                            <td>⬇️
                            <span v-for="format in ['json']">
                                <a :href="create_link(layer, 'explains', format)">{{ format }}</a>
                            </span>

                            </td>
                        </tr>

                    </tbody>
                </table>
                <br /><br />
                <p>* = {{ $t("datasets.map_compatibility") }}</p>
            </div>
        </div>
    </div>
</template>
{% endverbatim %}


<script>
Vue.component('datasets', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                datasets: {
                    title: "Datasets",
                    intro: "These datasets contain all data currently displayed on this website. These datasets are suitable for automatic processing and importing in other sites like this.",

                    only_urls: "Only urls",
                    urls: 'Urls',
                    organizations: "Organizations",
                    map_data: "Map data",
                    organization_types: "Organization types",
                    map_compatibility: "These datasets can be imported in another installation of Web Security Map.",
                    explanations: "Comply or explain explanations"
                }
            },
            nl: {
                datasets: {
                    title: "Datasets",
                    intro: "Download de gegevensbundels die worden gebruikt op deze site. Deze bundels zijn geschikt voor automatische verwerking. Zo kunnen bijvoorbeeld beheerders van dit soort sites deze gegevens importeren.",

                    only_urls: "Alleen Domeinnamen",
                    urls: 'Domeinnamen',
                    organizations: "Organisaties",
                    map_data: "Kaartgegevens",
                    organization_types: "Organisatie typen",
                    map_compatibility: "Deze gegevens kunnen worden geimporteerd in een nieuwe installatie van Web Security Map",
                    explanations: "Verklaringen"
                }
            }
        },
    },
    template: "#datasets_template",
    mixins: [new_state_mixin, translation_mixin],

    data: function () {
        return {
            supported_formats: ["json", "csv", "ods", "xlsx", "mediawiki", "latex"]
        }
    },

    props: {
        show_comply_or_explain: Boolean
    },

    methods: {
        load: function(){
            // doesn't have a load method, but is auto called via the state_mixin.
            // values are set via another vue, which is not very nice, but it works...
        },
        create_link: function(layer, linktype, filetype="json"){
            return `/data/export/${linktype}/${this.state.country}/${layer}/${filetype}/`;
        },
    },
});
</script>
