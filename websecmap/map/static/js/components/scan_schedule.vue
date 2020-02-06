{% verbatim %}
<template type="x-template" id="scan_schedule_templates">
    <div class="container">
        <div class="page-header">
            <h2>
                <svg class="svg-inline--fa fa-clock fa-w-16" aria-hidden="true" data-prefix="far" data-icon="clock" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M256 8C119 8 8 119 8 256s111 248 248 248 248-111 248-248S393 8 256 8zm0 448c-110.5 0-200-89.5-200-200S145.5 56 256 56s200 89.5 200 200-89.5 200-200 200zm61.8-104.4l-84.9-61.7c-3.1-2.3-4.9-5.9-4.9-9.7V116c0-6.6 5.4-12 12-12h32c6.6 0 12 5.4 12 12v141.7l66.8 48.6c5.4 3.9 6.5 11.4 2.6 16.8L334.6 349c-3.9 5.3-11.4 6.5-16.8 2.6z"></path></svg>
                {{ $t("scan_schedule.title") }}
            </h2>
            <p>{{ $t("scan_schedule.intro") }}</p>
        </div>
        <div class="row schedule_row" v-for="next_item in next">
            <div class="col-md-3 schedule_item">
                {{ humanize_relative_date(next_item.date) }}
            </div>
            <div class="col-md-9 schedule_item" v-html="next_item.name">
            </div>
        </div>
        <div class="row schedule_row" v-if="!next.length">
            {{ $t("scan_schedule.no_scans_scheduled") }}
        </div>
    </div>
</template>
{% endverbatim %}

<script>
const ScanSchedule = Vue.component('scan_schedule', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                scan_schedule: {
                    title: "Scan schedule",
                    intro: "Below scans and tasks will be performed in the future. This can help you getting a better perspective on when updates will be hapening to your organization. Note that all times are approximate due to caching and rounding. The time listed is the time the scan starts, it might take a while before your organization is scanned.",
                    no_scans_scheduled: "No scans are scheduled to be performed.",
                }
            },
            nl: {
                scan_schedule: {
                    title: "Scan schema",
                    intro: "Dit is een schema van alle aankomende scans. De scantijd verschilt per scan, bij grote hoeveelheden urls kan dit langer duren. De bevindingen worden bij het creëren van een nieuwe rapportage meegenomen.",
                    no_scans_scheduled: "Er zijn geen scans ingepland.",
                }
            }
        },
    },
    template: "#scan_schedule_templates",
    mixins: [humanize_mixin],

    data: function () {
        return {
            next: Array(),
            previous: Array(),
        }
    },

    mounted: function () {
        this.load()
    },

    methods: {
        load: function() {
            fetch('/data/upcoming_and_past_scans/').then(response => response.json()).then(data => {
                this.next = data.next;
                this.previous = data.previous;
            }).catch((fail) => {
                console.log('An error occurred on scan schedule: ' + fail)
            });
        },
    },
});
</script>
