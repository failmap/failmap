{% verbatim %}
<template type="x-template" id="mapstatebar_template">
    <div >
    {% if number_of_countries > 1 %}
        <nav class="navbar navbar-expand-md navbar-light" id="countrynavbar">
            <div class="container">
                <a class="navbar-brand" href="#">
                <svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="globe" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 496 512" class="svg-inline--fa fa-globe fa-w-16"><path fill="currentColor" d="M336.5 160C322 70.7 287.8 8 248 8s-74 62.7-88.5 152h177zM152 256c0 22.2 1.2 43.5 3.3 64h185.3c2.1-20.5 3.3-41.8 3.3-64s-1.2-43.5-3.3-64H155.3c-2.1 20.5-3.3 41.8-3.3 64zm324.7-96c-28.6-67.9-86.5-120.4-158-141.6 24.4 33.8 41.2 84.7 50 141.6h108zM177.2 18.4C105.8 39.6 47.8 92.1 19.3 160h108c8.7-56.9 25.5-107.8 49.9-141.6zM487.4 192H372.7c2.1 21 3.3 42.5 3.3 64s-1.2 43-3.3 64h114.6c5.5-20.5 8.6-41.8 8.6-64s-3.1-43.5-8.5-64zM120 256c0-21.5 1.2-43 3.3-64H8.6C3.2 212.5 0 233.8 0 256s3.2 43.5 8.6 64h114.6c-2-21-3.2-42.5-3.2-64zm39.5 96c14.5 89.3 48.7 152 88.5 152s74-62.7 88.5-152h-177zm159.3 141.6c71.4-21.2 129.4-73.7 158-141.6h-108c-8.8 56.9-25.6 107.8-50 141.6zM19.3 352c28.6 67.9 86.5 120.4 158 141.6-24.4-33.8-41.2-84.7-50-141.6h-108z" class=""></path></svg>
                {% trans "Countries" %}
                </a>
                <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#countrycollapse" aria-controls="countrycollapse" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="countrycollapse">
                    <ul class="navbar-nav mr-auto">

                        {% for country in initial_countries %}
                            {% get_country country as country_details %}
                        <li class="nav-item" v-bind:class="[selected_country == '{{ country_details.code }}' ? 'selected_country' : '']">
                            <a  class="nav-link" v-on:click="set_country('{{ country_details.code }}')">
                                <img src="{{ country_details.flag }}" width="16" height="10">
                                {{ country_details.name }}</a>
                        </li>

                        {% endfor %}

                    </ul>
                </div>
            </div>
        </nav>
        {% endif %}

        <nav class="navbar navbar-expand-md navbar-light" id="layernavbar" v-if="layers.length > 1" v-cloak>
            <div class="container">
                <a class="navbar-brand" href="#">
                <svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="layer-group" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="svg-inline--fa fa-layer-group fa-w-16"><path fill="currentColor" d="M12.41 148.02l232.94 105.67c6.8 3.09 14.49 3.09 21.29 0l232.94-105.67c16.55-7.51 16.55-32.52 0-40.03L266.65 2.31a25.607 25.607 0 0 0-21.29 0L12.41 107.98c-16.55 7.51-16.55 32.53 0 40.04zm487.18 88.28l-58.09-26.33-161.64 73.27c-7.56 3.43-15.59 5.17-23.86 5.17s-16.29-1.74-23.86-5.17L70.51 209.97l-58.1 26.33c-16.55 7.5-16.55 32.5 0 40l232.94 105.59c6.8 3.08 14.49 3.08 21.29 0L499.59 276.3c16.55-7.5 16.55-32.5 0-40zm0 127.8l-57.87-26.23-161.86 73.37c-7.56 3.43-15.59 5.17-23.86 5.17s-16.29-1.74-23.86-5.17L70.29 337.87 12.41 364.1c-16.55 7.5-16.55 32.5 0 40l232.94 105.59c6.8 3.08 14.49 3.08 21.29 0L499.59 404.1c16.55-7.5 16.55-32.5 0-40z" class=""></path></svg>
                {% trans "Layers" %}
                </a>
                <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#layercollapse" aria-controls="layercollapse" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>

                <div class="collapse navbar-collapse" id="layercollapse">
                    <ul class="navbar-nav mr-auto">
                        <li class="nav-item" v-for="(x, key) in layers" v-bind:class="[selected_layer == x ? 'selected_layer' : '']">
                            <a class="nav-link" v-on:click="set_layer(x)">
                                {% verbatim %}{{ translate("category_menu_" + x) }}{% endverbatim %}
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
Vue.component('mapstatebar', {
    // This is the most important driver for state changes in websecmap.
    // This bar shows all available options and will allow visitors to switch.
    // Instead of translating every country into every language, we use django's content.
    // So this is just non-auto-updating menu... which is much simpler than it was.
    // no dynamic content, but faster load times :)

    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                mapstatebar: {

                }
            },
            nl: {
                mapstatebar: {

                }
            }
        },
    },
    template: "#mapstatebar_template",
    mixins: [new_state_mixin, translation_mixin],

    data: function () {
        return {
            scans: {}
        }
    },

    props: {
        state: Object,
        map_configuration: Object,
    },

    methods: {
        load: function(){},

        
    },
});



// merged layer and country navbars to have a single point of setting the state at startup.
    window.vueMapStateBar = new Vue({
        name: "MapStateBar",
        mixins: [translation_mixin],
        el: '#map_state_bar',

        data: {
            layers: [""],
            countries: [""],
            selected_layer: "",
            selected_country: "",
        },

        mounted: function() {
            this.get_defaults();
        },

        // todo: load the map without parameters should result in the default settings to save a round trip.
        methods: {
            get_defaults: function() {
                fetch('/data/defaults/').then(response => response.json()).then(data => {
                    this.selected_layer = data.layer;
                    this.selected_country = data.country;
                    // countries are already loaded in the django template for faster menus
                    // then load this as fast as you can.
                    this.get_layers();
                    app.set_state(this.selected_country, this.selected_layer);
                }).catch((fail) => {console.log('An error occurred in mapstatebar: ' + fail)});
            },
            get_countries: function() {
                fetch('/data/countries/').then(response => response.json()).then(countries => {
                    // it's fine to clear the navbar if there are no layers for this country
                    this.countries = countries;

                    // this is async, therefore you cannot call countries and then layers. You can only do while...
                    this.get_layers();
                }).catch((fail) => {console.log('An error occurred in get_countries: ' + fail)});
            },
            get_layers: function() {
                fetch('/data/layers/' + this.selected_country + '/').then(response => response.json()).then(layers => {
                    // it's fine to clear the navbar if there are no layers for this country
                    this.layers = layers;
                    app.layers = layers;  // todo: Move this to app... so layers will be reactive.
                });
            },
            set_country: function(country_name) {
                // when changing the country, a new set of layers will appear.
                this.selected_country = country_name;

                // the first layer of the country is the default. Load the map and set that one.
                fetch('/data/layers/' + this.selected_country + '/').then(response => response.json()).then(layers => {
                    // yes, there are layers.
                    if (layers.length) {
                        this.layers = layers;
                        this.selected_layer = layers[0];
                        app.set_state(this.selected_country, this.selected_layer);
                    } else {
                        this.layers = [""];
                        app.set_state(this.selected_country, this.selected_layer);
                    }
                });
            },
            set_layer: function(layer_name){
                this.selected_layer = layer_name;
                app.set_state(this.selected_country, this.selected_layer);
            },
            load: function() {
                console.log("Load function of mapstatebar called, but why?")
            }
        }
    });
</script>
