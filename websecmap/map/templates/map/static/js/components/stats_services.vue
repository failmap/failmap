{% verbatim %}
<template type="x-template" id="stats_services_template">
    <div v-cloak class="container">

        <loading v-if="loading"></loading>

        <div class="row" v-if="filteredData.length">
            <div class="col-md-12">
                <h3>{{ $t("statistics.services.title") }}</h3>
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
const StatsServices = Vue.component('stats_services', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                statistics: {
                    services: {
                        title: 'Protocols and ports',
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
                    services: {
                        title: 'Protocollen en poorten',
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
    template: "#stats_services_template",
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

            loading: false,
        }
    },

    props: {},

    methods: {
        load: function (weeknumber=0) {
            this.loading = true;
            fetch(`/data/stats/${this.state.country}/${this.state.layer}/${weeknumber}`).then(response => response.json()).then(data => {

                // empty
                if (Object.keys(data).length < 1){
                    this.data = [];
                    this.endpoints_now = 0;
                    this.services = [];
                    return;
                }

                this.data = data;

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

                this.loading = false;
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail); throw fail});
        },

        sortBy: function (key) {
            this.sortKey = key;
            this.sortOrders[key] = this.sortOrders[key] * -1;
        },
        // https://stackoverflow.com/questions/15762768/javascript-math-round-to-two-decimal-places

    },
    computed: {
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
