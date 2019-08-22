{% verbatim %}
<template type="x-template" id="mapstatebar_template">
    <div >

        <nav class="navbar navbar-expand-md navbar-light" id="countrynavbar" v-if="countries.length > 1">
            <div class="container">
                <a class="navbar-brand" href="#">
                <svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="globe" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 496 512" class="svg-inline--fa fa-globe fa-w-16"><path fill="currentColor" d="M336.5 160C322 70.7 287.8 8 248 8s-74 62.7-88.5 152h177zM152 256c0 22.2 1.2 43.5 3.3 64h185.3c2.1-20.5 3.3-41.8 3.3-64s-1.2-43.5-3.3-64H155.3c-2.1 20.5-3.3 41.8-3.3 64zm324.7-96c-28.6-67.9-86.5-120.4-158-141.6 24.4 33.8 41.2 84.7 50 141.6h108zM177.2 18.4C105.8 39.6 47.8 92.1 19.3 160h108c8.7-56.9 25.5-107.8 49.9-141.6zM487.4 192H372.7c2.1 21 3.3 42.5 3.3 64s-1.2 43-3.3 64h114.6c5.5-20.5 8.6-41.8 8.6-64s-3.1-43.5-8.5-64zM120 256c0-21.5 1.2-43 3.3-64H8.6C3.2 212.5 0 233.8 0 256s3.2 43.5 8.6 64h114.6c-2-21-3.2-42.5-3.2-64zm39.5 96c14.5 89.3 48.7 152 88.5 152s74-62.7 88.5-152h-177zm159.3 141.6c71.4-21.2 129.4-73.7 158-141.6h-108c-8.8 56.9-25.6 107.8-50 141.6zM19.3 352c28.6 67.9 86.5 120.4 158 141.6-24.4-33.8-41.2-84.7-50-141.6h-108z" class=""></path></svg>
                {{ $t("mapstatebar.country") }}
                </a>
                <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#countrycollapse" aria-controls="countrycollapse" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="countrycollapse">
                    <ul class="navbar-nav mr-auto">

                        <template v-for="country in countries">
                        <li class="nav-item" :class="[$store.state.country === country.code ? 'selected_country' : '']">
                            <a  class="nav-link" v-on:click="set_country(country.code)">
                                <img :src="country.flag" width="16" height="10">
                                {{ country.name }}</a>
                        </li>
                        </template>

                    </ul>
                </div>
            </div>
        </nav>

        <nav class="navbar navbar-expand-md navbar-light" id="layernavbar" v-if="layers.length > 1" v-cloak>
            <div class="container">
                <a class="navbar-brand" href="#">
                <svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="layer-group" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="svg-inline--fa fa-layer-group fa-w-16"><path fill="currentColor" d="M12.41 148.02l232.94 105.67c6.8 3.09 14.49 3.09 21.29 0l232.94-105.67c16.55-7.51 16.55-32.52 0-40.03L266.65 2.31a25.607 25.607 0 0 0-21.29 0L12.41 107.98c-16.55 7.51-16.55 32.53 0 40.04zm487.18 88.28l-58.09-26.33-161.64 73.27c-7.56 3.43-15.59 5.17-23.86 5.17s-16.29-1.74-23.86-5.17L70.51 209.97l-58.1 26.33c-16.55 7.5-16.55 32.5 0 40l232.94 105.59c6.8 3.08 14.49 3.08 21.29 0L499.59 276.3c16.55-7.5 16.55-32.5 0-40zm0 127.8l-57.87-26.23-161.86 73.37c-7.56 3.43-15.59 5.17-23.86 5.17s-16.29-1.74-23.86-5.17L70.29 337.87 12.41 364.1c-16.55 7.5-16.55 32.5 0 40l232.94 105.59c6.8 3.08 14.49 3.08 21.29 0L499.59 404.1c16.55-7.5 16.55-32.5 0-40z" class=""></path></svg>
                {{ $t("mapstatebar.layer") }}
                </a>
                <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#layercollapse" aria-controls="layercollapse" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>

                <div class="collapse navbar-collapse" id="layercollapse">
                    <ul class="navbar-nav mr-auto">
                        <li class="nav-item" v-for="layer in layers" :class="[$store.state.layer === layer ? 'selected_layer' : '']">
                            <a class="nav-link" v-on:click="set_layer(layer)">
                                {{ $t(layer) }}
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
        </nav>


    </div>
</template>
{% endverbatim %}

<script>
Vue.component('Mapstatebar', {
    store,

    // This is the most important driver for state changes in websecmap.
    // This bar shows all available options and will allow visitors to switch.
    // Instead of translating every country into every language, we use django's content.
    // So this is just non-auto-updating menu... which is much simpler than it was.
    // no dynamic content, but faster load times :)
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                mapstatebar: {
                    country: "Country",
                    layer: "Layer",
                }
            },
            nl: {
                mapstatebar: {
                    country: "Land",
                    layer: "Laag",
                }
            }
        },
    },
    template: "#mapstatebar_template",

    data: function () {
        return {
            // gets set when a country is selected.
            layers: [],
        }
    },

    props: {
        map_configuration: Object,
    },

    methods: {
        load: function(){
            console.log("Load called automatically")

        },

        set_country: function(country_code) {
            // There is always at least one layer for every country.
            this.layers = this.map_configuration[country_code].layers;
            store.commit('change', {layers: this.layers});

            this.selected_country = country_code;

            store.commit('change', {country: country_code, layer: this.layers[0]});

            // remove the current loaded report:
            store.commit('change', {reported_organization: {id: 0, name: ""}});
        },
        set_layer: function(layer_name){
            store.commit('change', {country: this.selected_country, layer: layer_name});

            // remove the current loaded report:
            store.commit('change', {reported_organization: {id: 0, name: ""}});
        },
    },

    computed: {
        countries: function() {
            let available_countries = [];

            // basic dict to list, what would be the generic approach?
            let country_codes = Object.keys(this.map_configuration);
            let self = this;
            country_codes.forEach(function(country_code){
                available_countries.push(self.map_configuration[country_code])
            });

            return available_countries;
        }
    },

    mounted: function() {
        let first = Object.keys(this.map_configuration);
        this.layers = this.map_configuration[first[0]].layers;
        store.commit('change', {layers: this.layers});
        this.selected_country = this.map_configuration[first[0]].code;
    },

});
</script>
