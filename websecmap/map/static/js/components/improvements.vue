{% verbatim %}
<template type="x-template" id="issue_improvements_template">
    <div class="stats_part" v-cloak>
        <div class="page-header">
            <h3>{{ $t("improvements.title") }}</h3>
            <p>{{ $t("improvements.intro") }}</p>
        </div>
        <div class="row">
            <div class="col-md-4" style="text-align:center">
                <h4>{{ $t("improvements.headers.high") }}</h4>
                <span :class="goodbad(results.overall.high) + '_large'">{{ results.overall.high }}</span>
                <table class="table table-striped">
                    <tr><td colspan="2" style="text-align: center;">{{ $t("improvements.consisting_of") }}</td></tr>
                    <tr v-for="issue in issues" v-if="issue['relevant impacts'].includes('high')">
                        <td v-html="translate(issue['name'])"></td>
                        <td v-if="results[issue['name']] !== undefined" :class="'number-sm ' + goodbad(results[issue['name']].high)"> <!-- :class="'number-sm ' + goodbad(results[issue['name']].high)" -->
                            {{ results[issue['name']]['high'] }}
                        </td>
                        <td v-if="results[issue['name']] === undefined" class="number-sm" style="font-size: 40px;">-</td>
                    </tr>
                </table>
            </div>
            <div class="col-md-4" style="text-align:center">
                <h4>{{ $t("improvements.headers.medium") }}</h4>
                <span :class="goodbad(results.overall.medium) + '_large'">{{ results.overall.medium }}</span>
                <table class="table table-striped">
                    <tr><td colspan="2" style="text-align: center;">{{ $t("improvements.consisting_of") }}</td></tr>
                    <tr v-for="issue in issues" v-if="issue['relevant impacts'].includes('medium')">
                        <td v-html="translate(issue['name'])"></td>
                        <td v-if="results[issue['name']]" :class="'number-sm ' + goodbad(results[issue['name']].medium)">
                            {{ results[issue['name']].medium }}
                        </td>
                        <td v-if="results[issue['name']] === undefined" class="number-sm" style="font-size: 40px;">-</td>
                    </tr>
                </table>
            </div>
            <div class="col-md-4" style="text-align:center">
                <h4>{{ $t("improvements.headers.low") }}</h4>
                <span :class="goodbad(results.overall.low) + '_large'">{{ results.overall.low }}</span>
                <table class="table table-striped">
                    <tr><td colspan="2" style="text-align: center;">{{ $t("improvements.consisting_of") }}</td></tr>
                    <tr v-for="issue in issues" v-if="issue['relevant impacts'].includes('low')">
                        <td v-html="translate(issue['name'])"></td>
                        <td v-if="results[issue['name']]" :class="'number-sm ' + goodbad(results[issue['name']].low)">
                            {{ results[issue['name']].low }}
                        </td>
                        <td v-if="results[issue['name']] === undefined" class="number-sm" style="font-size: 40px;">-</td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('improvements', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                improvements: {
                    title: "Improvements",
                    intro: "These are the improvements of the last 7 days. Positive numbers show progress, while negative numbers are a setback in security.",
                    headers: {
                        high: 'Total high risk improvements',
                        medium: 'Total medium risk improvements',
                        low: 'Total low risk improvements',
                    },
                    consisting_of: "Consisting of:"
                }
            },
            nl: {
                improvements: {
                    title: "Verbeteringen",
                    intro: "Dit zijn de verbeteringen van de laatste zeven dagen. Positieve getallen laten een vooruitgang zien, terwijl negatieve getallen verslechtering laten zien.",
                    headers: {
                        high: 'Totaal hoog risico verbeteringen',
                        medium: 'Totaal midden risico verbeteringen',
                        low: 'Totaal laag risico verbeteringen',
                    },
                    consisting_of: "Bestaande uit:"
                }
            }
        },
    },
    template: "#issue_improvements_template",
    mixins: [new_state_mixin, translation_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            results: {'overall': {high: 0, medium: 0, low: 0}}
        }
    },

    props: {
        issues: Array,
        state: Object,
    },

    methods: {
        load: function (weeks_ago=0) {
            fetch(`/data/improvements/${this.state.country}/${this.state.layer}/${weeks_ago}/0`).then(response => response.json()).then(data => {
                self = this;
                if ($.isEmptyObject(data)) {
                    this.issues.forEach(function (issue){
                       self.results[issue['name']] = {high: 0, medium:0, low: 0}
                    });

                    this.results.overall = {high: 0, medium:0, low: 0}
                } else {
                    this.issues.forEach(function (issue){
                        if (data[issue['name']] !== undefined)
                            self.results[issue['name']] = data[issue['name']].improvements;
                        else
                            self.results[issue['name']] = {high: 0, medium:0, low: 0}
                    });

                    if (data.overall !== undefined)
                        this.results.overall = data.overall.improvements;
                }

                // because some nested keys are used (results[x['bla']), updates are not handled correctly.
                this.$forceUpdate();

            }).catch((fail) => {console.log('An error occurred loading improvements:' + fail)});
        },
        goodbad: function (value) {
            if (value === 0) return "improvements_neutral";
            if (value > 0) return "improvements_good";
            return "improvements_bad";
        }
    }
});
</script>
