{% verbatim %}
<template type="x-template" id="report_composition_template">
    <div class="container">
        <report_selection></report_selection>
        <report_content
            :issues="issues"
            :url_issue_names="url_issue_names"
            :color_scheme="color_scheme"
            :incorrect_finding_mail="incorrect_finding_mail"
            :show_comply_or_explain="show_comply_or_explain"
            :send_in_email_address="send_in_email_address"
            :authenticated="authenticated"
            :comply_or_explain_email_address="comply_or_explain_email_address">
        </report_content>
    </div>
</template>
{% endverbatim %}

<script>
const ReportComposition = Vue.component('report_composition', {
    store,

    template: "#report_composition_template",

    props: {
        issues: Array,
        url_issue_names: Array,
        organization: [String, Number],
        color_scheme: Object,
        incorrect_finding_mail: String,
        show_comply_or_explain: Boolean,
        comply_or_explain_email_address: String,
        send_in_email_address: String,
        authenticated: Boolean,
    },
});
</script>
