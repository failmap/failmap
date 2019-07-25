{% verbatim %}
<template type="x-template" id="chart_template">
    <div class="col-md-12">

    <p v-if="metadata">{{ $t("chart.data_from") }} {{humanize(metadata.data_from_time) }}</p>

    <span role="button" class="btn btn-info btn-sm" v-on:click="swapFull()">
        <svg aria-hidden="true" data-prefix="fas" data-icon="plus-square" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" data-fa-i2svg="" class="svg-inline--fa fa-plus-square fa-w-14"><path fill="currentColor" d="M400 32H48C21.5 32 0 53.5 0 80v352c0 26.5 21.5 48 48 48h352c26.5 0 48-21.5 48-48V80c0-26.5-21.5-48-48-48zm-32 252c0 6.6-5.4 12-12 12h-92v92c0 6.6-5.4 12-12 12h-56c-6.6 0-12-5.4-12-12v-92H92c-6.6 0-12-5.4-12-12v-56c0-6.6 5.4-12 12-12h92v-92c0-6.6 5.4-12 12-12h56c6.6 0 12 5.4 12 12v92h92c6.6 0 12 5.4 12 12v56z"></path></svg>
        {{ $t("chart.expand_list") }}
    </span><br/><br/>

    <div class="table-responsive">
        <table class="table table-striped table-hover" id="chart_table">
            <thead>
            <tr>
                <th @click="sortBy('rank')" :class="{ active: sortKey === 'rank' }">{{ $t("chart.rank") }}
                    <span class="arrow" :class="sortOrders['rank'] > 0 ? 'asc' : 'dsc'">
              </span></th>
                <th @click="sortBy('organization_id')"
                    :class="{ active: sortKey === 'organization_id' }">{{ $t("chart.organization") }}
                    <span class="arrow" :class="sortOrders['organization_id'] > 0 ? 'asc' : 'dsc'"></span>
                </th>
                <th @click="sortBy('total_urls')" :class="{ active: sortKey === 'total_urls' }">{{ $t("chart.urls") }}
                    <span class="arrow" :class="sortOrders['total_urls'] > 0 ? 'asc' : 'dsc'"></span>
                </th>
                <th @click="sortBy('total_endpoints')" :class="{ active: sortKey === 'total_endpoints' }">{{ $t("chart.services") }}
                    <span class="arrow" :class="sortOrders['total_endpoints'] > 0 ? 'asc' : 'dsc'"></span>
                </th>
                <th @click="sortBy('high')" :class="{ active: sortKey === 'high' }">{{ $t("chart.high_risk") }}
                    <span class="arrow" :class="sortOrders['high'] > 0 ? 'asc' : 'dsc'"></span>
                </th>
                <th @click="sortBy('medium')" :class="{ active: sortKey === 'medium' }">{{ $t("chart.medium_risk") }}
                    <span class="arrow" :class="sortOrders['medium'] > 0 ? 'asc' : 'dsc'"></span>
                </th>
                <th @click="sortBy('low')" :class="{ active: sortKey === 'low' }">{{ $t("chart.low_risk") }}
                    <span class="arrow" :class="sortOrders['low'] > 0 ? 'asc' : 'dsc'">
              </span></th>
                <th @click="sortBy('relative')" :class="{ active: sortKey === 'relative' }">{{ $t("chart.relative_score") }}
                    <span class="arrow" :class="sortOrders['relative'] > 0 ? 'asc' : 'dsc'">
              </span></th>
            </tr>
            </thead>
            <tbody>

            <tr v-for='rank in filteredData'>
                <td>{{ rank['rank'] }}</td>
                <td><a v-on:click="showReport(rank.organization_id)">🔍 {{ rank['organization_name'] }}</a></td>
                <td>{{ rank['total_urls'] }}</td>
                <td>{{ rank['total_endpoints'] }}</td>
                <td>{{ rank['high'] }}</td>
                <td>{{ rank['medium'] }}</td>
                <td>{{ rank['low'] }}</td>
                <td>{{ rank['relative'] }}</td>
            </tr>
            </tbody>
        </table>
    </div>
</div>

</template>
{% endverbatim %}

<script>
Vue.component('chart', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                chart: {
                    data_from: "Data from: ",
                    expand_list: "Expand / shorten list",
                    rank: "#",
                    organization: "Organization",
                    urls: "Urls",
                    services: "Services",
                    high_risk: "High risk",
                    medium_risk: "Medium risk",
                    low_risk: "Low risk",
                    relative_score: "Relative",
                }
            },
            nl: {
                chart: {

                }
            }
        },
    },
    template: "#chart_template",
    mixins: [new_state_mixin],

    data: function () {
        return {
            data: Array, // a short list of 10 items.
            fulldata: Array, // a much larger list.
            columns: ['rank', 'high', 'medium', 'low', 'organization_id', 'total_urls', 'total_endpoints'],
            sortOrders: {'rank': 1, 'organization_id': 1, 'high': 1, 'medium': 1, 'low': 1, 'relative': 1, 'total_urls': 1, 'total_endpoints': 1},
            sortKey: '',
            metadata: {},
            key: {},
            filterKey: "",
        }
    },

    mounted: function () {
        this.load(0)
    },

    props: {
        data_url: String,
    },
    methods: {
        showReport: function (organization_id) {
            // you can only jump once to an anchor, unless you use a dummy
            location.hash = "#loading";
            location.hash = "#report";

            app.organization = organization_id;

            // todo: will be autoloaded as part of app, as the organization changes.
            app.week = vueMap.week;
            vueDomainlist.load(organization_id, vueMap.week);
        },
        humanize: function (date) {
            return new Date(date).humanTimeStamp()
        },
        load: function () {
            fetch(`${this.data_url}${this.state.country}/${this.state.layer}/${this.state.week}`).then(response => response.json()).then(data => {
                this.data = data.ranking.slice(0,10);
                this.fulldata = data.ranking;
                this.metadata = data.metadata;
            }).catch((fail) => {console.log('An error occurred in chart: ' + fail)});
        },
        sortBy: function (key) {
            this.sortKey = key;
            this.sortOrders[key] = this.sortOrders[key] * -1
        },
        swapFull: function(){
            temp = Array;
            temp = this.data;
            this.data = this.fulldata;
            this.fulldata = temp;
        }
    },
    computed: {
        filteredData: function () {
          let sortKey = this.sortKey;
          let filterKey = this.filterKey && this.filterKey.toLowerCase();
          let order = this.sortOrders[sortKey] || 1;
          let data = this.data;
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
    filters: {
        capitalize: function (str) {
            return str.charAt(0).toUpperCase() + str.slice(1)
        }
    }
});
</script>