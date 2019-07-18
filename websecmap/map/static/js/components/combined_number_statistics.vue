{% verbatim %}
<template type="x-template" id="combined_number_statistics_template">
    <div v-cloak>
        <div class="page-header">
            <a href="#" class="backtomap">{{ $t("statistics.back_to_map") }} ↑</a>
            <a name="extensive_statistics" class="jumptonav"></a>
            <h2><svg class="svg-inline--fa fa-chart-area fa-w-16" aria-hidden="true" data-prefix="fas" data-icon="chart-area" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M500 384c6.6 0 12 5.4 12 12v40c0 6.6-5.4 12-12 12H12c-6.6 0-12-5.4-12-12V76c0-6.6 5.4-12 12-12h40c6.6 0 12 5.4 12 12v308h436zM372.7 159.5L288 216l-85.3-113.7c-5.1-6.8-15.5-6.3-19.9 1L96 248v104h384l-89.9-187.8c-3.2-6.5-11.4-8.7-17.4-4.7z"></path></svg>
                {{ $t("statistics.title") }}
            </h2>
        </div>
        <div class="row">
            <div class="col-md-6">
                <h3>{{ $t("statistics.progress_bars.organizations.title") }}</h3>
                <p>{{ $t("statistics.progress_bars.organizations.intro") }}</p>

                <div class="progress">
                    <div class="progress-bar bg-success" :style="{width:goodpercentage}">
                        <span class="sr-only">{{ $t("statistics.progress_bars.good") }}</span>
                    </div>
                    <div class="progress-bar bg-warning" :style="{width:mediumpercentage}">
                        <span class="sr-only">{{ $t("statistics.progress_bars.average") }}</span>
                    </div>
                    <div class="progress-bar bg-danger" :style="{width:highpercentage}">
                        <span class='sr-only'>{{ $t("statistics.progress_bars.bad") }}</span>
                    </div>
                    <div class="progress-bar bg-basic" :style="{width:unknownpercentage}">
                        <span class='sr-only'>{{ $t("statistics.progress_bars.unknown") }}</span>
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="table table-striped table-hover">
                        <thead>
                        <tr>
                            <th width="25%">{{ $t("statistics.progress_bars.when") }}</th>
                            <th width="5%">{{ $t("statistics.progress_bars.number") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.good") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.average") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.bad") }}</th>
                        </tr>
                        </thead>
                        <tbody v-if="data.data">

                        <tr v-for="(x, key) in data.data">
                            <td>{{ translate(key) }}</td>
                            <td>{{ x["included_organizations"] }}</td>
                            <td :style="'background: linear-gradient(0deg, rgba(93, 255, 42, 0.2) 0%, rgba(93, 255, 42, 0.2) ' + x['good percentage'] + '%, transparent ' + x['good percentage'] + '%, transparent 100%);'">
                                {{ x["good"] }}
                                <small>({{ x["good percentage"] }}%)</small>
                            </td>
                            <td :style="'background: linear-gradient(0deg, rgba(255, 211, 134, 0.19) 0%, rgba(255, 211, 134, 0.19) ' + x['medium percentage'] + '%, transparent ' + x['medium percentage'] + '%, transparent 100%);'">
                                {{ x["medium"] }}
                                <small>({{ x["medium percentage"] }}%)</small>
                            </td>
                            <td :style="'background: linear-gradient(0deg, rgba(255, 42, 42, 0.2) 0%, rgba(255, 42, 42, 0.2) ' + x['high percentage'] + '%, transparent ' + x['high percentage'] + '%, transparent 100%);'">
                                {{ x["high"] }}
                                <small>({{ x["high percentage"] }}%)</small>
                            </td>
                        </tr>

                        </tbody>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <h3>{{ $t("statistics.progress_bars.internet_addresses.title") }}</h3>
                <p>{{ $t("statistics.progress_bars.internet_addresses.intro") }}</p>

                <div class="progress">
                    <div class="progress-bar bg-success" :style="{width:goodurlpercentage}">
                        <span class="sr-only">{{ $t("statistics.progress_bars.good") }}</span>
                    </div>
                    <div class="progress-bar bg-warning" :style="{width:mediumurlpercentage}">
                        <span class="sr-only">{{ $t("statistics.progress_bars.medium") }}</span>
                    </div>
                    <div class="progress-bar bg-danger" :style="{width:highurlpercentage}">
                        <span class='sr-only'>{{ $t("statistics.progress_bars.bad") }}</span>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover">
                        <thead>
                        <tr>
                            <th width="25%">{{ $t("statistics.progress_bars.when") }}</th>
                            <th width="5%">{{ $t("statistics.progress_bars.number") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.good") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.average") }}</th>
                            <th width="20%">{{ $t("statistics.progress_bars.bad") }}</th>
                        </tr>
                        </thead>
                        <tbody v-if="data.data">

                        <tr v-for="(x, key) in data.data">
                            <td>{{ translate(key) }}</td>
                            <td>{{ x["total_urls"] }}</td>
                            <td :style="'background: linear-gradient(0deg, rgba(93, 255, 42, 0.2) 0%, rgba(93, 255, 42, 0.2) ' + x['good url percentage'] + '%, transparent ' + x['good url percentage'] + '%, transparent 100%);'">
                                {{ x["good_urls"] }}
                                <small>({{ x["good url percentage"] }}%)</small>
                            </td>
                            <td :style="'background: linear-gradient(0deg, rgba(255, 211, 134, 0.19) 0%, rgba(255, 211, 134, 0.19) ' + x['medium url percentage'] + '%, transparent ' + x['medium url percentage'] + '%, transparent 100%);'">
                                {{ x["medium_urls"] }}
                                <small>({{ x["medium url percentage"] }}%)</small>
                            </td>
                            <td :style="'background: linear-gradient(0deg, rgba(255, 42, 42, 0.2) 0%, rgba(255, 42, 42, 0.2) ' + x['high url percentage'] + '%, transparent ' + x['high url percentage'] + '%, transparent 100%);'">
                                {{ x["high_urls"] }}
                                <small>({{ x["high url percentage"] }}%)</small>
                            </td>
                        </tr>

                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="row" v-if="issue_categories.includes('integrity') || issue_categories.includes('website')">
            <div class="col-md-6" v-if="issue_categories.includes('integrity')">
                <h4>{{ $t("statistics.numbers.integrity_and_confidentiality.title") }}</h4>
                <p>{{ $t("statistics.numbers.integrity_and_confidentiality.intro") }}</p>
            </div>
            <div class="col-md-6" v-if="issue_categories.includes('website')">
                <h4>{{ $t("statistics.numbers.website_content_security.title") }}</h4>
                <p>{{ $t("statistics.numbers.website_content_security.intro") }}</p>
            </div>
        </div>
        <div class="row" v-if="data.data && (issue_categories.includes('integrity') || issue_categories.includes('website'))">
            <div class="col-md-6">
                <div v-for="(x, key) in data.data" v-if="key === 'now'">
                    <div class="table-responsive">
                        <table class="table" v-if="x['explained']">
                            <thead>
                            <tr>
                                <th width="10%">{{ $t("statistics.numbers.technology") }}</th>
                                <th width="50%">{{ $t("statistics.numbers.result") }}</th>
                                <th width="40%">{{ $t("statistics.numbers.total") }}</th>
                            </tr>
                            </thead>
                            <tbody v-for="issue in issues" v-if="issue.category.includes('integrity') && Object.keys(x.explained).includes(issue.name)">
                                <tr>
                                    <td colspan="3" v-html="translate(issue['name'])"></td>
                                </tr>
                                <tr class="highrow" v-for="grade in issue.statistics.bad">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="mediumrow" v-for="grade in issue.statistics.medium">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="goodrow" v-for="grade in issue.statistics.good">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div v-for="(x, key) in data.data" v-if="key === 'now'">
                    <div class="table-responsive">
                        <table class="table" v-if="x['explained']">
                            <thead>
                            <tr>
                                <th width="10%">{{ $t("statistics.numbers.technology") }}</th>
                                <th width="50%">{{ $t("statistics.numbers.result") }}</th>
                                <th width="40%">{{ $t("statistics.numbers.total") }}</th>
                            </tr>
                            </thead>
                            <tbody v-for="issue in issues" v-if="issue.category.includes('website') && Object.keys(x.explained).includes(issue.name)">
                                <tr>
                                    <td colspan="3" v-html="translate(issue['name'])"></td>
                                </tr>
                                <tr class="highrow" v-for="grade in issue.statistics.bad">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="mediumrow" v-for="grade in issue.statistics.medium">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                                <tr class="goodrow" v-for="grade in issue.statistics.good">
                                    <td></td>
                                    <td v-html="translate(grade.explanation)">:</td>
                                    <td>{{ x.explained[issue.name][grade.explanation] }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="row" v-if="show_services">
            <div class="col-md-12" v-for="(x, key) in data.data" v-if="key === 'now'">
                <h3>{{ $t("statistics.services.title") }}</h3>
                <p>{{ $t("statistics.services.intro") }}</p>
                    <p>{{ $t("statistics.services.number_of_service_checked", [x['endpoints']]) }}</p>
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
                                    <td>{{ ((service['amount']/endpoints_now) * 100).toFixed(2) }}%</td>
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
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                statistics: {
                    title: "Extensive statistics",
                    back_to_map: "back to the map",
                    progress_bars: {

                        organizations: {
                            title: "Organizations",
                            intro: "Organizations often have an extensive online presence with several websites and other services. The sum of the security of all of these services defines if the organization is secure or not.",
                        },
                        internet_addresses: {
                            title: "Internet addresses",
                            intro: "A security status has been determined for all below addresses.",
                        },
                        now: "now",
                        seven_days_ago: "7 days ago",
                        two_weeks_ago: "2 weeks ago",
                        three_weeks_ago: "3 weeks ago",
                        one_month_ago: "1 month ago",
                        two_months_ago: "2 months ago",
                        three_months_ago: "3 months ago",

                        when: "When",
                        number: "Number",
                        good: "Good",
                        average: "Average",
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
                    title: "",
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

            // sorting
            columns: ['ip_version', 'protocol', 'port', 'amount'],
            sortKey: 'amount',
            sortOrders: {'ip_version': 1, 'protocol': 1, 'port': 1, 'amount': -1},
        }
    },

    props: {
        issues: Array,
        state: Object,
        show_services: Boolean,
    },

    methods: {
        load: function (weeknumber=0) {
            fetch(`/data/stats/${this.state.country}/${this.state.layer}/${weeknumber}`).then(response => response.json()).then(data => {
                this.data = data;
                this.endpoints_now = data.data.now['endpoints'];
                this.services = [];
                for(let i=0; i<data.data.now['endpoint'].length; i++){
                    let z = data.data.now['endpoint'][i][1];
                    this.services.push({
                        'amount': z.amount,
                        'ip_version': z.ip_version,
                        'protocol': z.protocol,
                        'port': z.port})
                }
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail)});
        },
        perc: function (data, amount, total) {
            return (!data) ? "0%" :
                roundTo(data.now[amount] / data.now[total] * 100, 2) + "%";
        },
        translate: function(string){
            return gettext(string);
        },
        sortBy: function (key) {
            this.sortKey = key;
            this.sortOrders[key] = this.sortOrders[key] * -1;
        }
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
        goodpercentage: function () {
            return this.perc(this.data.data, "good", "total_organizations");
        },

        highpercentage: function () {
            return this.perc(this.data.data, "high", "total_organizations");
        },

        mediumpercentage: function () {
            if (this.data.data) {
                let score = 100 -
                    roundTo(this.data.data.now["no_rating"] / this.data.data.now["total_organizations"] * 100, 2) -
                    roundTo(this.data.data.now["high"] / this.data.data.now["total_organizations"] * 100, 2) -
                    roundTo(this.data.data.now["good"] / this.data.data.now["total_organizations"] * 100, 2);
                return roundTo(score, 2) + "%";
            }
            return 0
        },
        unknownpercentage: function () {
            return this.perc(this.data.data, "no_rating", "total_organizations");
        },
        goodurlpercentage: function () {
            return this.perc(this.data.data, "good_urls", "total_urls");
        },

        highurlpercentage: function () {
            return this.perc(this.data.data, "high_urls", "total_urls");
        },

        mediumurlpercentage: function () {
            if (this.data.data) {
                let score = 100 -
                    roundTo(this.data.data.now["high_urls"] / this.data.data.now["total_urls"] * 100, 2) -
                    roundTo(this.data.data.now["good_urls"] / this.data.data.now["total_urls"] * 100, 2);
                return roundTo(score, 2) + "%";
            }
            return 0
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
