{% verbatim %}
<template type="x-template" id="explain_template">
    <span>
        <a class='btn-sm' @click="start_explaining()" v-if="rating.high || rating.medium || rating.low">[admin] explain</a>
        <modal v-if="show_explanation" @close="stop_explaining()">
            <h3 slot="header">{{ $t("explain.title") }}</h3>

            <div slot="body">

                <server-response :response="explain_server_response"></server-response>

                <div style="width: 100%; background-color: lightcoral; padding: 10px;">
                    <h3>Issue</h3>

                    <template v-if="endpoint">
                        <b>Endpoint</b>: {{endpoint.id}}, {{endpoint.concat}}<br>
                    </template>

                    <template v-if="url">
                        <b>Url</b>: {{url.id}}, {{url.concat}}<br>
                    </template>

                    <b>Explanation</b>: {{rating.explanation}}<br>
                    <b>Scan</b>: {{rating.scan}}, {{rating.scan_type}}<br>
                    <b>Since</b>: {{rating.since}}<br>
                    <b>Impact</b>: high: {{rating.high}}, medium: {{rating.medium}}, low: {{rating.low}}<br>
                </div>

                <div v-if="rating.is_explained"  style="width: 100%; background-color: lightgreen; padding: 10px;">
                    <h3>Explanation</h3>
                    <b>Explanation:</b> {{ rating.comply_or_explain_explanation }}<br>
                    <b>Valid until</b>: {{ rating.comply_or_explain_explanation_valid_until }}<br>
                </div>

                <h4>Canned Explanation:</h4>
                <select v-model="explanation" size="4" style="width: 100%">
                    <option :value='$t("explain.canned_explanations.device_only_certificate")'>{{ $t("explain.canned_explanations.device_only_certificate") }}</option>
                    <option :value='$t("explain.canned_explanations.device_only_certificate")'>{{ $t("explain.canned_explanations.for_devices_only_not_browsers") }}</option>
                    <option :value='$t("explain.canned_explanations.fix_in_progress")'>{{ $t("explain.canned_explanations.fix_in_progress") }}</option>
                    <option :value='$t("explain.canned_explanations.scanner_bug")'>{{ $t("explain.canned_explanations.scanner_bug") }}</option>
                </select>

                <h4>Custom explanation</h4>
                <p v-if="scan.comply_or_explain_explanation"></p>
                <textarea style="width: 100%; height: 70px" v-model="explanation" placeholder="Enter explanation here..." v-html="scan.comply_or_explain_explanation"></textarea>

                <h4>Explained by</h4>
                <input style="width: 100%" v-model="explained_by">

                <h4>Validity</h4>
                <select v-model="validity">
                    <option value="30">30 days</option>
                    <option value="60">60 days</option>
                    <option value="180">180 days</option>
                    <option value="365">1 year</option>
                    <option value="730">2 years</option>
                    <option value="1095">3 years</option>
                    <option value="3650">10 years</option>
                    <option value="36500">Forever and ever</option>
                </select>
            </div>
            <div slot="footer">
                <button type="button" class="btn btn-secondary" @click="stop_explaining()">Close</button>

                <button v-if="rating.is_explained" type="button" class="btn btn-danger" @click="remove_explanation()">Remove</button>

                <!-- Only first explanation and extension have costs, alterations are free. -->
                <template v-if="!scan.comply_or_explain_is_explained">
                    <button class="btn btn-primary" @click="explain()">Explain</button>
                </template>
            </div>
        </modal>
    </span>
</template>
{% endverbatim %}

<script>
Vue.component('explain', {
    store,
    i18n: {
        messages: {
            en: {
                explain: {
                    title: "Explain this finding",
                    canned_explanations: {
                        device_only_certificate: "The certificate is used on specific devices exclusively, these trust this certificate specifically.",
                        for_devices_only_not_browsers: "This domain is for devices only, not browsers. These devices does not need this requirement.",
                        fix_in_progress: "The issue is being fixed by the supplier, a new version will be delivered soon.",
                        scanner_bug: "A bug in the scanner caused this issue. Manual testing has shown this issue does not occur.",
                    }
                },
            },
            nl: {
                intro: {
                    title: "Verklaar deze bevinding",
                    canned_explanations: {
                        device_only_certificate: "Dit certificaat wordt op specifieke apparatuur gebruikt. Deze apparatuur vertrouwd alleen dit certificaat.",
                        for_devices_only_not_browsers: "Dit domein wordt voor specifieke apparatuur gebruikt. Deze apparatuur heeft geen noodzaak voor deze beveiligingseis.",
                        fix_in_progress: "Dit probleem wordt op dit moment opgelost door de leverancier. Een nieuwe versie zal binnenkort beschikbaar zijn.",
                        scanner_bug: "Een bug in de scanner zorgt voor een verkeerde beoordeling. Een handmatige test toont aan dat dit probleem hier niet voorkomt.",
                    }
                }
            }
        },
    },

    mixins: [http_mixin],

    template: "#explain_template",

    data: function () {return {
        // current scan.
        scan: {},

        show_explanation: false,

        explain_server_response: {},

        explanation: '',
        explained_by: store.state.reported_organization.name,
        validity: 730,
    }},

    props: {
        authenticated: Boolean,

        url: Object,
        endpoint: Object,
        rating: Object
    },

    methods: {
        start_explaining: function(){
            this.stop_explaining();
            this.show_explanation = true;
        },
        stop_explaining: function(){
            // reset everything.
            this.show_explanation = false;

            this.explanation = '';
        },

        explain(){
            let data = {
                scan_type: this.rating.scan_type,
                scan_id: this.rating.scan,

                explanation: this.explanation,
                explained_by: this.explained_by,
                validity: this.validity
            };

            this.asynchronous_json_post(
                `/data/explain/explain/`, data, (server_response) => {
                    this.explain_server_response = server_response;
                });

        },
        remove_explanation(){
            fetch(`/pro/data/explain/remove_explanation/${this.scan_id}/${this.scan_type}/`).then(response => response.json()).then(data => {
                this.result = data;
            }).catch((fail) => {console.log('A loading error occurred: ' + fail);});
        },
    }
});
</script>
