{% verbatim %}
<template type="x-template" id="stats_named_issues_template">
    <div v-cloak class="container">

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

    </div>
</template>
{% endverbatim %}

<script>
const StatsNamedIssues = Vue.component('stats_named_issues', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                statistics: {
                    title: "Extensive statistics",

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

                }
            },
            nl: {
                statistics: {
                    title: "Uitgebreide statistieken",

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

                }
            }
        },
    },
    template: "#stats_named_issues_template",
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

        }
    },

    props: {
        issues: Array,
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

    },
});
</script>
