{% verbatim %}
<template type="x-template" id="account_template">
    <div class="stats_part" v-cloak>
        <h1>Account</h1>

        <h2>Credits</h2>
        <p>This account currently has {{ credits }} credits.</p>

        <h2>Transactions</h2>
        <table class="table table-sm table-striped table-bordered table-hover">
        <thead>
            <tr>
            <th>Transaction ID</th>
            <th>Description</th>
            <th>When</th>
            <th>Mutation</th>
            </tr>
        </thead>
        <tbody>
            <tr v-for="transaction in transactions">
                <td>{{ transaction.id }}</td>
                <td>{{ transaction.goal }}</td>
                <td><span :title="transaction.when">{{ transaction.when | naturaltime }}</span></td>
                <td>{{ transaction.credit_mutation }}</td>
            </tr>
            <tr v-if="!transactions.length">
                <td colspan="100">No transactions found.</td>
            </tr>
        </tbody>
        </table>

        <h2>Feeds</h2>
        <h3>Organization Feeds</h3>
        <table class="table table-sm table-striped table-bordered table-hover">
        <thead>
            <tr>
            <th>Feed ID</th>
            <th>Organization</th>
            <th>New urls placed in list</th>

            </tr>
        </thead>
        <tbody>
            <tr v-for="feed in feeds.organization">
                <td>{{ feed.id }}</td>
                <td>{{ feed.organization }}</td>
                <td>{{ feed.list }}</td>
            </tr>
            <tr v-if="!feeds.organization.length">
                <td colspan="100">No organization feeds found.</td>
            </tr>
        </tbody>
        </table>

        <h3>Url Feeds</h3>
        <table class="table table-sm table-striped table-bordered table-hover">
        <thead>
            <tr>
            <th>Feed ID</th>
            <th>Url filter</th>
            <th>New urls placed in list</th>

            </tr>
        </thead>
        <tbody>
            <tr v-for="feed in feeds.url">
                <td>{{ feed.id }}</td>
                <td>{{ feed.organization }}</td>
                <td>{{ feed.list }}</td>
            </tr>
            <tr v-if="!feeds.url.length">
                <td colspan="100">No url feeds found.</td>
            </tr>
        </tbody>
        </table>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('account', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                account: {
                    title: "Account",

                }
            },
            nl: {
                account: {
                    title: "Account",
                }
            }
        },
    },
    template: "#account_template",
    mixins: [credits_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            account: [],
            transactions: [],
            feeds: {
                organization: [],
                url: [],
            }
        }
    },

    props: {
        issues: Array,
        color_scheme: Object,
    },

    methods: {
        load: function () {
            fetch(`/data/account/info/`).then(response => response.json()).then(data => {
                this.account = data;
            }).catch((fail) => {console.log('An error occurred in account: ' + fail)});

            fetch(`/data/account/transactions/`).then(response => response.json()).then(data => {
                this.account = data;
            }).catch((fail) => {console.log('An error occurred in transactions: ' + fail)});

            fetch(`/data/account/datafeeds/organization/`).then(response => response.json()).then(data => {
                this.account = data;
            }).catch((fail) => {console.log('An error occurred in account: ' + fail)});

            fetch(`/data/account/datafeeds/url/`).then(response => response.json()).then(data => {
                this.account = data;
            }).catch((fail) => {console.log('An error occurred in account: ' + fail)});
        },
    },
});
</script>
