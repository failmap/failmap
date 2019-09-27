<script>
// todo: get language key, and make sure the correct translations are used in these grahs.
const chart_mixin = {
    props: {
        data: {type: Array, required: true},
        axis: {type: Array, required: false},
        color_scheme: {type: Object, required: false},
        translation: {type: Object, required: false},
    },
    data: function() {
        // [Vue warn]: The "data" option should be a function that returns a per-instance value in component definitions.
        // so what should i use then? No suggestion?
        return {
            chart: {}
        }
    },
    render: function(createElement) {
        return createElement(
            'canvas',
            {
                ref: 'canvas'
            },
        )
    },
    methods: {
        translate: function(key) {
            if (this.translation === undefined)
                return "";

            if (Object.keys(this.translation).length === 0)
                return "";

            return this.translation[key];
        }
    },
    mounted: function () {
        this.buildChart();
        this.renderData();
    },
    watch: {
        data: function(newsetting, oldsetting){
            this.renderData();
        },

        // Supports changing the colors of this graph ad-hoc.
        // charts.js is not reactive.
        color_scheme: function(newsetting, oldsetting){
            this.renderData();
        },

        translation: function(newsetting, oldsetting){
            this.renderData();
        },
    }
};

Vue.component('vulnerability-chart', {
    mixins: [chart_mixin],

    methods: {
        // let's see if we can do it even better.
        buildChart: function(){
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'line',
                data: {
                    datasets: []
                },
                options: {
                    legend: {
                        display: true
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: this.translate('title')
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                    scales: {
                        xAxes: [{
                            display: true,
                            type: 'time',
                            distribution: 'linear',
                            time: {
                                unit: 'month'
                            },
                            scaleLabel: {
                                display: false,
                                labelString: this.translate('xAxis_label'),
                            }
                        }],
                        yAxes: [{
                            display: true,
                            stacked: true,
                            scaleLabel: {
                                display: false,
                                labelString: this.translate('yAxis_label'),
                            }
                        }]
                    }
                }
            });
        },

        renderData: function(){
            let data = this.data;
            let possible_axis = ['high', 'medium', 'low', 'good'];

            let ax_data = {'labels': [], 'high': [], 'medium': [], 'low': [], 'good': []};

            for(let i=0; i<data.length; i++){
                ax_data['labels'].push(data[i].date);
                ax_data['high'].push(data[i].high);
                ax_data['medium'].push(data[i].medium);
                ax_data['low'].push(data[i].low);
                ax_data['good'].push(data[i].good);
            }

            this.chart.data.labels = ax_data['labels'];

            this.chart.data.datasets = [];
            possible_axis.forEach((ax) => {
                    if (this.axis.includes(ax)) {
                        this.chart.data.datasets.push(
                            {
                                label: this.translate(`amount_${ax}`),
                                data: ax_data[ax],
                                backgroundColor: this.color_scheme[`${ax}_background`],
                                borderColor: this.color_scheme[`${ax}_border`],
                                borderWidth: 1,
                                lineTension: 0,
                                hidden: !this.axis.includes(ax)
                            }
                        )
                    }
                }
            );

            this.chart.update();
        }
    }
});

// not because pie charts are useful, but because they look cool.
// https://www.businessinsider.com/pie-charts-are-the-worst-2013-6?international=true&r=US&IR=T
// https://www.datapine.com/blog/notorious-pie-charts/
Vue.component('vulnerability-donut', {
    mixins: [chart_mixin],

    methods: {

        buildChart: function(){
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'doughnut',
                data: {

                },
                options: {
                    legend: {
                        display: true
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: this.translate('title'),
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                }
            });

        },
        renderData: function(){
            let data = this.data;

            let labels = Array();
            let high = Array();
            let medium = Array();
            let low = Array();
            let ok = Array();

            high.push(data[data.length-1].high);
            medium.push(data[data.length-1].medium);
            low.push(data[data.length-1].low);
            ok.push(data[data.length-1].ok);

            let backgroundColor = [];
            let borderColor = [];
            let chartdata = [];

            if (this.axis.includes('high')){
                backgroundColor.push(this.color_scheme.high_background);
                borderColor.push(this.color_scheme.high_border);
                labels.push(this.translate('amount_high'));
                chartdata.push(high);
            }
            if (this.axis.includes('medium')){
                backgroundColor.push(this.color_scheme.medium_background);
                borderColor.push(this.color_scheme.medium_border);
                labels.push(this.translate('amount_medium'));
                chartdata.push(medium);

            }
            if (this.axis.includes('low')){
                backgroundColor.push(this.color_scheme.low_background);
                borderColor.push(this.color_scheme.low_border);
                labels.push(this.translate('amount_low'));
                chartdata.push(low);
            }

            // Only include OK in the donuts, not the graphs. Otherwise the graphs become unreadable (too much data)
            backgroundColor.push(this.color_scheme.good_background);
            borderColor.push(this.color_scheme.good_border);
            labels.push(this.translate('amount_good'));
            chartdata.push(ok);

            this.chart.data.labels = labels;
            this.chart.data.datasets = [{
                data: chartdata,
                backgroundColor: backgroundColor,
                borderColor: borderColor,
                borderWidth: 2,
                lineTension: 0,
            }];

            this.chart.update();
        }
    }
});

Vue.component('connectivity-chart', {
    mixins: [chart_mixin],

    methods: {
        buildChart: function() {
            let context = this.$refs.canvas.getContext('2d');
            this.chart = new Chart(context, {
                type: 'line',
                data: {

                },
                options: {
                    legend: {
                        display: true
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: 'Internet connectivity'
                    },
                    tooltips: {
                        mode: 'index',
                        intersect: false,
                    },
                    hover: {
                        mode: 'nearest',
                        intersect: true
                    },
                    scales: {
                        xAxes: [{
                            display: true,
                            type: 'time',
                            distribution: 'linear',
                            time: {
                                unit: 'month'
                            },
                            scaleLabel: {
                                display: false,
                                labelString: 'Month'
                            }
                        }],
                        yAxes: [{
                            display: true,
                            stacked: false,
                            scaleLabel: {
                                display: false,
                                labelString: 'Value'
                            },
                            ticks: {
                                min: 0,
                            }
                        }]
                    }
                }
            });
        },

        renderData: function(){
            let data = this.data;

            let labels = Array();

            let urls = Array();
            let endpoints = Array();

            for(let i=0; i<data.length; i++){
                labels.push(data[i].date);
                urls.push(data[i].urls);
                endpoints.push(data[i].endpoints);
            }

            this.chart.data.labels = labels;
            this.chart.data.datasets = [{
                label: '# Internet Adresses',
                data: urls,
                backgroundColor: this.color_scheme.addresses_background,
                borderColor: this.color_scheme.addresses_border,
                borderWidth: 2,
                lineTension: 0
            },
            {
                label: '# Services',
                data: endpoints,
                backgroundColor: this.color_scheme.services_background,
                borderColor: this.color_scheme.services_border,
                borderWidth: 2,
                lineTension: 0
            }];

            this.chart.update();
        }
    }
});
</script>
