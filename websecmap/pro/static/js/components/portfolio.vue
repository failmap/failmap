{% verbatim %}
<template type="x-template" id="portfolio_template">
    <div>
        <h1>Portfolio</h1>
        <div id="urllists"></div>

        <div>
            <main><section>

            <div class="loading" v-if="loading"><i class="fas fa-spinner fa-pulse"></i></div>

            <div style="margin-bottom: 60px;" v-for="urllist in urllists">

                <div style="padding: 20px; background-color: rgba(225, 225, 225, 0.42); border-radius: 10px;">
                    <h2>{{ urllist.name }}</h2>

                    <br><br>

                    <h3>Quick actions</h3>
                    <div>
                        <a role="button" class="btn btn-danger btn-lg" :href="'/pro/issues/' + urllist.name_slug + '/'">Manage Issues</a>
                        <a role="button" class="btn btn-success btn-lg" :href="'/pro/issues/' + urllist.name_slug + '/'">Add Urls</a>
                    </div>

                    <br><br>

                    <h3>Timelines</h3>
                    <div class="chart-container" style="position: relative; height:300px; width:100%">
                        <vulnerability-chart :data="urllist.stats"></vulnerability-chart>
                    </div>

                    <div class="chart-container" style="position: relative; height:300px; width:100%">
                        <connectivity-chart :data="urllist.stats"></connectivity-chart>
                    </div>

                    <br><br>

                    <h3>Urls</h3>
                    <p>This is a list of all urls in your portfolio, it includes urls where we might not have discovered services.
                    Some Urls might be listed as being removed. This happens with urls that use wildcard DNS systems.</p>
                    <table class="table table-sm table-striped table-bordered table-hover">
                    <thead>
                    </thead>
                    <tbody>
                        <tr v-if="urllist.urls">
                            <th>Url</th>
                            <th>Created on</th>
                            <th>Resolvable</th>
                            <th>Removed</th>
                        </tr>

                        <!-- todo: this will be the summary table -->
                        <tr v-for="url in urllist.urls">
                            <td>{{ url.url }}</td>
                            <td>{{ url.created_on }} </td>
                            <td>{{ url.resolves }}</td>
                            <td>{{ url.is_dead }}</td>
                        </tr>
                    </tbody>
                    </table>
                </div>
            </div>
                </section>
                </main>
        </div>
    </div>
</template>
{% endverbatim %}

<script>
// Inspiration from https://github.com/apertureless/vue-chartjs/blob/develop/dist/vue-chartjs.js
// and various blogposts, reduced it to a very very simple example.
Vue.component('vulnerability-chart', {
    props: {
        data: {type: Array, required: true}
    },
    render: function(createElement) {
        return createElement(
            'canvas',
            {
                ref: 'canvas'
            },
        )
    },
    mounted: function () {
        this.renderChart();
    },
    methods: {
        renderChart: function(){
            let data = this.data;

            let labels = Array();
            let high = Array();
            let medium = Array();
            let low = Array();

            let urls = Array();
            let endpoints = Array();

            for(let i=0; i<data.length; i++){
                labels.push(data[i].date);
                high.push(data[i].high);
                medium.push(data[i].medium);
                low.push(data[i].low);
                urls.push(data[i].urls);
                endpoints.push(data[i].endpoints);
            }


            let context = this.$refs.canvas.getContext('2d');
            new Chart(context, {
                type: 'line',
                data: {
                    labels: labels,

                    datasets: [{
                        label: '# High risk',
                        data: high,
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        borderColor: 'rgba(255,99,132,1)',
                        borderWidth: 1,
                        lineTension: 0
                    },
                    {
                        label: '# Medium risk',
                        data: medium,
                        backgroundColor: 'rgba(255, 102, 0, 0.2)',
                        borderColor: 'rgba(255,102,0,1)',
                        borderWidth: 1,
                        lineTension: 0
                    },
                    {
                        label: '# Low risk',
                        data: low,
                        backgroundColor: 'rgba(255, 255, 0, 0.2)',
                        borderColor: 'rgba(255,255,0,1)',
                        borderWidth: 1,
                        lineTension: 0
                    },
                    ]
                },
                options: {
                    legend: {
                        display: false
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    title: {
                        display: true,
                        text: 'Vulnerabilities over time'
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
                            stacked: true,
                            scaleLabel: {
                                display: false,
                                labelString: 'Value'
                            }
                        }]
                    }
                }
            });
        }
    }
});

Vue.component('connectivity-chart', {
    props: {
        data: {type: Array, required: true}
    },
    render: function(createElement) {
        return createElement(
            'canvas',
            {
                ref: 'canvas'
            },
        )
    },
    mounted: function () {
        this.renderChart();
    },
    methods: {
        renderChart: function(){
            let data = this.data;

            let labels = Array();
            let high = Array();
            let medium = Array();
            let low = Array();

            let urls = Array();
            let endpoints = Array();

            for(let i=0; i<data.length; i++){
                labels.push(data[i].date);
                high.push(data[i].high);
                medium.push(data[i].medium);
                low.push(data[i].low);
                urls.push(data[i].urls);
                endpoints.push(data[i].endpoints);
            }


            let context = this.$refs.canvas.getContext('2d');
            new Chart(context, {
                type: 'line',
                data: {
                    labels: labels,

                    datasets: [{
                        label: '# Internet Adresses',
                        data: urls,
                        backgroundColor: 'rgba(0, 0, 0, 0.2)',
                        borderColor: 'rgba(0,0,0,1)',
                        borderWidth: 1,
                        lineTension: 0
                    },
                    {
                        label: '# Services',
                        data: endpoints,
                        backgroundColor: 'rgba(0, 40, 255, 0.2)',
                        borderColor: 'rgba(0,40,255,1)',
                        borderWidth: 1,
                        lineTension: 0
                    },
                    ]
                },
                options: {
                    legend: {
                        display: false
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
        }
    }
});


Vue.component('portfolio', {
    i18n: { // `i18n` option, setup locale info for component
        messages: {
            en: {
                portfolio: {
                    title: "Portfolio",

                }
            },
            nl: {
                portfolio: {
                    title: "Portfolio",
                }
            }
        },
    },
    template: "#portfolio_template",
    mixins: [credits_mixin],

    mounted: function () {
        this.load(0)
    },

    data: function () {
        return {
            urllists: [],
            loading: true,
        }
    },

    props: {
        issues: Array,
        color_scheme: Object,
    },

    methods: {
        load: function(){
            this.loading = true;
            fetch(`/pro/data/portfolio/`).then(response => response.json()).then(data => {
                this.urllists = data;
                this.loading = false;
                // tocbot.refresh();
            }).catch((fail) => {
                console.log('A loading error occurred: ' + fail);
            });
        },
    },
});
</script>
