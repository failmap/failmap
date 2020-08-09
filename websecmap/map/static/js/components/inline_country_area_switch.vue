{% verbatim %}
<template type="x-template" id="inline_country_area_switch">
    <div>

        <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#layercollapse" aria-controls="layercollapse" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
        </button>

        <div class="collapse navbar-collapse" id="layercollapse">
            <ul class="navbar-nav mr-auto">

                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle router-link-exact-active" href="#" id="navbarDropdown1" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                        <span>
                            <span v-if="this.countries.length > 1"><img :src="map_configuration[$store.state.country].flag" width="16" height="10"> {{ map_configuration[$store.state.country].name }}, </span>
                            {{ $t($store.state.layer) }}
                        </span>
                        <span class="caret"></span></a>
                    <div class="dropdown-menu" aria-labelledby="navbarDropdown1" style="z-index: 100000">
                        <template v-for="key in Object.keys(map_configuration)">
                            <template v-if="countries.length > 1">
                                <div class="dropdown-divider" v-if="key !== Object.keys(map_configuration)[0]"></div>
                                <a  class="dropdown-item router-link-exact-active" v-on:click="set_country_and_layer(map_configuration[key].code, map_configuration[key].layers[0])">
                                <img :src="map_configuration[key].flag" width="16" height="10">
                                {{ map_configuration[key].name }}</a>
                            </template>

                            <template v-for="layer in map_configuration[key].layers">
                                <a class="dropdown-item" v-on:click="set_country_and_layer(key, layer)">
                                    {{ $t(layer) }}
                                </a>
                            </template>
                        </template>
                    </div>
                </li>
            </ul>
        </div>

    </div>
</template>
{% endverbatim %}

<script>
Vue.component('inline-country-area-switch', {
    store,

    // todo: this code is copied from the navbar and should be deduplicated...

    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                mapstatebar: {
                    country: "Country",
                    layer: "Change",
                    today: "today",
                    data_from: "with data from",
                    data_selection: "Data Selection",
                    map: "Map",
                }
            },
            nl: {
                mapstatebar: {
                    country: "Land",
                    layer: "Gegevens",
                    today: "vandaag",
                    data_from: "met gegevens van",
                    data_selection: "Selecteer gegevens",
                    map: "Kaart",
                }
            }
        },
    },
    template: "#inline_country_area_switch",

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

        set_country_and_layer: function(country_code, layer_name) {
            store.commit('change', {country: country_code, layer: layer_name});
            store.commit('change', {reported_organization: {id: 0, name: ""}});
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
        },
        weeks: function() {

            let objs = [];

            for (let i=0; i<366; i += 7){
                let x = new Date();
                x.setDate(x.getDate() - i);

                if (i === 0)
                    objs.push({'weeks_back': i/7, 'human_date': this.$i18n.t("mapstatebar.today")});
                else
                    objs.push({'weeks_back': i/7, 'human_date': x.humanTimeStamp()});
            }

            return objs;
        },
    },

    mounted: function() {
        let first = Object.keys(this.map_configuration);
        if (first[0] === undefined)
            return;

        // todo: retrieve correctly.
        this.layers = this.map_configuration[first[0]].layers;
        store.commit('change', {layers: this.layers});
        this.selected_country = this.map_configuration[first[0]].code;
    },

});
</script>
