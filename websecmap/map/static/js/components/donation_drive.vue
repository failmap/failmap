{% verbatim %}
<style>
    .donation_drive a, .donation_drive a:hover, .donation_drive a:visited {
        text-decoration: underline;
    }

    a.btn.btn-primary.lightlink, a.btn.btn-primary.lightlink:hover, a.btn.btn-primary.lightlink:visited, a.btn.btn-primary.lightlink:active {
        color: white;
    }

</style>

<template type="x-template" id="donation_drive_template">
    <modal v-if="show_donation_drive" @close="stop()" class="donation_drive">
            <h3 slot="header">Ondersteun basisbeveiliging.nl</h3>

            <div slot="body">

                <p>
                    Basisbeveiliging biedt een vrij toegankelijke bron van informatie rondom beveiliging van
                    de overheid. Deze informatie hoort vrij beschikbaar en actueel te zijn.
                </p>

                <p>
                    Een team van vrijwilligers vormt, samen met subsidies en donaties, de basis om deze site actueel
                    te houden. Dat is een behoorlijke klus waar nog verbetering nodig is.
                </p>

                <h4>Doneren</h4>
                <p>
                    Aan organisaties op de kaart vragen we een donatie tussen de &euro;0.25 en &euro;0.50 per domein per maand.
                </p>
                <p>
                    Gezien budgetten altijd complex zijn kunnen we ook werken met offertes, facturen, codes of een andere weg die bij uw organisatie past. Neem hiervoor <a href="mailto:info@internetcleanup.foundation?subject=donatie"> contact met ons op via deze link</a>.
                </p>

                <p>
                    Voor fans is het mogelijk om voor ongeveer &euro;5,- per maand bij te dragen.
                </p>
                <p>
                    <a class="btn btn-primary lightlink" style='text-decoration: underline' href="https://www.patreon.com/internetcleanupfoundation?fan_landing=true"><img height='24' src="/static/images/1200px-Patreon_logo.svg.png"> Steun maandelijks via Patreon</a><br>
                    <br>
                    <small>Algemene donaties gaan via Patreon voor de <i>Internet Cleanup Foundation</i> en <i>Web Security Map</i>.</small><br>
                </p>

                <h4>Vrijwilliger worden</h4>
                <p>
                    We zijn altijd op zoek naar meer mensen die ervoor zorgen dat de kaart actueel blijft. Hiervoor moet van alles gebeuren.
                    Ons team is klein en heeft uiteenlopende disciplines. We zijn verenigd in het veiliger maken van het internet.
                </p>
                <p>
                    <a class="btn btn-primary" style='text-decoration: underline' href="mailto:info@internetcleanup.foundation?subject=vrijwilligen">Word vrijwilliger, mail ons</a>
                </p>

                <h4>Waarom doneren of vrijwilligen?</h4>
                <ul>
                    <li>Het internet aantoonbaar veiliger maken</li>
                    <li>De kaart up to date houden met dagelijkse en wekelijkse scans</li>
                    <li>Verbeteren scanners, voor meer accurate resultaten</li>
                    <li>Oplossen van bugs</li>
                    <li>Het ontwikkelen van nieuwe functionaliteit</li>
                </ul>

            </div>
            <div slot="footer">
                <button type="button" class="btn btn-secondary" @click="stop()">sluiten</button>
            </div>
        </modal>
</template>
{% endverbatim %}

<script>
const DonationDrive = Vue.component('donation_drive', {
    store,
    template: "#donation_drive_template",

    mounted: function () {},

    data: function () {
        return {

        }
    },

    computed: {
        show_donation_drive: () => {
            return store.state.show_donation_drive
        }
    },

    methods: {
        start: function(){
            store.commit("show_donation_drive", true);
        },
        stop: function(){
            // reset everything.
            store.commit("show_donation_drive", false);
        },

    },
});
</script>
