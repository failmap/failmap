{% verbatim %}
<template type="x-template" id="combined_number_statistics_template">
    <div v-cloak>
        <div class="page-header">
            <h2><svg class="svg-inline--fa fa-chart-area fa-w-16" aria-hidden="true" data-prefix="fas" data-icon="chart-area" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M500 384c6.6 0 12 5.4 12 12v40c0 6.6-5.4 12-12 12H12c-6.6 0-12-5.4-12-12V76c0-6.6 5.4-12 12-12h40c6.6 0 12 5.4 12 12v308h436zM372.7 159.5L288 216l-85.3-113.7c-5.1-6.8-15.5-6.3-19.9 1L96 248v104h384l-89.9-187.8c-3.2-6.5-11.4-8.7-17.4-4.7z"></path></svg>
                {{ $t("statistics.title") }}
            </h2>
        </div>
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

        <div class="row" v-if="Object.keys(explained).length && issue_categories.includes('integrity') || issue_categories.includes('website')">
            <div class="col-md-6" v-if="issue_categories.includes('integrity')">
                <h4>{{ $t("statistics.numbers.integrity_and_confidentiality.title") }}</h4>
                <p>{{ $t("statistics.numbers.integrity_and_confidentiality.intro") }}</p>
            </div>
            <div class="col-md-6" v-if="issue_categories.includes('website')">
                <h4>{{ $t("statistics.numbers.website_content_security.title") }}</h4>
                <p>{{ $t("statistics.numbers.website_content_security.intro") }}</p>
            </div>
        </div>
        <div class="row" v-if="Object.keys(explained).length && (issue_categories.includes('integrity') || issue_categories.includes('website'))">
            <div class="col-md-6">
                <div>
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                            <tr>
                                <th width="10%">{{ $t("statistics.numbers.technology") }}</th>
                                <th width="50%">{{ $t("statistics.numbers.result") }}</th>
                                <th width="40%">{{ $t("statistics.numbers.total") }}</th>
                            </tr>
                            </thead>
                            <tbody v-for="issue in issues" v-if="issue.category.includes('integrity') && Object.keys(explained).includes(issue.name)">
                                <tr>
                                    <td colspan="3" v-html="translate(issue['name'])"></td>
                                </tr>
                                <tr class="highrow" v-for="grade in issue.statistics.bad">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="mediumrow" v-for="grade in issue.statistics.medium">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="goodrow" v-for="grade in issue.statistics.good">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div>
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                            <tr>
                                <th width="10%">{{ $t("statistics.numbers.technology") }}</th>
                                <th width="50%">{{ $t("statistics.numbers.result") }}</th>
                                <th width="40%">{{ $t("statistics.numbers.total") }}</th>
                            </tr>
                            </thead>
                            <tbody v-for="issue in issues" v-if="issue.category.includes('website') && Object.keys(explained).includes(issue.name)">
                                <tr>
                                    <td colspan="3" v-html="translate(issue['name'])"></td>
                                </tr>
                                <tr class="highrow" v-for="grade in issue.statistics.bad">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="mediumrow" v-for="grade in issue.statistics.medium">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="goodrow" v-for="grade in issue.statistics.good">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ explained[issue.name][grade.explanation] }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="row" v-if="show_services && filteredData.length">
            <div class="col-md-12">
                <h3>{{ $t("statistics.services.title") }}</h3>
                <p>{{ $t("statistics.services.intro") }}</p>
                    <p>{{ $t("statistics.services.number_of_service_checked", [endpoints_now]) }}</p>
                    <div class="table-responsive">
                        <table class="table table-striped" id="services_table">
                            <thead>
                                <tr>
                                    <th @click="sortBy('ip_version')" :class="{ active: sortKey === 'ip_version' }">
                                        {{ $t("statistics.services.ip_version") }}
                                        <span class="arrow" :class="sortOrders['ip_version'] > 0 ? 'asc' : 'dsc'"></span>
                                    </th>
                                    <th @click="sortBy('protocol')" :class="{ active: sortKey === 'protocol' }">
                                        {{ $t("statistics.services.protocol") }}
                                        <span class="arrow" :class="sortOrders['protocol'] > 0 ? 'asc' : 'dsc'"></span>
                                    </th>
                                    <th @click="sortBy('port')" :class="{ active: sortKey === 'port' }">
                                        {{ $t("statistics.services.port") }}
                                        <span class="arrow" :class="sortOrders['port'] > 0 ? 'asc' : 'dsc'"></span>
                                    </th>
                                    <th @click="sortBy('amount')" :class="{ active: sortKey === 'amount' }">
                                        {{ $t("statistics.services.amount") }}
                                        <span class="arrow" :class="sortOrders['amount'] > 0 ? 'asc' : 'dsc'"></span>
                                    </th>
                                    <th>{{ $t("statistics.services.percentage") }}</th>
                                </tr>
                            </thead>
                            <tbody>

                                <tr v-for="service in filteredData">
                                    <td>{{ service['ip_version'] }}</td>
                                    <td>{{ service['protocol'] }}</td>
                                    <td>{{ service['port'] }}</td>
                                    <td>{{ service['amount'] }}</td>
                                    <td>{{ ((service['amount'] / endpoints_now) * 100).toFixed(2) }}%</td>
                                </tr>

                            </tbody>
                        </table>
                    </div>
                </div>
        </div>

    </div>
