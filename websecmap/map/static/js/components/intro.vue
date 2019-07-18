{% verbatim %}
<template type="x-template" id="intro_template">
    <div class="container theme-showcase" role="main">
        <a name="info" class="jumptonav"></a>
        <div class="jumbotron">
            <h1 class="display-4">
                <svg class="svg-inline--fa fa-info-circle fa-w-16" aria-hidden="true" data-prefix="fas" data-icon="info-circle" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" data-fa-i2svg=""><path fill="currentColor" d="M256 8C119.043 8 8 119.083 8 256c0 136.997 111.043 248 248 248s248-111.003 248-248C504 119.083 392.957 8 256 8zm0 110c23.196 0 42 18.804 42 42s-18.804 42-42 42-42-18.804-42-42 18.804-42 42-42zm56 254c0 6.627-5.373 12-12 12h-88c-6.627 0-12-5.373-12-12v-24c0-6.627 5.373-12 12-12h12v-64h-12c-6.627 0-12-5.373-12-12v-24c0-6.627 5.373-12 12-12h64c6.627 0 12 5.373 12 12v100h12c6.627 0 12 5.373 12 12v24z"></path></svg>
                {{ $t("intro.title") }}</h1>
            <p class="lead">{{ $t("intro.intro") }}</p>
            <p v-if="organization">{{ $t("intro.run_by", {organization: organization}) }}</p>
            <p v-if="organization_mail">{{ $t("intro.contact", {organization_mail: organization_mail}) }}</p>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('intro', {
    i18n: {
        messages: {
            en: {
                intro: {
                    title: "About this website",
                    intro: "This website displays how well security is applied by the government. The quality is displayed using a traffic light system: red means bad, green means great. Our goal is to improve security and privacy for everyone. Therefore this site only displays the simplest and cheapest tier of security issues. This should all be fine... right?",
                    run_by: "This website is run by %{organization}.",
                    contact: "To submit new domains, or ask questions, contact us via: %{organization_mail}.",
                }
            },
            nl: {
                intro: {
                    title: "Over deze website",
                    intro: "Deze website laat zien hoe goed de overheid veiligheid toepast op haar websites. De kleur geeft aan hoe goed dit wordt gedaan. Rood is slecht, groen is goed. Omdat we willen dat het internet veiliger wordt laten we alleen informatie zien over het aller simpelste beveiligingsniveau: hierdoor wordt het risico voor niemand groter, maar kan je toch zien of de veiligheid op orde is. Dit zou allemaal op orde moeten zijn... toch?",
                    run_by: "Deze website wordt onderhouden door %{organization}.",
                    contact: "Het insturen van domeinen, stellen van vragen et cetera kunt u doen op: %{organization_mail}"
                }
            }
        },
    },
    template: "#intro_template",

    data: function () {return {}},

    props: {
        organization: String,
        organization_mail: String,
    },
});
</script>
