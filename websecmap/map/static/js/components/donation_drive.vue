{% verbatim %}
<style>
    .donation_drive a, .donation_drive a:hover, .donation_drive a:visited {
        text-decoration: underline;
    }

</style>

<template type="x-template" id="donation_drive_template">
    <modal v-if="show_donation_drive" @close="stop()" class="donation_drive">
            <h3 slot="header">{{ $t("title") }} $CAMPAIGN</h3>

            <div slot="body">

                <p>
                    Basisbeveiliging biedt een vrij toegankelijke bron van informatie rondom beveiliging van
                    de overheid. Dit wordt samengesteld door een team van vrijwilligers.
                </p>

                <p>
                    Deze informatie hoort vrij beschikbaar en actueel te zijn. Dat is een behoorlijke klus.
                </p>
                <p>
                    In 2020 willen we meer aandacht besteden aan actuele scanresultaten en afhandelen van meldingen.
                    Hiervoor willen we minder afhankelijk zijn van vrijwilligers, en meer zekerheid bieden naar de bezoekers.
                    Doneer aan Basisbeveiliging en help mee aan een veiliger internet.
                </p>

                <h4>Een gepast bedrag</h4>
                <p>
                    Het donatiebedrag is vrij te kiezen. Om het makkelijk te maken suggereren we een donatie.
                    Als je geen vaste bezoeker bent van de site, en toch het initiatief wil steunen, dan suggereren
                    we een donatie van 2 euro. <a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/2/">Deze kan je hier overmaken</a>.
                </p>
                <p>
                    Organisaties die op deze website worden genoemd vragen we om een bijdrage die bij de grootte van de
                    organisatie past. Deze bijdrage wordt per organisatie berekend aan de hand van de online voetafdruk.
                </p>
                <h4>Voor welke organisatie wil je doneren?</h4>
                <v-select label="name"
                          v-model="selected"
                          :options="possible_organizations"
                          :placeholder="$t('report.select_organization')"
                ></v-select>

                <pre>
                $organization_name              amount  donation    total
                - Internet addresses:           400     0.20        80
                - Services:                     780     0.05        39
                - Scans / metrics:              4680    0.01        46
                - basic support                 1       100         100

                Suggested donation amount:                          265
                </pre>

                <p>Met de onderstaande link is het mogelijk om dit bedrag te doneren.</p>

                <button class="btn btn-success" href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/265/">Doneer €265</button>
                (<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/">of kies zelf een bedrag, hier</a>)

            </div>
            <div slot="footer">
                <button type="button" class="btn btn-primary" @click="stop()">Bedankt voor je donatie!</button>
            </div>
        </modal>
</template>
{% endverbatim %}

<script>
const DonationDrive = Vue.component('donation_drive', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                title: "Donation Drive",
                intro: "",
            },
            nl: {
                title: "Donatieronde",
                intro: "",
            }
        },
    },
    template: "#donation_drive_template",
    mixins: [new_state_mixin, translation_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            loading: false,

            show_donation_drive: false,
            possible_organizations: [],

            selected: {},

        }
    },

    props: {},

    methods: {
        load: function () {
            this.loading = true;
            fetch(`/data/organizations/list/${this.$store.state.country}/${this.$store.state.layer}/`).then(response => response.json()).then(data => {
                this.possible_organizations = data;
                this.loading = false;
            }).catch((fail) => {console.log('An error occurred in combined number statistics: ' + fail); throw fail});
        },

        start: function(){
            this.show_donation_drive = true;
        },
        stop: function(){
            // reset everything.
            this.show_donation_drive = false;
        },

    },
});
</script>
