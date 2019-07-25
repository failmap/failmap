{% verbatim %}
<template type="x-template" id="ticker_template">
    <div id="ticker" v-cloak>
        <div id="ticker_bar">
            <p id="marquee" class="marquee very-huge"><span v-html="get_tickertext()"></span></p>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
Vue.component('ticker', {
    store,
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                ticker: {
                   perfect: "PERFECT",
                }
            },
            nl: {
                ticker: {
                   perfect: "PERFECT",
                }
            }
        },
    },
    template: "#ticker_template",
    mixins: [new_state_mixin],

    data: function () {
        return {
            tickertext: "",

            changes: Array(),
            slogan: ""
        }
    },

    methods: {
        setMarqueeSpeed: function (){
            // Time = Distance/Speed
            // https://stackoverflow.com/questions/38118002/css-marquee-speed
            // todo: use the virtual dom instead of real dom...
            try {
                var spanSelector = document.getElementById("marquee").querySelector("span");
                var timeTaken = this.tickertext.length / 20;  // about N characters per second.
                spanSelector.style.animationDuration = timeTaken + "s";
            } catch(err) {
                console.log("Marquee was not visible in the DOM.")
                // Weird is that when the property is set when hiding... it isn't stored. probably
                // because it affects the real dom only, not the virtual dom.
            }
        },
        colorize: function (value, rank) {
            if (value === 0)
                return "black";

            if (rank === "high")
                return "high";

            if (rank === "medium")
                return "medium";

            if (rank === "low")
                return "low";

            return "good";
        },
        arrow: function(value, rank){
            if (value > 0)
                return "<a class='high'>▲</a>+"+ value + " ";
            if (value === 0)
                return "▶0";
            if (value < 0)
                return "<a class='good'>▼</a>-" + (value * -1) + " ";
        },
        get_tickertext: function() {
            // weird that this should be a function...
            return this.tickertext;
        },
        load: function () {

            if (!this.country || !this.layer)
                return;


            fetch('/data/ticker/' + this.country + '/' + this.layer + '/0/0').then(response => response.json()).then(data => {

                // reset the text for the new data.
                this.tickertext = "";

                this.changes = data.changes;
                this.slogan = data.slogan;

                for (let j=0; j<this.changes.length; j++){
                    let change = this.changes[j];

                    this.tickertext += " &nbsp; &nbsp; " + change['organization'].toUpperCase() + " &nbsp; ";

                    if (!change['high_now'] && !change['medium_now'] && !change['low_now']){

                        this.tickertext += "<span class='goodrow' title='---------------------------------------" +
                            "------'>PERFECT</span>  ";

                    } else {

                        this.tickertext += "<span class='" + this.colorize(change['high_now'], 'high') + "row'>" + change['high_now'] + "</span>";
                        this.tickertext += this.arrow(change['high_changes'], 'high');
                        this.tickertext += " &nbsp; ";

                        this.tickertext += "<span class='" + this.colorize(change['medium_now'], 'medium') + "row'>" + change['medium_now'] + "</span>";
                        this.tickertext += this.arrow(change['medium_changes'], 'medium');
                        this.tickertext += " &nbsp; ";

                        this.tickertext += "<span class='" + this.colorize(change['low_now'], 'low') + "row'>" + change['low_now'] + "</span>";
                        this.tickertext += this.arrow(change['low_changes'], 'low');
                        this.tickertext += "  ";

                    }

                    if (j % 10 === 0) {
                        this.tickertext += " &nbsp; &nbsp; <b> " + this.slogan.toUpperCase() + " </b> &nbsp; "
                    } else {
                        // show space between each rating, except the first / after the closing message
                        this.tickertext += " &nbsp; ";
                    }
                }

                this.setMarqueeSpeed()

            }).catch((fail) => {console.log('A Ticker error occurred: ' + fail)});
        }
    },

    watch: {
        visibility: function(){
            // evil fix.
            setTimeout(function(){ vueTicker.setMarqueeSpeed()}, 2000);
        }
    }
});

</script>
