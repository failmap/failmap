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
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="data.total"
                        :axis="['high', 'medium', 'low']"
                        :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_graph"
                    ></vulnerability-chart>
                </div>
            </div>
        </div>
        <div class="row" v-if="data">

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="data.total"
                        :axis="['high']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_graph"
                    ></vulnerability-chart>
                </div>
            </div>

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="data.total"
                        :axis="['medium']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_graph"
                    ></vulnerability-chart>
                </div>
            </div>

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="data.total"
                        :axis="['low']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_graph"
                    ></vulnerability-chart>
                </div>
            </div>

        </div>

        <div class="row" v-if="data">
            <div class="col-md-12">
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
                        <vulnerability-donut
                            :color_scheme="color_scheme"
                            :data="data[issue['name']]"
                            :axis="issue['relevant impacts']"
                            :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_donut"
                        ></vulnerability-donut>
                    </div>
                </div>
                <div class="col-md-6"  v-if="data[issue['name']]">
                    <div class="chart-container" style="position: relative; height:400px; width:100%">
                        <vulnerability-chart
                            :color_scheme="color_scheme"
                            :data="data[issue['name']]"
                            :axis="issue['relevant impacts']"
                            :translation="$i18n.messages[$i18n.locale].graphs.vulnerability_graph"
                        ></vulnerability-chart>
                    </div>
                </div>
            </template>

        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('graphs', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                graphs: {
                    title: "Graphs",
                    overall: "Summed up",

                    vulnerability_graph: {
                        title: "Total amount of issues over time",
                        xAxis_label: "Month",
                        yAxis_label: "Risk",
                        amount_high: "# High Risk",
                        amount_medium: "# Medium Risk",
                        amount_low: "# Low Risk",
                        amount_good: "# Good",
                    },

                    vulnerability_donut: {
                        title: "Today's issue in this category",
                        xAxis_label: "Month",
                        yAxis_label: "Risk",
                        amount_high: "# High Risk",
                        amount_medium: "# Medium Risk",
                        amount_low: "# Low Risk",
                        amount_good: "# Good",
                    },
                },
            },
            nl: {
                graphs: {
                    title: "Grafieken",
                    overall: "Alles bij elkaar",

                    vulnerability_graph: {
                        title: "Totaal aantal risico's over tijd.",
                        xAxis_label: "Maand",
                        yAxis_label: "Risico",
                        amount_high: "# Hoog risico",
                        amount_medium: "# Midden risico",
                        amount_low: "# Laag risico",
                        amount_good: "# Goed",
                    },

                    vulnerability_donut: {
                        title: "Actuele risico's in deze categorie",
                        xAxis_label: "Maand",
                        yAxis_label: "Risico",
                        amount_high: "# Hoog risico",
                        amount_medium: "# Midden risico",
                        amount_low: "# Laag risico",
                        amount_good: "# Goed",
                    },
                }
            }
        },
    },
    template: "#graphs_template",
    mixins: [new_state_mixin, translation_mixin],

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
        color_scheme: Object,
    },

    methods: {
        load: function () {
            fetch(`/data/vulnerability_graphs/${this.state.country}/${this.state.layer}/0`).then(response => response.json()).then(data => {
                this.data = data;
            }).catch((fail) => {console.log('An error occurred in graphs: ' + fail)});
        },
    },
});
</script>
