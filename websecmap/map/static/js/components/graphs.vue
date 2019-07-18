{% verbatim %}
<template type="x-template" id="graphs_template">
    <div class="stats_part" v-cloak>
        <div class="page-header">
            <h3>{{ $t("graphs.title") }}</h3>
        </div>

        <div class="row" v-if="data">
            <div class="col-md-12">
                <h4>{{ $t("graphs.overall") }}</h4>
                <div class="chart-container" style="position: relative; height:555px; width:100%" v-if="data.total">
                    <vulnerability-chart :color_scheme="color_scheme" :data="data.total" :axis="['high', 'medium', 'low']"></vulnerability-chart>
                </div>
                <div class="chart-container" style="position: relative; height:300px; width:100%" v-if="data.total">
                    <connectivity-chart :color_scheme="color_scheme" :data="data.total"></connectivity-chart>
                </div>
            </div>
        </div>

        <div class="row" v-if="data">

            <template v-for="issue in issues">
                <div class="col-md-12"  v-if="data[issue['name']]" style="text-align: center">
                    <h4 v-html="translate(issue.name)"></h4>
                </div>

                <div class="col-md-6"  v-if="data[issue['name']]" style="margin-bottom: 30px;">
                    <div class="chart-container" style="position: relative; height:400px; width:100%">
                        <vulnerability-donut :color_scheme="color_scheme" :data="data[issue['name']]" :axis="issue['relevant impacts']"></vulnerability-donut>
                    </div>
                </div>
                <div class="col-md-6"  v-if="data[issue['name']]">
                    <div class="chart-container" style="position: relative; height:400px; width:100%">
                        <vulnerability-chart :color_scheme="color_scheme" :data="data[issue['name']]" :axis="issue['relevant impacts']"></vulnerability-chart>
                    </div>
                </div>
            </template>

        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('graphs', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                graphs: {
                    title: "Graphs",
                    overall: "Summed up"

                }
            },
            nl: {
                graphs: {
                    title: "Grafieken",
                    overall: "Alles bij elkaar"
                }
            }
        },
    },
    template: "#graphs_template",
    mixins: [new_state_mixin, translation_mixin, data_loader_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            data: []
        }
    },

    props: {
        issues: Array,
        state: Object,
        color_scheme: Object,
    },

    methods: {
        load: function () {
            fetch(`/data/vulnerability_graphs/${this.state.country}/${this.state.layer}/0`).then(response => response.json()).then(data => {
                this.data = data;
            }).catch((fail) => {console.log('An error occurred: ' + fail)});
        },
    },
});
</script>
