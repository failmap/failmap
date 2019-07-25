{% verbatim %}
<template type="x-template" id="fullscreenreport_template">
    <div class="page-header"  v-if="visible">
        <div v-if="name" class="fullscreenlayout">
            <p class="closebutton" onclick="vueFullScreenReport.hide()">
                [ x ]
            </p>

            <!--
            <br />
            <a onclick="vueFullScreenReport.hide()" class="btn btn-primary" style="color:white;"><svg aria-hidden="true" data-prefix="fas" data-icon="times" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" data-fa-i2svg="" class="svg-inline--fa fa-times fa-w-12"><path fill="currentColor" d="M323.1 441l53.9-53.9c9.4-9.4 9.4-24.5 0-33.9L279.8 256l97.2-97.2c9.4-9.4 9.4-24.5 0-33.9L323.1 71c-9.4-9.4-24.5-9.4-33.9 0L192 168.2 94.8 71c-9.4-9.4-24.5-9.4-33.9 0L7 124.9c-9.4 9.4-9.4 24.5 0 33.9l97.2 97.2L7 353.2c-9.4 9.4-9.4 24.5 0 33.9L60.9 441c9.4 9.4 24.5 9.4 33.9 0l97.2-97.2 97.2 97.2c9.3 9.3 24.5 9.3 33.9 0z"></path></svg>
                {% trans "close report" %}</a>
            <a @click="printreport('reportcontent')" class="btn btn-success" style="color:white;"><svg aria-hidden="true" data-prefix="fas" data-icon="print" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg="" class="svg-inline--fa fa-print fa-w-16"><path fill="currentColor" d="M464 192h-16V81.941a24 24 0 0 0-7.029-16.97L383.029 7.029A24 24 0 0 0 366.059 0H88C74.745 0 64 10.745 64 24v168H48c-26.51 0-48 21.49-48 48v132c0 6.627 5.373 12 12 12h52v104c0 13.255 10.745 24 24 24h336c13.255 0 24-10.745 24-24V384h52c6.627 0 12-5.373 12-12V240c0-26.51-21.49-48-48-48zm-80 256H128v-96h256v96zM128 224V64h192v40c0 13.2 10.8 24 24 24h40v96H128zm304 72c-13.254 0-24-10.746-24-24s10.746-24 24-24 24 10.746 24 24-10.746 24-24 24z"></path></svg>
                {% trans "print report" %}</a>
                <br /><br />
                -->
            <report_content
                    :issues="issues"
                    :url_issue_names="url_issue_names"
                    :organization="organization"
                    :color_scheme="color_scheme"
                    :incorrect_finding_mail="incorrect_finding_mail"
                    :show_comply_or_explain="show_comply_or_explain"
                    :send_in_email_address="send_in_email_address"
                    :comply_or_explain_email_address="comply_or_explain_email_address">
            </report_content>

        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('fullscreenreport', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                fullscreenreport: {
                    close: "Close",

                }
            },
            nl: {
                fullscreenreport: {
                    close: "Sluiten",
                }
            }
        },
    },
    template: "#fullscreenreport_template",
    mixins: [new_state_mixin],

    data: function () {
        return {
            visible: false,
        }
    },

    props: {
        // is there a pass through option? Or should this all be state?
        issues: Array,
        url_issue_names: Array,
        organization: [String, Number],
        color_scheme: Object,
        incorrect_finding_mail: String,
        show_comply_or_explain: Boolean,
        comply_or_explain_email_address: String,
        send_in_email_address: String,
    },

    methods: {
        show: function () {
            this.visible = true;
        },
        hide: function () {
            this.visible = false;
        },
        load: function (){}
    },
});
</script>
