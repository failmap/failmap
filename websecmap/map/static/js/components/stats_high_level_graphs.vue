{% verbatim %}
<template type="x-template" id="stats_high_level_graphs">
    <div v-cloak class="container">
        <div class="page-header">
            <h2><svg class="svg-inline--fa fa-chart-area fa-w-16" aria-hidden="true" data-prefix="fas" data-icon="chart-area" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M500 384c6.6 0 12 5.4 12 12v40c0 6.6-5.4 12-12 12H12c-6.6 0-12-5.4-12-12V76c0-6.6 5.4-12 12-12h40c6.6 0 12 5.4 12 12v308h436zM372.7 159.5L288 216l-85.3-113.7c-5.1-6.8-15.5-6.3-19.9 1L96 248v104h384l-89.9-187.8c-3.2-6.5-11.4-8.7-17.4-4.7z"></path></svg>
                {{ $t("statistics.title") }}
            </h2>
        </div>

        <loading v-if="loading"></loading>

        <div class="row" v-if="organization_stats.length">

            <div class="col-md-12">
                <h3>{{ $t("statistics.progress_bars.organizations.title") }}</h3>
                <p>{{ $t("statistics.progress_bars.organizations.intro") }}</p>
                <div class="chart-container" style="position: relative; height:300px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="organization_stats"
                        :axis="['high', 'medium', 'good']"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.organization_graph"
                    ></vulnerability-chart>
                </div>
            </div>

        </div>
        <div class="row" v-if="organization_stats.length" style="margin-bottom: 30px;">

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="organization_stats"
                        :axis="['high']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.organization_graph"
                    ></vulnerability-chart>
                </div>
            </div>
            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="organization_stats"
                        :axis="['medium']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.organization_graph"
                    ></vulnerability-chart>
                </div>
            </div>
            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="organization_stats"
                        :axis="['good']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.organization_graph"
                    ></vulnerability-chart>
                </div>
            </div>

        </div>
        <div class="row" v-if="url_stats.length">

            <div class="col-md-12">
                <h3>{{ $t("statistics.progress_bars.internet_addresses.title") }}</h3>
                <p>{{ $t("statistics.progress_bars.internet_addresses.intro") }}</p>
                <div class="chart-container" style="position: relative; height:300px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="url_stats"
                        :axis="['high', 'medium', 'good']"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.internet_graph"
                    ></vulnerability-chart>
                </div>
            </div>

        </div>

        <div class="row" v-if="url_stats.length" style="margin-bottom: 30px;">

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="url_stats"
                        :axis="['high']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.internet_graph"
                    ></vulnerability-chart>
                </div>
            </div>

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="url_stats"
                        :axis="['medium']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.internet_graph"
                    ></vulnerability-chart>
                </div>
            </div>

            <div class="col-md-4">
                <div class="chart-container" style="position: relative; height:200px; width:100%">
                    <vulnerability-chart
                        :color_scheme="color_scheme"
                        :data="url_stats"
                        :axis="['good']"
                        :display_title="false"
                        :display_legend="false"
                        :translation="$i18n.messages[$i18n.locale].statistics.progress_bars.internet_graph"
                    ></vulnerability-chart>
                </div>
            </div>

        </div>
    </div>
</template>
{% endverbatim %}

<script>
const StatsHighLevelGraphs = Vue.component('stats_high_level_graphs', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                statistics: {
                    title: "Extensive statistics",
                    progress_bars: {

                        organizations: {
                            title: "Organizations",
                            intro: "This graph shows the quality of all organizations combined over time, for the maximum of one year. It determines the state by looking at the highest risk issue per organization, in all internet addresses and endpoints. The organization is awarded the grade and color of the highest risk.",
                        },

                        organization_graph: {
                            title: "Total amount and quality of organizations over time.",
                            xAxis_label: "Month",
                            yAxis_label: "Risk",
                            amount_high: "# High Risk",
                            amount_medium: "# Medium Risk",
                            amount_low: "# Low Risk",
                            amount_good: "# Good",
                        },

                        internet_addresses: {
                            title: "Internet addresses",
                            intro: "This graph shows the quality of all urls combined over time, for the maximum of one year. It determines the state by looking at the highest risk issue per url.",
                        },

                        internet_graph: {
                            title: "Total amount and quality of internet addresses over time.",
                            xAxis_label: "Month",
                            yAxis_label: "Risk",
                            amount_high: "# High Risk",
                            amount_medium: "# Medium Risk",
                            amount_low: "# Low Risk",
                            amount_good: "# Good",
                        },

                        when: "When",
                        number: "Number",
                        good: "Good",
                        medium: "Medium",
                        bad: "Bad",
                        unknown: "Unknown",
                    },
                }
            },
            nl: {
                statistics: {
                    title: "Uitgebreide statistieken",
                    progress_bars: {

                        organizations: {
                            title: "Organisaties",
                            intro: "Deze grafiek toont de kwaliteit van alle organizaties over tijd, tot maximaal een jaar geleden. De beoordeling wordt gedaan door te kijken welke bevinding het hoogste risico heeft van alle adressen en endpoints. De organisatie krijgt het oordeel en kleur op basis van het hoogste risico.",
                        },

                        organization_graph: {
                            title: "Totaal aantal en kwaliteit van organisaties over tijd.",
                            xAxis_label: "Maand",
                            yAxis_label: "Risico",
                            amount_high: "# Hoog risico",
                            amount_medium: "# Midden risico",
                            amount_low: "# Laag risico",
                            amount_good: "# Goed",
                        },

                        internet_addresses: {
                            title: "Internet adressen",
                            intro: "Deze grafiek toont de kwaliteit van alle internet adressen (urls) over tijd, tot een maximum van een jaar. Er wordt gekeken wat het hoogste risico is per adres, de kleur en beoordeling hangt daar vanaf.",
                        },

                        internet_graph: {
                            title: "Totaal aantal en kwaliteit internet adressen over tijd.",
                            xAxis_label: "Maand",
                            yAxis_label: "Risico",
                            amount_high: "# Hoog risico",
                            amount_medium: "# Midden risico",
                            amount_low: "# Laag risico",
                            amount_good: "# Goed",
                        },

                        when: "Tijd",
                        number: "Aantal",
                        good: "Goed",
                        medium: "Midden",
                        bad: "Slecht",
                        unknown: "Onbekend",
                    },
                }
            }
        },
    },
    template: "#stats_high_level_graphs",
    mixins: [new_state_mixin, translation_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            data: Array,

            //
            organization_stats: [],
            url_stats: [],

            loading: false,
        }
    },

    props: {
        color_scheme: Object,
    },

    methods: {
        load: function (weeknumber=0) {
            this.loading = true;
            fetch(`/data/stats/${this.state.country}/${this.state.layer}/${weeknumber}`).then(response => response.json()).then(data => {

                // empty
                if (Object.keys(data).length < 1){
                    this.data = [];
                    this.organization_stats= [];
                    this.url_stats = [];
                    return;
                }

                this.data = data;
                this.organization_stats = data.organizations;
                this.url_stats = data.urls;

                this.loading = false;
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail); throw fail});
        },
    },
});
</script>