</template>
{% endverbatim %}

<script>
Vue.component('combined_number_statistics', {
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
                    numbers: {
                        integrity_and_confidentiality: {
                            title: "Integrity and confidentiality",
                            intro: "Good encryption guarantees that information cannot be read or altered by others.",
                        },

                        website_content_security: {
                            title: "Website content security",
                            intro: "Does the website prevent a series of attacks?"
                        },

                        technology: "Technology",
                        result: "Result",
                        total: "Total",

                    },
                    services: {
                        title: 'Services',
                        intro: 'One address can have a plethora of services.',
                        number_of_service_checked: 'A total of {0} services are checked.',

                        ip_version: "IP Version",
                        protocol: "Protocol",
                        port: "Port",
                        amount: "Amount",
                        percentage: "Percentage",
                    }
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
                    numbers: {
                        integrity_and_confidentiality: {
                            title: "Integriteit en vertrouwlijkheid",
                            intro: "Alle afzonderlijke bevindingen rondom integriteit en vertrouwelijkheid.",
                        },

                        website_content_security: {
                            title: "Website veiligheids instellingen",
                            intro: "Een overzicht van diverse instellingen die websites kunnen gebruiken om veiligheid te verhogen",
                        },

                        technology: "Techniek",
                        result: "Resultaat",
                        total: "Totaal",

                    },
                    services: {
                        title: 'Dienst',
                        intro: 'Een enkel adres kan meerdere diensten hebben, denk aan bestandsoverdracht, een website en e-mail.',
                        number_of_service_checked: 'In totaal werden {0} verschillende diensten gescand.',

                        ip_version: "IP Versie",
                        protocol: "Protocol",
                        port: "Poort",
                        amount: "Aantal",
                        percentage: "Percentage",
                    }
                }
            }
        },
    },
    template: "#combined_number_statistics_template",
    mixins: [new_state_mixin, translation_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            data: Array,
            services: [],
            endpoints_now: 0,
            explained: [],

            //
            organization_stats: [],
            url_stats: [],

            // sorting
            columns: ['ip_version', 'protocol', 'port', 'amount'],
            sortKey: 'amount',
            sortOrders: {'ip_version': 1, 'protocol': 1, 'port': 1, 'amount': -1},
        }
    },

    props: {
        issues: Array,
        show_services: Boolean,
        color_scheme: Object,
    },

    methods: {
        load: function (weeknumber=0) {
            fetch(`/data/stats/${this.state.country}/${this.state.layer}/${weeknumber}`).then(response => response.json()).then(data => {

                // empty
                if (Object.keys(data).length < 1){
                    this.data = [];
                    this.endpoints_now = 0;
                    this.explained = [];
                    this.organization_stats= [];
                    this.url_stats = [];
                    this.services = [];
                    return;
                }

                this.data = data;
                this.organization_stats = data.organizations;
                this.url_stats = data.urls;
                this.explained = data.explained;
                this.endpoints_now = data.endpoints_now;

                this.services = [];
                for(let i=0; i<data.endpoint.length; i++){
                    let z = data.endpoint[i][1];
                    this.services.push({
                        'amount': z.amount,
                        'ip_version': z.ip_version,
                        'protocol': z.protocol,
                        'port': z.port})
                }
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail); throw fail});
        },

        sortBy: function (key) {
            this.sortKey = key;
            this.sortOrders[key] = this.sortOrders[key] * -1;
        },
        // https://stackoverflow.com/questions/15762768/javascript-math-round-to-two-decimal-places

    },
    computed: {
        issue_categories: function() {
            // this delivers duplicates, but given the number of issues is low, it's fine.
            // otherway: arrayx = [array1, array2]
            let _categories = [];
            this.issues.forEach(function(issue){
                // console.log(_categories);
                _categories = _categories.concat(issue['category'])
            });
            return _categories;
        },

        filteredData: function () {
            let sortKey = this.sortKey;
            let filterKey = this.filterKey && this.filterKey.toLowerCase();
            let order = this.sortOrders[sortKey] || 1;
            let data = this.services;
            if (filterKey) {
                data = data.filter(function (row) {
                    return Object.keys(row).some(function (key) {
                        return String(row[key]).toLowerCase().indexOf(filterKey) > -1
                    })
                })
            }
            if (sortKey) {
                data = data.slice().sort(function (a, b) {
                    a = a[sortKey];
                    b = b[sortKey];
                    return (a === b ? 0 : a > b ? 1 : -1) * order
                })
            }
            return data
        }
    },
});
</script>
