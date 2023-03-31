{% verbatim %}
<template type="x-template" id="report_selection_template">
    <div>
        <div class="page-header">
            <h2><span class="organization_points"></span>
                <svg class="svg-inline--fa fa-file-alt fa-w-12" aria-hidden="true" data-prefix="far" data-icon="file-alt" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" data-fa-i2svg=""><path fill="currentColor" d="M288 248v28c0 6.6-5.4 12-12 12H108c-6.6 0-12-5.4-12-12v-28c0-6.6 5.4-12 12-12h168c6.6 0 12 5.4 12 12zm-12 72H108c-6.6 0-12 5.4-12 12v28c0 6.6 5.4 12 12 12h168c6.6 0 12-5.4 12-12v-28c0-6.6-5.4-12-12-12zm108-188.1V464c0 26.5-21.5 48-48 48H48c-26.5 0-48-21.5-48-48V48C0 21.5 21.5 0 48 0h204.1C264.8 0 277 5.1 286 14.1L369.9 98c9 8.9 14.1 21.2 14.1 33.9zm-128-80V128h76.1L256 51.9zM336 464V176H232c-13.3 0-24-10.7-24-24V48H48v416h288z"></path></svg>
                {{ $t("report.title") }}</h2>
        </div>

        <div class="row">
            <div class="col-md-12">
                {{ $t("report.select_organization") }}
                <v-select label="name"
                          v-model="selected"
                          :options="available_organizations"
                          :placeholder="$t('report.select_organization')"
                ></v-select>
                <br />
            </div>
        </div>
        <iframe name="print_frame" title="Print frame, used to load reports when clicking print." width="0" height="0" frameborder="0" src="about:blank"></iframe>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('report_selection', {
    store,

    mixins: [new_state_mixin, translation_mixin],

    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                report: {
                    title: "Report",
                    select_organization: "Show report for organization...",
                }
            },
            nl: {
                report: {
                    title: "Rapport",
                    select_organization: "Toon rapport van organisatie...",
                }
            }
        },
    },

    template: "#report_selection_template",

    data: function () {
        return {
            selected: {},
            available_organizations: [],
        }
    },

    methods: {
        load: function (weeknumber=0) {
            this.loading = true;
            fetch(`/data/organizations/list/${this.$store.state.country}/${this.$store.state.layer}/`).then(response => response.json()).then(data => {
                this.available_organizations = data;
                this.loading = false;
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail); throw fail});
        },
    },

    mounted: function(){
        this.load();
    },

    watch: {
        organizations: () => {

        },

        selected: function () {
            if (this.selected === undefined)
                return;

            store.commit('change', {reported_organization: {
                id: this.selected.id,
                name: this.selected.name,
            }});
        }
    }
});
</script>
