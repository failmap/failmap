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
                    <li class="nav-item"><a class="nav-link" :href="admin_url">{{ $t("menu.admin") }}</a></li>
                    <li class="nav-item"><a class="nav-link" href="/grafana/">{{ $t("menu.monitoring") }}</a></li>
                    <li class="nav-item"><a class="nav-link" onclick="">{{ $t("menu.load_tiles") }}</a></li>
                    <li class="nav-item"><a class="nav-link" @click="start_alter_state">{{ $t("menu.alter_state") }}</a></li>
                    <!-- This allows testing different themes -->
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown2" role="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Theme<span class="caret"></span></a>
                        <div class="dropdown-menu" aria-labelledby="navbarDropdown3">
                            <a href="#" data-theme="default" class="dropdown-item theme-link">Default</a>
                            <a href="#" data-theme="darkly" class="dropdown-item theme-link">Darkly</a>
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
                    monitoring: "monitoring",
                    load_tiles: "load tiles",
                    alter_state: "alter state",
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

    data: function () {
        return {
            // # adding domains, should be it's own component...
            show_alter_state: false,
        }
    },

    methods: {
        start_alter_state: function(){
            this.show_alter_state = true;
        },
        stop_alter_state: function(){
            this.show_alter_state = false;
        }

    },

    props: {
        config: Object,
        admin_url: String,
        version: String,
    },
});
</script>
