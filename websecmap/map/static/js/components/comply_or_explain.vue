{% verbatim %}
<template type="x-template" id="comply_or_explain_template">
    <div>
        <div class="page-header">
            <a href="#" class="backtomap">{{ $t("comply_or_explain.back_to_map") }} ↑</a>
            <a name="comply_or_explain_info" class="jumptonav"></a>
            <h2><svg class="svg-inline--fa fa-comments fa-w-18" aria-hidden="true" data-prefix="fas" data-icon="comments" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" data-fa-i2svg=""><path fill="currentColor" d="M416 192c0-88.4-93.1-160-208-160S0 103.6 0 192c0 34.3 14.1 65.9 38 92-13.4 30.2-35.5 54.2-35.8 54.5-2.2 2.3-2.8 5.7-1.5 8.7S4.8 352 8 352c36.6 0 66.9-12.3 88.7-25 32.2 15.7 70.3 25 111.3 25 114.9 0 208-71.6 208-160zm122 220c23.9-26 38-57.7 38-92 0-66.9-53.5-124.2-129.3-148.1.9 6.6 1.3 13.3 1.3 20.1 0 105.9-107.7 192-240 192-10.8 0-21.3-.8-31.7-1.9C207.8 439.6 281.8 480 368 480c41 0 79.1-9.2 111.3-25 21.8 12.7 52.1 25 88.7 25 3.2 0 6.1-1.9 7.3-4.8 1.3-2.9.7-6.3-1.5-8.7-.3-.3-22.4-24.2-35.8-54.5z"></path></svg>
                {{ $t("comply_or_explain.title") }}</h2>
            <p>{{ $t("comply_or_explain.intro") }}</p>

        </div>

        <template v-for="explain in explains">
            <div class="row">

                <div class="col-md-10">
                    <div class="chat_quote_left">
                        <del>
                        <span :class="'awarded_points_' + explain.original_severity">
                            {{ translate(explain.original_severity) }}
                        </span>&nbsp;&nbsp;
                        {{ translate(explain.scan_type) }}:
                        {{ translate(explain.original_explanation) }}
                        </del>
                    </div>
                    <br>
                    <blockquote class="blockquote text-right chat_quote_right">
                        <p class="mb-0">
                            {{ explain.explanation }}
                        </p>
                        <footer class="blockquote-footer">
                            {{ explain.explained_by }} <cite title="Source Title">{{ humanize(explain.explained_on) }} </cite>
                        </footer>
                    </blockquote>

                </div>

                <div class="col-md-2 text-center">
                    <small>{{ $t("comply_or_explain.view_report") }}</small>
                    <ul style="padding-left: 0px">
                        <li v-for="organization in explain.organizations" class="explain_reports">
                            <a @click="showreport(organization.id)" :title="'View report for ' + organization.name">
                            <svg class="svg-inline--fa fa-file-alt fa-w-12" aria-hidden="true" data-prefix="far" data-icon="file-alt" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" data-fa-i2svg=""><path fill="currentColor" d="M288 248v28c0 6.6-5.4 12-12 12H108c-6.6 0-12-5.4-12-12v-28c0-6.6 5.4-12 12-12h168c6.6 0 12 5.4 12 12zm-12 72H108c-6.6 0-12 5.4-12 12v28c0 6.6 5.4 12 12 12h168c6.6 0 12-5.4 12-12v-28c0-6.6-5.4-12-12-12zm108-188.1V464c0 26.5-21.5 48-48 48H48c-26.5 0-48-21.5-48-48V48C0 21.5 21.5 0 48 0h204.1C264.8 0 277 5.1 286 14.1L369.9 98c9 8.9 14.1 21.2 14.1 33.9zm-128-80V128h76.1L256 51.9zM336 464V176H232c-13.3 0-24-10.7-24-24V48H48v416h288z"></path></svg>
                                {{ organization.name }}
                            </a>
                        </li>
                    </ul>
                </div>

            </div>
        </template>

        <div class="row" v-if="!explains.length">
            <div class="col-md-12">
                {{ $t("comply_or_explain.no_explanations_yet") }}
            </div>
        </div>

        <div class="row">
            <div class="col-md-12 text-center">
                <button type="button" class="btn btn-primary" @click="showmore()" v-show="more_available">{{ $t("comply_or_explain.show_more") }}</button>
            </div>
        </div>

    </div>
</template>
{% endverbatim %}

<script>
Vue.component('comply_or_explain', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                comply_or_explain: {
                    title: "Comply or explain",
                    intro: "Comply or explain allows organizations to explain certain results on this website. In some edge cases, our finding may be technically correct but does not represent any danger. Below is a list of the latest explained issues. Organizations can explain issues using the 'explain' link per finding. You can download the entire dataset for further analysis in the datasets section. ",

                }
            },
            nl: {
                changes: {
                    title: "Pas toe of leg uit",
                }
            }
        },
    },
    template: "#comply_or_explain_template",
    mixins: [new_state_mixin, translation_mixin],

    data: function () {
        return {
            explains: Array(),
            more_explains: Array(),
            more_available: true,
        }
    },

    props: {
        show_discussion: Boolean,
    },

    methods: {
        humanize: function (date) {
            // It's better to show how much time was between the last scan and now. This is easier to understand.
            return moment(date).fromNow();
        },
        load: function() {
            fetch(`/data/explained/${this.state.country}/${this.state.layer}/`).then(response => response.json()).then(explains => {
                this.more_explains = explains.slice(3);
                this.explains = explains.slice(0, 3);

                if (this.more_explains.length === 0)
                    this.more_available = false;

            }).catch((fail) => {console.log('An error occurred in explains: ' + fail)});
        },
        showreport(organization_id){
            location.href = '#report';
            // todo: interaction between components...
            vueReport.selected = {'id': organization_id};
        },
        showmore(){
            if (this.more_explains.length > 3) {
                this.explains.push(this.more_explains.shift());
                this.explains.push(this.more_explains.shift());
                this.explains.push(this.more_explains.shift());
            } else if (this.more_explains.length > 1) {
                for (i=0; i<this.more_explains.length; i++){
                    this.explains.push(this.more_explains.shift());
                }
                this.more_available = false;
            }
        }
    },
});
</script>
