{% verbatim %}
<template type="x-template" id="stats_composition_template">
    <div>
        <stats_high_level_graphs :issues="issues" :color_scheme="color_scheme"></stats_high_level_graphs>
        <stats_detailed_graphs :issues="issues" :color_scheme="color_scheme"></stats_detailed_graphs>
        <stats_services :issues="issues" :color_scheme="color_scheme"></stats_services>
    </div>
</template>
{% endverbatim %}

<script>
const StatsComposition = Vue.component('stats_composition', {
    template: "#stats_composition_template",
    mixins: [new_state_mixin, translation_mixin],

    props: {
        issues: Array,
        color_scheme: Object,
    }
});
</script>
