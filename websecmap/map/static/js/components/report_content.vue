{% verbatim %}
<template type="x-template" id="report_content_template">
    <div id="report_content">
        <template v-if='loading'><div class="loader" style="width: 100px; height: 100px;"></div></template>
        <template v-if='!loading && (reported_organization.id || reported_organization.name)'>

            <div class="row report_controls" style="margin-bottom: 30px;">
                <div  class="col-md-3">
                    <a @click="closereport()" class="btn btn-danger" style="color:white; width: 100%"><svg aria-hidden="true" data-prefix="fas" data-icon="times" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" data-fa-i2svg="" class="svg-inline--fa fa-times fa-w-12"><path fill="currentColor" d="M323.1 441l53.9-53.9c9.4-9.4 9.4-24.5 0-33.9L279.8 256l97.2-97.2c9.4-9.4 9.4-24.5 0-33.9L323.1 71c-9.4-9.4-24.5-9.4-33.9 0L192 168.2 94.8 71c-9.4-9.4-24.5-9.4-33.9 0L7 124.9c-9.4 9.4-9.4 24.5 0 33.9l97.2 97.2L7 353.2c-9.4 9.4-9.4 24.5 0 33.9L60.9 441c9.4 9.4 24.5 9.4 33.9 0l97.2-97.2 97.2 97.2c9.3 9.3 24.5 9.3 33.9 0z"></path></svg>
                        {{ $t("report_content.controls.close_report") }}</a>
                </div>
                <div  class="col-md-3">
                    <a @click="printreport('report_content')" class="btn btn-primary" style="color:white; width: 100%"><svg aria-hidden="true" data-prefix="fas" data-icon="print" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg="" class="svg-inline--fa fa-print fa-w-16"><path fill="currentColor" d="M464 192h-16V81.941a24 24 0 0 0-7.029-16.97L383.029 7.029A24 24 0 0 0 366.059 0H88C74.745 0 64 10.745 64 24v168H48c-26.51 0-48 21.49-48 48v132c0 6.627 5.373 12 12 12h52v104c0 13.255 10.745 24 24 24h336c13.255 0 24-10.745 24-24V384h52c6.627 0 12-5.373 12-12V240c0-26.51-21.49-48-48-48zm-80 256H128v-96h256v96zM128 224V64h192v40c0 13.2 10.8 24 24 24h40v96H128zm304 72c-13.254 0-24-10.746-24-24s10.746-24 24-24 24 10.746 24 24-10.746 24-24 24z"></path></svg>
                        {{ $t("report_content.controls.print_report") }}</a>
                </div>
                <div  class="col-md-3">
                    <a :href="'/data/updates_on_organization_feed/' + selected.id" target="_blank" class="btn btn-warning" style="color:white;  width: 100%"><svg aria-hidden="true" data-prefix="fas" data-icon="rss" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" data-fa-i2svg="" class="svg-inline--fa fa-rss fa-w-14"><path fill="currentColor" d="M128.081 415.959c0 35.369-28.672 64.041-64.041 64.041S0 451.328 0 415.959s28.672-64.041 64.041-64.041 64.04 28.673 64.04 64.041zm175.66 47.25c-8.354-154.6-132.185-278.587-286.95-286.95C7.656 175.765 0 183.105 0 192.253v48.069c0 8.415 6.49 15.472 14.887 16.018 111.832 7.284 201.473 96.702 208.772 208.772.547 8.397 7.604 14.887 16.018 14.887h48.069c9.149.001 16.489-7.655 15.995-16.79zm144.249.288C439.596 229.677 251.465 40.445 16.503 32.01 7.473 31.686 0 38.981 0 48.016v48.068c0 8.625 6.835 15.645 15.453 15.999 191.179 7.839 344.627 161.316 352.465 352.465.353 8.618 7.373 15.453 15.999 15.453h48.068c9.034-.001 16.329-7.474 16.005-16.504z"></path></svg>
                        {{ $t("report_content.controls.rss_feed") }}</a>
                </div>
                <div  class="col-md-3">
                    <a class="btn btn-success" style="color:white; width: 100%" :href="'mailto:' + send_in_email_address + '?subject=' + encodeURIComponent($t('report_content.controls.send_in_mail.subject')) + '&body=' + encodeURIComponent($t('report_content.controls.send_in_mail.body'))">
                    {{ $t("report_content.controls.send_in_domains") }}</a>
                </div>
            </div>


            <div class="page-header" v-if="name">
                <a href="#" class="backtomap">{{ $t("back_to_map") }} ↑</a>
                <h3>{{ $t("report_content.report_of") }} {{ name }}</h3>
                <p>{{ $t("report_content.data_from") }}: {{ humanize(when) }}.</p>
            </div>

            <div class="row" v-if="name" style="margin-bottom: 30px;">
                <div class="col-md-4">
                    <div class="score high">
                        <span class="score_value high_text">{{ high }}</span><br/>
                        <span class="score_label">{{ $t("report_content.high_risk") }}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="score medium">
                        <span class="score_value medium_text">{{ medium }}</span><br/>
                        <span class="score_label">{{ $t("report_content.medium_risk") }}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="score low">
                        <span class="score_value low_text">{{ low }}</span><br/>
                        <span class="score_label">{{ $t("report_content.low_risk") }}</span>
                    </div>
                </div>
            </div>

            <div class="row" v-if="name" style="margin-bottom: 30px;">
                <div  class="col-md-12">
                    <h4>{{ $t("report_content.timeline.title") }}</h4>
                    <p></p>
                    <br style="clear: both">

                    <div class="chart-container" style="position: relative; height:555px; width:100%">
                        <vulnerability-chart :color_scheme="color_scheme" :data="timeline" :axis="['high', 'medium', 'low']"></vulnerability-chart>
                    </div>

                    <br />
                    <div class="chart-container" style="position: relative; height:555px; width:100%">
                        <connectivity-chart :color_scheme="color_scheme" :data="timeline"></connectivity-chart>
                    </div>
                </div>
            </div>

            <div class="row" v-if="name" style="margin-bottom: 30px;">
                <div  class="col-md-12">
                    <h4>{{ $t("report_content.risksummary.title") }}</h4>
                    <p></p>

                    <div class="table-responsive">
                    <table class="table table-striped table-bordered table-hover table-sm">
                        <thead>
                        <tr>
                            <th style="width:40%"></th>
                            <th style="white-space: nowrap; vertical-align: bottom; height: 240px;" v-for="issue in issues">
                                <div style="transform: translate(21px, -10px) rotate(315deg); width: 30px;">
                                    <span v-html="translate(issue['name'])"></span>
                                </div>
                            </th>
                        </thead>
                        <tbody style="max-height: 240px; overflow-y: scroll">
                        <template v-for="url in urls" >
                            <tr v-html="total_summary_row(url)"></tr>
                        </template>
                        </tbody>
                    </table>
                    </div>

                </div>
            </div>


            <div class="row" v-if="name">
                <div  class="col-md-12">
                    <h4>{{ $t("report_content.report.title") }}</h4>
                </div>
            </div>


            <div v-if="name" v-for="url in urls" class="perurl" :class="colorizebg(url.high, url.medium, url.low)">

                <div class="row">
                    <div class="col-md-4">
                        &nbsp;
                    </div>
                    <div class="col-md-8">
                        <a :name="'report_url_'+url.url"></a>
                        <span v-html="total_awarded_points(url.high, url.medium, url.low)"> </span>
                        <span :class="'faildomain ' + colorize(url.high, url.medium, url.low)+'_text'" :data-tooltip-content="idizetag(url.url)">{{ url.url }}</span><br/>
                        <a :href="'mailto:' + incorrect_finding_mail + '?subject=' + encodeURIComponent($t('report_content.report.incorrect_finding_mail.title', [url.url])) + '&body=' + encodeURIComponent($t('report_content.report.incorrect_finding_mail.body'))" class="btn btn-secondary btn-sm" style="margin-top: 11px;" role="button">
                            {{ $t("report_content.report.report_incorrect_finding") }}</a>
                    </div>
                </div>

                <!-- url reports -->
                <div v-if="url.ratings.length > 0" class="row">
                    <div class="col-md-4">
                        &nbsp;
                    </div>
                    <div class="col-md-8 giveroom_url">
                        <h4>{{ $t("report_content.report.url_level_findings") }}</h4>

                        <div v-for="rating in url.ratings">
                            <h5>&nbsp; {{ create_header(rating) }}</h5>
                            <div class="finding_block">
                                <span v-html="awarded_points(rating.high, rating.medium, rating.low)"></span> {{ translate(rating.explanation) }}<br/>
                                {{ $t("report_content.report.since") }}: {{ humanize(rating.since) }}, {{ $t("report_content.report.last_check") }}: {{ humanize(rating.last_scan) }}
                                <div class="finding_references">
                                    <span v-html="second_opinion_links(rating, url)"> </span>
                                    <span v-if="show_comply_or_explain" class="explain_link" v-html="explain_link(comply_or_explain_email_address, rating, url)"></span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- endpoint reports -->
                <div v-if="name" v-for="endpoint in url.endpoints" class="row">
                    <div class="col-md-4 giveroom photobar">
                        <a :href="endpoint.protocol + '://' + url.url + ':' + endpoint.port"
                           target="_blank"
                           :title="'Visit ' + endpoint.protocol + '://' + url.url + ':' + endpoint.port">
                            <img src="data:image/gif;base64,R0lGODdhAQABAPAAAMPDwwAAACwAAAAAAQABAAACAkQBADs="
                                 class="img-fluid rounded lazyload clippedimage" :data-src="'/static/images/screenshots/' + endpoint.id + '_latest.png'"
                                :alt="'Latest screenshot of '+ endpoint.protocol + idize(url.url) + endpoint.port"
                            />
                        </a>
                    </div>
                    <div class="col-md-8 giveroom">
                        <h4>{{ $t("report_content.report.service") }}: {{endpoint_type(endpoint) }}</h4>

                        <div>
                            <div v-for="rating in endpoint.ratings">
                                <h5>&nbsp; {{ create_header(rating) }}</h5>
                                <div class="finding_block" v-if="rating.comply_or_explain_valid_at_time_of_report">
                                    <span class="awarded_points_explained">{{ $t("report_content.report.explained") }}</span> {{ rating.comply_or_explain_explanation }}<br />
                                    {{ $t("report_content.report.explained_on") }}: {{ humanize(rating.comply_or_explain_explained_on) }}, {{ $t("report_content.report.explanation_expires") }}: {{ humanize(rating.comply_or_explain_explanation_valid_until) }}<br>
                                    <del style="font-size: 0.8em"><span v-html="awarded_points(rating.high, rating.medium, rating.low)"></span> {{ translate(rating.explanation) }}<br/>
                                    {{ $t("report_content.report.since") }}: {{ humanize(rating.since) }}, {{ $t("report_content.report.last_check") }}: {{ humanize(rating.last_scan) }}</del>
                                    <div class="finding_references" v-html="second_opinion_links(rating, url)"> </div>
                                </div>
                                <div class="finding_block" v-else>
                                    <span v-html="awarded_points(rating.high, rating.medium, rating.low)"></span> {{ translate(rating.explanation) }}<br/>
                                    {{ $t("report_content.report.since") }}: {{ humanize(rating.since) }}, {{ $t("report_content.report.last_check") }}: {{ humanize(rating.last_scan) }}

                                    <div class="finding_references">
                                        <span v-html="second_opinion_links(rating, url)"> </span>
                                        <span v-if="show_comply_or_explain" class="explain_link" v-html="explain_link(comply_or_explain_email_address, rating, url)"></span>
                                    </div>

                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('report_content', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                report_content: {

                    explain: {
                        explain: "Explain",
                        subject: "Explanation of finding",
                        body: "Hi!,\n" +
                            "\n" +
                            "I would like to explain the below finding.\n" +
                            "\n" +
                            "Address: %{url}\n" +
                            "Scan Type: %{scan_type}\n" +
                            "Scan ID: %{scan_id}\n" +
                            "Impact: High: %{high}, Medium %{medium}, Low: %{low}.\n" +
                            "\n" +
                            "I believe the finding to be incorrect. This is why:\n" +
                            "[... please enter your explanation for review here ...]\n" +
                            "\n" +
                            "I acknowledge that this finding will be published together with my organizations name.\n" +
                            "\n" +
                            "tip: please refer to documentation or standards where possible. Be aware that an explanation is valid " +
                            "for one year by default.\n" +
                            "\n" +
                            "Kind regards,\n" +
                            "",
                    },

                    controls: {
                        close_report: "Close",
                        print_report: "Print",
                        rss_feed: "RSS feed",
                        send_in_domains: "Send in more domains",

                        send_in_mail: {
                            subject: "New subdomains for ...",
                            body: "Dear,\n\n" +
                                "Please add the following domains to the map:\n\n" +
                                "Tip: send a zonefile with all domains if possible.\n\n" +
                                "Kind regards,\n\n",
                        }
                    },

                    report_of: "Report of",
                    data_from: "Data from",
                    high_risk: "High risk",
                    medium_risk: "Medium risk",
                    low_risk: "Low risk",
                    timeline: {
                        title: "Timeline of risks and available services",
                    },
                    risksummary: {
                        title: "Risk summary table"
                    },

                    report: {
                        title: "Complete report",
                        report_incorrect_finding: "Report incorrect finding",
                        incorrect_finding_mail: {
                            title: 'Incorrect finding on {0}',
                            body: 'Notice: be aware that everything is scanned and updated routinely. This can take a few days.\n\n\n' +
                                'Dear,\n\n' +
                                'It seems there is some incorrect data on the map, the following is incorrect:\n\n' +
                                '1: ...\n' +
                                '2: ...\n' +
                                '3: ...\n' +
                                '\n\n' +
                                'Tip: include an explanation why the measurement is wrong, to speed up resolving this issue.\n\n\n' +
                                'Kind regards,\n' +
                                '',
                        },
                        url_level_findings: "Url level findings",
                        service: "Service",
                        since: "Since",
                        explained_on: "Explained on",
                        last_check: "Last check",
                        explained: "Explained",
                        explanation_expires: "Explanation expired on",

                        score_perfect: "perfect",
                        score_high: "high",
                        score_medium: "medium",
                        score_low: "low",
                        second_opinion: "Second opinion",
                        documentation: "Documentation",
                    },


                }
            },
            nl: {
                report_content: {
                    title: "Rapport",
                    intro: "",
                }
            }
        },
    },
    template: "#report_content_template",
    mixins: [new_state_mixin, translation_mixin],

    data: function () {
        return {
            calculation: '',
            rating: 0,
            points: 0,
            high: 0,
            medium: 0,
            low: 0,
            when: 0,
            twitter_handle: '',
            name: "",
            urls: Array,
            selected: {'id': null, 'label': null, 'name': null},
            loading: false,
            visible: false,  // fullscreenreport
            promise: false,

            // so they can be destroyed and re-initialized, is this really needed?
            myChart: null,
            myChart2: null,
            timeline: [],
        }
    },

    props: {
        issues: Array,
        url_issue_names: Array,
        organization: [String, Number],
        color_scheme: Object,
        incorrect_finding_mail: String,
        show_comply_or_explain: Boolean,
        comply_or_explain_email_address: String,
        send_in_email_address: String,
    },

    // https://vuejs.org/v2/api/#updated
    // When this has been updated, call the lazyload again, as the images below need to be lazyloaded.
    updated: function () {
        this.$nextTick(function () {
          lazyload()
        })
    },

    methods: {
        closereport: function(){
            store.commit('change', {reported_organization: {
                id: null,
                name: null,
            }});
        },
        printreport: function(divId){
            css1 = '<link href="/static/css/vendor/bootstrap.min.css" rel="stylesheet" type="text/css">';
            css4 = '<link href="/static/css/overrides.css" rel="stylesheet" type="text/css">';
            window.frames["print_frame"].document.body.innerHTML=css1 + css4 + document.getElementById(divId).innerHTML;

            // there is no real guarantee that the content / css has loaded...
            setTimeout(this.startprinting,1000);
        },
        startprinting: function(){
            window.frames["print_frame"].window.focus();
            window.frames["print_frame"].window.print();
        },

        load: function () {
            // against symptom of autoloading when setting state, this doesn't have the right parameters.
            if (!this.reported_organization.id && !this.reported_organization.name) {
                // reset:
                this.timeline = null;

                this.calculation = '';
                this.rating = 0;
                this.points = 0;
                this.high = 0;
                this.medium = 0;
                this.low = 0;
                this.when = 0;
                this.twitter_handle = '';
                this.name = "";
                this.urls = Array;
                this.selected = {'id': null, 'label': null, 'name': null};
                this.loading = false;
                this.visible = false;
                this.promise = false;

                // so they can be destroyed and re-initialized, is this really needed?
                this.myChart = null;
                this.myChart2 = null;
                this.timeline = [];

                // todo: clear this thing if there is nothing reported......
                // todo: make reset function.
                return;
            }

            this.loading = true;
            this.name = null;

            let org = this.reported_organization.id ? this.reported_organization.id : this.reported_organization.name;

            // first update the graphs, doing this around, the graph will show the previous data, not the current stuff
            fetch(`/data/organization_vulnerability_timeline/${org}/${this.state.layer}/${this.state.country}`).then(response => response.json()).then(timelinedata => {
                if (!$.isEmptyObject(timelinedata)){
                    this.timeline = timelinedata;
                    console.log("Todo: implement graph return on organization name.")
                }
            }).catch((fail) => {console.log('An error occurred on report content: ' + fail)});

            let url = "";
            if (this.reported_organization.name){
                url = `/data/report/${this.state.country}/${this.state.layer}/${this.reported_organization.name}/${this.state.week}`;
            }
            if (this.reported_organization.id){
                url = `/data/report/${this.state.country}/${this.state.layer}/${this.reported_organization.id}/${this.state.week}`;
            }

            console.log(`Retrieving report data from ${url}.`);
            fetch(url)
                .then(response => response.json()).then(data => {
                this.urls = data.calculation["organization"]["urls"];
                this.points = data.rating;
                this.high = data.calculation["organization"]["high"];
                this.medium = data.calculation["organization"]["medium"];
                this.low = data.calculation["organization"]["low"];
                this.when = data.when;
                this.name = data.name;
                this.twitter_handle = data.twitter_handle;
                this.promise = data.promise;
                this.slug = data.slug;

                // include id in anchor to allow url sharing
                let newHash = 'report-' + this.slug;
                $('a#report-anchor').attr('name', newHash);
                history.replaceState({}, '', '#' + newHash);

                this.loading = false;
            }).catch((fail) => {console.log('An error occurred on report content: ' + fail)});
        },
        total_summary_row: function(url){

            let worst = {};

            self = this;
            this.issues.forEach((issue) => {
                if (self.url_issue_names.includes(issue['name']))
                    worst[issue['name']] = this.worstof(issue['name'], [url]);
                else
                    worst[issue['name']] = this.worstof(issue['name'], url.endpoints);
            });

            let text = `<td><b><a href="#report_url_${url.url}">🔎 ${url.url}</a></b></td>`;

            let findings = "";

            this.issues.forEach(function (issue) {
                findings += `<td class='text-center ${worst[issue['name']].bgclass}'>${worst[issue['name']].text}</td>`;
            });

            return text + findings;
        },

        worstof: function(risk, endpoints){
            let high = 0, medium = 0, low = 0;
            let risk_found = false;
            let explained = false;

            for(let i=0; i<endpoints.length; i++) {
                let endpoint = endpoints[i];
                for (let i = 0; i < endpoint.ratings.length; i++) {
                    let rating = endpoint.ratings[i];

                    if (rating.type === risk) {
                        risk_found = true;
                        high += rating.high;
                        medium += rating.medium;
                        low += rating.low;
                        if (rating.comply_or_explain_valid_at_time_of_report)
                            explained = true;
                    }
                }
            }

            let text = "";
            let bgclass = "";

            if (high){
                text = "";
                bgclass = "high_background_light";
            } else if (medium){
                text = "";
                bgclass = "medium_background_light";
            } else if (low){
                text = "";
                bgclass = "low_background_light";
            } else if (risk_found) {
                text = "";
                bgclass = "good_background_light";
            }

            if (explained) {
                // if this is a string with "", translations say unterminated string. As ES6 template it's fine.
                text = `<svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="comments" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" class="svg-inline--fa fa-comments fa-w-18"><path fill="currentColor" d="M416 192c0-88.4-93.1-160-208-160S0 103.6 0 192c0 34.3 14.1 65.9 38 92-13.4 30.2-35.5 54.2-35.8 54.5-2.2 2.3-2.8 5.7-1.5 8.7S4.8 352 8 352c36.6 0 66.9-12.3 88.7-25 32.2 15.7 70.3 25 111.3 25 114.9 0 208-71.6 208-160zm122 220c23.9-26 38-57.7 38-92 0-66.9-53.5-124.2-129.3-148.1.9 6.6 1.3 13.3 1.3 20.1 0 105.9-107.7 192-240 192-10.8 0-21.3-.8-31.7-1.9C207.8 439.6 281.8 480 368 480c41 0 79.1-9.2 111.3-25 21.8 12.7 52.1 25 88.7 25 3.2 0 6.1-1.9 7.3-4.8 1.3-2.9.7-6.3-1.5-8.7-.3-.3-22.4-24.2-35.8-54.5z" class=""></path></svg>`;
                bgclass = "good_background_light";
            }

            return {'bgclass': bgclass, 'text': text}

        },

        colorize: function (high, medium, low) {
            if (high > 0) return "high";
            if (medium > 0) return "medium";
            return "good";
        },
        colorizebg: function (high, medium, low) {
            if (high > 0) return "report_url_background_high";
            if (medium > 0) return "report_url_background_medium";
            return "report_url_background_good";
        },
        idize: function (url) {
            url = url.toLowerCase();
            return url.replace(/[^0-9a-z]/gi, '')
        },
        idizetag: function (url) {
            url = url.toLowerCase();
            return "#" + url.replace(/[^0-9a-z]/gi, '')
        },
        humanize: function (date) {
            // It's better to show how much time was between the last scan and now. This is easier to understand.
            return moment(date).fromNow();
        },
        create_header: function (rating) {
            return this.translate(rating.type);
        },
        second_opinion_links: function (rating, url) {

            // todo: no documentation links are found...
            // console.log(this.issues);
            let selected_issue = this.issues[rating.type];

            if (!selected_issue) {
                return ""
            }

            let links = "";

            // todo: take in account language.
            // todo: this should be part of the template, not a weird function...
            selected_issue['second opinion links'].forEach(function (item){
                let filled_url = item.url;
                filled_url = filled_url.replace("${url.url}", url.url);
                links += `<a href="${filled_url}" target="_blank" class="btn-sm"><svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="clipboard-check" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" class="svg-inline--fa fa-clipboard-check fa-w-12"><path fill="currentColor" d="M336 64h-80c0-35.3-28.7-64-64-64s-64 28.7-64 64H48C21.5 64 0 85.5 0 112v352c0 26.5 21.5 48 48 48h288c26.5 0 48-21.5 48-48V112c0-26.5-21.5-48-48-48zM192 40c13.3 0 24 10.7 24 24s-10.7 24-24 24-24-10.7-24-24 10.7-24 24-24zm121.2 231.8l-143 141.8c-4.7 4.7-12.3 4.6-17-.1l-82.6-83.3c-4.7-4.7-4.6-12.3.1-17L99.1 285c4.7-4.7 12.3-4.6 17 .1l46 46.4 106-105.2c4.7-4.7 12.3-4.6 17 .1l28.2 28.4c4.7 4.8 4.6 12.3-.1 17z" class=""></path></svg>&nbsp;` +
                    this.$t("report_content.report.second_opinion") + ` (${item.provider}) </a> `;
            });

            selected_issue['documentation links'].forEach(function (item){
                links += `<a href="${item.url}" target="_blank" class="btn-sm"><svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="book" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" class="svg-inline--fa fa-book fa-w-14"><path fill="currentColor" d="M448 360V24c0-13.3-10.7-24-24-24H96C43 0 0 43 0 96v320c0 53 43 96 96 96h328c13.3 0 24-10.7 24-24v-16c0-7.5-3.5-14.3-8.9-18.7-4.2-15.4-4.2-59.3 0-74.7 5.4-4.3 8.9-11.1 8.9-18.6zM128 134c0-3.3 2.7-6 6-6h212c3.3 0 6 2.7 6 6v20c0 3.3-2.7 6-6 6H134c-3.3 0-6-2.7-6-6v-20zm0 64c0-3.3 2.7-6 6-6h212c3.3 0 6 2.7 6 6v20c0 3.3-2.7 6-6 6H134c-3.3 0-6-2.7-6-6v-20zm253.4 250H96c-17.7 0-32-14.3-32-32 0-17.6 14.4-32 32-32h285.4c-1.9 17.1-1.9 46.9 0 64z" class=""></path></svg>&nbsp;` +
                    this.$t("report_content.report.documentation") + ` (${item.provider})</a> `;
            });

            return links;

        },
        explain_link: function(address, rating, url) {
            let subject = this.$t("report_content.explain.subject");
            let explain = this.$t("report_content.explain.explain");
            let body = this.$t("report_content.explain.body", {
                url: url.url, scan_type: rating.type, scan_id: rating.scan, high: rating.high, medium: rating.medium, low: rating.low
            });
            return `<a href='mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}' class='btn-sm'>
                        <svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="comments" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" class="svg-inline--fa fa-comments fa-w-18"><path fill="currentColor" d="M416 192c0-88.4-93.1-160-208-160S0 103.6 0 192c0 34.3 14.1 65.9 38 92-13.4 30.2-35.5 54.2-35.8 54.5-2.2 2.3-2.8 5.7-1.5 8.7S4.8 352 8 352c36.6 0 66.9-12.3 88.7-25 32.2 15.7 70.3 25 111.3 25 114.9 0 208-71.6 208-160zm122 220c23.9-26 38-57.7 38-92 0-66.9-53.5-124.2-129.3-148.1.9 6.6 1.3 13.3 1.3 20.1 0 105.9-107.7 192-240 192-10.8 0-21.3-.8-31.7-1.9C207.8 439.6 281.8 480 368 480c41 0 79.1-9.2 111.3-25 21.8 12.7 52.1 25 88.7 25 3.2 0 6.1-1.9 7.3-4.8 1.3-2.9.7-6.3-1.5-8.7-.3-.3-22.4-24.2-35.8-54.5z" class=""></path>
                    </svg> ${explain}</a>`;
        },
        total_awarded_points: function (high, medium, low) {
            let marker = this.make_marker(high, medium, low);
            return '<span class="total_awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
        },
        awarded_points: function (high, medium, low) {
            let marker = this.make_marker(high, medium, low);
            return '<span class="awarded_points_' + this.colorize(high, medium, low) + '">' + marker + '</span>'
        },
        make_marker: function (high, medium, low) {
            if (high === 0 && medium === 0 && low === 0)
                return this.$t("report_content.report.score_perfect");
            else if (high > 0)
                return this.$t("report_content.report.score_high");
            else if (medium > 0)
                return this.$t("report_content.report.score_medium");
            else
                return this.$t("report_content.report.score_low");
        },
        endpoint_type: function (endpoint) {
            return endpoint.protocol + "/" + endpoint.port + " (IPv" + endpoint.ip_version + ")";
        },
    },

    watch: {
        reported_organization: function () {
            // load selected organization id
            this.load()
        }
    }
});
</script>
