{% verbatim %}
<template type="x-template" id="changes_template">
    <div class="stats_part">
        <div class="page-header">
            <h3>{{ $t("changes.title") }}</h3>
            <p>{{ $t("changes.intro") }}</p>
        </div>

        <div class="row">
            <template v-for="issue in issues">
                <template v-if="Object.keys(scans).includes(issue.name) && scans[issue.name].length">
                    <div class="col-md-6">
                        <h4 v-html="translate(issue.name)"></h4>
                        <p>{{ $t("changes.rss_feed_teaser") }}
                            <a :href="'/data/feed/' + issue.name" target="_blank">
                            <svg aria-hidden="true" data-prefix="fas" data-icon="rss" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" data-fa-i2svg="" class="svg-inline--fa fa-rss fa-w-14"><path fill="currentColor" d="M128.081 415.959c0 35.369-28.672 64.041-64.041 64.041S0 451.328 0 415.959s28.672-64.041 64.041-64.041 64.04 28.673 64.04 64.041zm175.66 47.25c-8.354-154.6-132.185-278.587-286.95-286.95C7.656 175.765 0 183.105 0 192.253v48.069c0 8.415 6.49 15.472 14.887 16.018 111.832 7.284 201.473 96.702 208.772 208.772.547 8.397 7.604 14.887 16.018 14.887h48.069c9.149.001 16.489-7.655 15.995-16.79zm144.249.288C439.596 229.677 251.465 40.445 16.503 32.01 7.473 31.686 0 38.981 0 48.016v48.068c0 8.625 6.835 15.645 15.453 15.999 191.179 7.839 344.627 161.316 352.465 352.465.353 8.618 7.373 15.453 15.999 15.453h48.068c9.034-.001 16.329-7.474 16.005-16.504z"></path></svg>
                            {{ $t("changes.rss_feed") }}</a>.
                        </p>

                        <div class="table-responsive">

                            <table class="table table-striped changes">
                                <thead>
                                <tr>
                                    <th>{{ $t("changes.scan_moment") }}</th>
                                    <th>{{ $t("changes.url") }}</th>
                                </tr>
                                </thead>
                                <tbody v-for="scan in scans[issue['name']]">
                                <tr :class="rowclass(scan)">
                                    <td class="date">{{ humanize_relative_date(scan.last_scan_moment) }}</td>
                                    <td class="url">{{ scan.url }}</td>
                                </tr>
                                <tr>
                                    <td class="service">{{ scan.service }}</td>
                                    <td colspan="2" class="explanation">{{ translate(scan.explanation) }}</td>
                                </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </template>
            </template>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('changes', {
    // it does not show all things nothing has been measured / no changes ...
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                changes: {
                    title: "Latest changes",
                    intro: "This is an overview of the most recent changes. These are processed at the end of the day. Because only changes are shown, it can take a while to see new information. Scans are being performed daily.",
                    scan_moment: "Scan moment",
                    url: "Domain",
                    rss_feed_teaser: "Stay updated of the latest findings using this ",
                    rss_feed: "RSS feed",
                }
            },
            nl: {
                changes: {
                    title: "Laatste wijzigingen",
                    intro: "Dit is een overzicht van de meest recente wijzigingen. Dit laat zien dat er e.e.a. veranderd en verbeterd, nog voordat het in een rapport komt te staan. Deze bevindingen worden dagelijks samengevat in een rapport.",
                    scan_moment: "Scan moment",
                    url: "Domein",
                    rss_feed_teaser: "Blijf op de hoogte van de laatste scans, gebruik deze ",
                    rss_feed: "RSS feed",
                }
            }
        },
    },
    template: "#changes_template",
    mixins: [new_state_mixin, translation_mixin, humanize_mixin],

    data: function () {
        return {
            scans: {}
        }
    },

    props: {
        issues: Array,
    },

    mounted: function () {
        this.load()
    },

    methods: {
        load: function(){
            let url = `/data/all_latest_scans/${this.state.country}/${this.state.layer}/`;

            fetch(url).then(response => response.json()).then(data => {
                    this.scans = data.scans;
                    // because some nested keys are used (results[x['bla']), updates are not handled correctly.
                    this.$forceUpdate();
                }).catch((fail) => {
                    console.log('An error occurred in changes: ' + fail)
            });
        },
        rowclass: function (scan) {
            if (scan.high === 0 && scan.medium === 0 && scan.low === 0)
                return "goodrow";
            else if (scan.high > 0)
                return "highrow";
            else if (scan.medium > 0)
                return "mediumrow";
            else
                return "lowrow";
        }
    },
});
</script>
