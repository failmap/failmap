{% verbatim %}
<script>
Vue.component('plus_info', {
    i18n: {
        messages: {
            en: {
                tip: "Tip",
                alerts: "Receive an alert 🚨 on service degradation. Use our Plus+ service. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Click here to see all features!</a>",
                rescan: "This site is updated automatically. Re-scan now 🕵️ using our Plus+ service. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Click here to see all features!</a>",
                comply_or_explain: "Need to add an 💬 explanation to a finding? Use our Plus+ service. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Click here to see all features!</a>",
                plus: "With our Plus+ service you can get more out of this website. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Click here to see all features!</a>"
            },
            nl: {
                tip: "Tip",
                alerts: "Ontvang direct meldingen 🚨 bij verslechteringen met Basisbeveiliging+. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Meer weten? Kijk hier!</a>",
                rescan: "Er wordt regelmatig gescand. Meteen opnieuw scannen? 🕵️ Gebruik Basisbeveiliging+. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Klik hier voor meer handige tools</a>",
                comply_or_explain: "Een 💬 verklaring toevoegen of aanpassen? Gebruik Basisbeveiliging+ <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Klik hier voor meer handige tools</a>",
                plus: "In control zijn op veiligheid en privacy met Basisbeveiliging+. <a style='text-decoration: underline' href='https://plus.basisbeveiliging.nl' target='_blank' rel='nofollow'>↗️ Klik hier voor meer handige tools</a>"
            }
        }
    },

    methods: {
        random_announcement: function() {
            let announcements = [
                'alerts', 'rescan', 'comply_or_explain', 'plus'
            ];

            return announcements[Math.floor(Math.random() * announcements.length)]
        }
    },

    template: `<div class="alert alert-success" v-if="$store.state.config.show.plus_info">
    ℹ️ {{ $t('tip') }}: <span v-html='$t(random_announcement())'></span>
</div>`,
});
</script>
{% endverbatim %}
