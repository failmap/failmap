{% verbatim %}
<template type="x-template" id="debugmenu_template">
    <div>
        <nav class="navbar navbar-expand-md navbar-light" v-if="config.debug || config.admin">
            <div class="container">
                Debug
                <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#adminbarcollapse" aria-controls="adminbarcollapse" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>
            <div class="collapse navbar-collapse" id="adminbarcollapse">
                <ul class="navbar-nav mr-auto">
                    <li v-if="config.debug" class="nav-item nav-link"><span class='btn btn-danger btn-sm'>{{ $t("menu.debug") }}</span></li>
                </ul>
                <ul class="navbar-nav navbar-right ml-auto" v-if="config.admin">
                    <!-- These are nice to haves... -->
                    <li class="nav-item nav-link"><span class="badge badge-secondary">{{ version }}</span></li>

                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown1" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Management<span class="caret"></span></a>
                        <div class="dropdown-menu" aria-labelledby="navbarDropdown1">
                            <a class="dropdown-item" :href="admin_url">{{ $t("menu.admin") }}</a>
                            <a class="dropdown-item" href="/grafana/">{{ $t("menu.grafana") }}</a>
                            <a class="dropdown-item" href="/flower/">{{ $t("menu.flower") }}</a>
                        </div>
                    </li>

                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown3" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Tools<span class="caret"></span></a>
                        <div class="dropdown-menu" aria-labelledby="navbarDropdown3">
                            <a class="dropdown-item" @click="start_alter_state">{{ $t("menu.alter_state") }}</a>
                            <a class="dropdown-item" @click="start_add_proxies">{{ $t("menu.add_proxies") }}</a>
                        </div>
                    </li>

                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown2" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Theme/Colors (beta)<span class="caret"></span></a>
                        <div class="dropdown-menu" aria-labelledby="navbarDropdown2" style="z-index: 100000">
                            <a @click="$parent.set_color_scheme('trafficlight')" class="dropdown-item">Traffic Light (default)</a>
                            <a @click="$parent.set_color_scheme('deutranopia')" class="dropdown-item">Deutranopia</a>
                            <a @click="$parent.set_color_scheme('pink')" class="dropdown-item">Pink (did you color all?)</a>
                            <a @click="$parent.set_theme('default')" class="dropdown-item">Theme: Default</a>
                            <a @click="$parent.set_theme('darkly')" class="dropdown-item">Theme: Darkly</a>
                        </div>
                    </li>

                </ul>
            </div>
            </div>
        </nav>
        <modal v-if="show_alter_state" @close="stop_alter_state()">
            <h3 slot="header">Alter state</h3>

            <div slot="body">
                <p>You can use this to alter the state of the map beyond what is shown in the menu.</p>
                <h4>Country</h4>
                <input v-model.lazy="$store.state.country">
                <h4>Layer</h4>
                <input v-model.lazy="$store.state.layer">
            </div>
            <div slot="footer">
                <button type="button" class="btn btn-secondary" @click="stop_alter_state()">Close</button>
            </div>
        </modal>
        <modal v-if="show_add_proxies" @close="stop_add_proxies()">
            <h3 slot="header">Add proxies</h3>

            <div slot="body">
                <server-response :response="add_proxies_server_response"></server-response>

                <p>You can add proxies using csv, newline or space separated... or mixed. Make sure that
                    the proxy is HTTPS capable(!). So only HTTPS proxies!</p>
                <p><i>Protip: try to add proxies for your region.
                    And more important: preferably use proxies you exclusively use.</i></p>
                <h4>Proxies</h4>
                <textarea style="width: 100%; height: 240px" v-model="new_proxies" placeholder="1.1.1.1:8000, 2.2.2.2.2:8008, 3.3.3.3:1234..."></textarea>
            </div>
            <div slot="footer">
                <button type="button" class="btn btn-secondary" @click="stop_add_proxies()">Close</button>
                <button class="btn btn-primary" @click="add_proxies()">Add</button>
            </div>
        </modal>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('debugmenu', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                menu: {
                    debug: "debug",
                    admin: "admin",
                    flower: "task monitoring",
                    grafana: "activity monitoring",
                    add_proxies: "Add proxies",
                    monitoring: "monitoring",
                    alter_state: "Alter state",
                }
            },
            nl: {
                menu: {
                    // jokes are allowed
                    debug: "ongediertebestrijdingsmodus",
                }
            }
        },
    },
    template: "#debugmenu_template",
    mixins: [http_mixin],

    data: function () {
        return {
            // # adding domains, should be it's own component...
            show_alter_state: false,

            // add proxies gui:
            show_add_proxies: false,
            add_proxies_server_response: "",
            new_proxies: "",
        }
    },

    methods: {
        start_alter_state: function(){
            this.show_alter_state = true;
        },
        stop_alter_state: function(){
            this.show_alter_state = false;
        },

        start_add_proxies: function(){
            this.new_proxies = "";
            this.show_add_proxies = true;
        },

        stop_add_proxies: function(){
            this.show_add_proxies = false;
            this.new_proxies = "";
        },

        add_proxies: function(){

            let data = {
                proxies: this.new_proxies,
            };

            this.asynchronous_json_post(
                `/data/admin/proxy/add/`, data, (server_response) => {
                this.add_proxies_server_response = server_response;

                if (server_response.data){
                    this.new_proxies = server_response.data.invalid_proxies.join(", ");
                }
            });
        },

    },

    props: {
        config: Object,
        admin_url: String,
        version: String,
    },
});
</script>
