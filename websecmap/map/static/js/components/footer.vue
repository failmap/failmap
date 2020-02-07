{% verbatim %}
<style>

    .footer a, .footer a:hover, .footer a:visited {
        color: #d9d9d9;
        text-decoration: none;
        font-size: 12px;
    }

    .footer {
        font-size: 12px;
    }

    .banner {
        background-color: #f2f2f2;
        border-radius: 40px;
        height: 28px;
        display: block;
        text-align: center;
        padding-top: 5px;
        width: 211px;
        color: #423c3c !important;
    }

</style>
<template type="x-template" id="foot_template">
    <div class="row footer">
        <div class="col-md-4 info">
            <a v-if="config.project.name.length > 1" target="_blank"><b>{{ config.project.name }}</b></a><br />
            <i v-if="config.project.tagline.length > 1"><a target="_blank">{{ config.project.tagline }}</a></i><br />
            <i v-if="config.project.mail.length > 1"><a :href="'mailto:'+config.project.mail" target="_blank">📯 {{ config.project.mail }}</a></i>
        </div>

        <div class="col-md-4 info">
            <b v-if="config.responsible_organization.name.length > 1"><a :href="config.responsible_organization.website" target="_blank" rel="noopener">{{ config.responsible_organization.name }}</a></b><br />
            <i v-if="config.responsible_organization.website.length > 1"><a :href="config.responsible_organization.website" target="_blank" rel="noopener">{{ config.responsible_organization.website }}</a></i><br />
            <i v-if="config.responsible_organization.mail.length > 1"><a :href="'mailto:' + config.responsible_organization.mail" target="_blank" rel="noopener">📯{{ config.responsible_organization.mail }}</a></i>
        </div>
        <div class="col-md-3 info" style="text-align: right">
            <a href="https://websecuritymap.org" target="_blank" rel="nofollow" class="banner">
                <img src="/static/images/web-security-map-logo-small.png" alt="logo" width="20px"/>️ {{ $t("footer.banner") }}
            </a>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('foot', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                footer: {
                    general_inquiry: "General inquiry",
                    feedback: "Feedback",
                    social_media: "Also on social media",
                    comply_or_explain: "Comply or explain",

                    // 2nd column
                    banner: "Made with Web Security Map",
                    get_source: "Get the sourcecode",
                    documentation: "Documentation",

                    // 3rd column
                    made_possible_by: "Made possible by",

                    // 4th column
                    contact: "Contact",
                    website_run_by: "This website is run by:"
                }
            },
            nl: {
                footer: {
                    general_inquiry: "Algemene contactgegevens",
                    feedback: "Feedback",
                    social_media: "Ook op social media",
                    comply_or_explain: "Pas toe of leg uit",

                    // 2nd column
                    banner: "Gemaakt met Web Security Map",
                    get_source: "Download de broncode",
                    documentation: "Documentatie",

                    // 3rd column
                    made_possible_by: "Mogelijk gemaakt door",

                    // 4th column
                    contact: "Contact",
                    website_run_by: "Deze site wordt gedraaid door:"
                }
            }
        },
    },
    template: "#foot_template",

    data: function () {
        return {
        }
    },

    props: {
        config: Object
    },
});
</script>
