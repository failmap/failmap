// Currently we're migrating to Vue.

// We chose vue because of this:
// https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc
// also: reacts patent clause and mandatory jsx syntax ... NO
// The amount of components available for vue is limited. But we can mix it with traditional scripts
// Javascript will not update the values when altering the data, javascript cannot observe that.


//                              Y     X
var map = L.map('map').setView([52.15, 5.8], 8);
map.scrollWheelZoom.disable();

// mapbox handles 1600 visitors a day, for static data. Fortunately we can A cache the request, B use another map provider,
// C the map looks fine without tiles. Paying 500 a month for max 1M visitors still sucks. Ideal case is local tiles.
// and real open streetmaps.

L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token=pk.eyJ1IjoibXJmYWlsIiwiYSI6ImNqMHRlNXloczAwMWQyd3FxY3JkMnUxb3EifQ.9nJBaedxrry91O1d90wfuw', {
    maxZoom: 18,
    attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
    '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
    'Imagery © <a href="http://mapbox.com">Mapbox</a>',
    id: 'mapbox.light'
}).addTo(map);

// control that shows state info on hover
var metadata = L.control();
metadata.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
};
metadata.update = function (metadata) {
    this._div.innerHTML = '' +  (metadata ?
            '<h4>' + new Date(metadata.data_from_time).humanTimeStamp() + '</h4>' : '<h4></h4>');
};
metadata.addTo(map);


var info = L.control();

info.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
};

info.update = function (props) {
    var sometext = "";
    if (props) {
        sometext += "<h4>" + props.OrganizationName +"</h4>";
        sometext += '<b>Score: </b><span style="color: '+getColor(props.Overall)+'">' + props.Overall + ' points</span>';
        domainsDebounced(props.OrganizationID, $("#history")[0].value);
    } else {
        sometext += "<h4>-</h4>";
        sometext += '<b>Score: </b><span>- points</span>';
    }

    this._div.innerHTML = sometext;
};

info.addTo(map);


// get color depending on population density value
function getColor(d) {
    return  d > 399 ? '#bd383c' :
            d > 99  ? '#fc9645' :
            d > -1  ? '#62fe69' :
                      '#c1bcbb';
}

function style(feature) {
    return {
        weight: 2,
        opacity: 1,
        color: 'white',
        dashArray: '3',
        fillOpacity: 0.7,
        fillColor: getColor(feature.properties.Overall)
    };
}

function highlightFeature(e) {
    var layer = e.target;

    layer.setStyle({
        weight: 5,
        color: '#ccc',
        dashArray: '',
        fillOpacity: 0.7
    });

    if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
        layer.bringToFront();
    }

    info.update(layer.feature.properties);
}

var domainsDebounced = debounce(function(organization, weeks_back) {
    if (!weeks_back)
        weeks_back = 0;

    $.getJSON('/data/report/' + organization + '/' + weeks_back, function (data) {
        var thingsdata = JSON.parse(data.calculation);
        vueDomainlist.urls = thingsdata["organization"]["urls"];
    });
}, 100);

function debounce(func, wait, immediate) {
	var timeout;
	return function() {
		var context = this, args = arguments;
		clearTimeout(timeout);
		timeout = setTimeout(function() {
			timeout = null;
			if (!immediate) func.apply(context, args);
		}, wait);
		if (immediate && !timeout) func.apply(context, args);
	};
}


var geojson;

function resetHighlight(e) {
    geojson.resetStyle(e.target);
    info.update();
}

function zoomToFeature(e) {
    map.fitBounds(e.target.getBounds());
}

function gotoLink(e){
    var layer = e.target;
    location.hash = "#" + layer.feature.properties['OrganizationName'];
}

// cache the requests on the client, so you can slide faster.
// the cache is valid about a week...
// only at weeknumber 0 we don't use cache, otherwise hourly updates don't work
// caching doesnt really work: returned data is severly altered and copy by value is messy.
// array.slice, but what if it's an object? then json things. Nope.
// also checking a weeknumber by this is meh: weeknumber !== '0'
// this is much simpler.
function loadmap(weeknumber){
    $.getJSON('/data/map/' + weeknumber, function (json) {
        if (geojson) { // if there already was data present
            geojson.clearLayers(); // prevent overlapping polygons
            map.removeLayer(geojson);
        }

        geojson = L.geoJson(json, {
            style: style,
            onEachFeature: onEachFeature
        }).addTo(map);

        // todo: add the date info on the map, or somewhere.
        metadata.update(json.metadata);
    });
}


function loadtopfail(weeknumber){
    $.getJSON('/data/topfail/' + weeknumber, function (data) {
        vueTopfail.top = data;
    });
}


function loadstats(weeknumber){
    $.getJSON('/data/stats/' + weeknumber, function(data) {
        vueStatistics.data = data;
    });
}



// reloads the map and the top fail every hour, so you don't need to manually refresh anymore
var hourly = false;
function update_hourly() {
    if (hourly){
        loadmap(0);
        loadtopfail(0);
        $("#history").val(0);
    }
    hourly = true; // first time don't run the code, so nothing surprising happens
    setTimeout(update_hourly,60*60*1000);
}


// support for week numbers in javascript
// https://stackoverflow.com/questions/7765767/show-week-number-with-javascript
Date.prototype.getWeek = function() {
        var onejan = new Date(this.getFullYear(), 0, 1);
        return Math.ceil((((this - onejan) / 86400000) + onejan.getDay() + 1) / 7);
};

// support for an intuitive timestamp
// translation?
Date.prototype.humanTimeStamp = function() {
    return this.getFullYear() + " Week " + this.getWeek();
};

// https://stackoverflow.com/questions/15762768/javascript-math-round-to-two-decimal-places
function roundTo(n, digits) {
     if (digits === undefined) {
       digits = 0;
     }

     var multiplicator = Math.pow(10, digits);
     n = parseFloat((n * multiplicator).toFixed(11));
     var test =(Math.round(n) / multiplicator);
     return +(test.toFixed(digits));
   }

// todo: add some browser cache for datasets from server :) So it feels even faster.
// possibly just completely caching it on the client after a while... because.. why not.

$( document ).ready(function() {
    loadmap(0);

    // perhaps make it clear in the gui that it auto-updates? Who wants a stale map for an hour?
    // a stop/play doesn't work, as there is no immediate reaction, countdown perhaps? bar emptying?
    update_hourly();

    window.vueReport = new Vue({
        el: '#report',
        data: {
            calculation: '',
            rating: 0,
            when: 0,
            name: "",
            urls: Array
        },
        filters: {
            // you cannot run filters in rawHtml, so this doesn't work.
            // therefore we explicitly do this elsewhere
        },
        methods: {
            colorize : function (points) {
                if (points < 100) return "green";
                if (points < 400) return "orange";
                if (points > 399) return "red";
            },
            idize: function (url){
                url = url.toLowerCase();
               return url.replace(/[^0-9a-z]/gi, '')
            },
            idizetag: function (url) {
                url = url.toLowerCase();
                return "#" + url.replace(/[^0-9a-z]/gi, '')
            },
            humanize: function(date){
                return new Date(date).humanTimeStamp()
            }
        }
    });

    window.vueStatistics = new Vue({
        el: '#statistics',
        data: {
            data: Array
        },
        computed: {
            greenpercentage: function() {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["green"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
            },

            redpercentage: function() {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["red"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
            },

            orangepercentage: function() {
                return (!this.data.data) ? "0%" :
                    Math.floor(roundTo(this.data.data.now["orange"] / this.data.data.now["total_organizations"] * 100, 2)) + "%";
            },

            unknownpercentage: function() {
                return (!this.data.data) ? "0%" :
                    roundTo(this.data.data.now["no_rating"] / this.data.data.now["total_organizations"] * 100, 2) + "%";
            }
        }
    });

    window.vueDomainlist = new Vue({
        el: '#domainlist',
        data: { urls: Array },
        methods: {
            colorize: function (points) {
                if (points < 100) return "green";
                if (points < 400) return "orange";
                if (points > 399) return "red";
            }
        }
    });

    window.vueTopfail = new Vue({
        el: '#topfail',
        data: { top: Array },
        methods: {
            showReport: function (OrganizationID) {
                jumptoreport();
                showReportData(OrganizationID, $("#history")[0].value);
                domainsDebounced(OrganizationID, $("#history")[0].value);
            },
            humanize: function(date){
                return new Date(date).humanTimeStamp()
            }
        }
    });

    window.vueHistory = new Vue({
        el: '#historycontrol',
        data: {
            weeksback: 0

        },
        computed: {
            visibleweek: function() {
                x = new Date();
                x.setDate(x.getDate() - this.weeksback * 7);
                return x.humanTimeStamp();
            }
        }
    });

    // move space and time ;)
    $("#history").on("change input", debounce(function() {
        loadmap(this.value);
        loadtopfail(this.value);

        if (selected_organization > -1){
            showReportData(selected_organization, this.value);
            domainsDebounced(selected_organization, this.value);
        }

        //loadstats(this.value); // todo: cache
        vueHistory.weeksback = this.value;
    }, 100));

    loadtopfail(0);
    loadstats(0);

});

selected_organization = -1;

function showReportData(OrganizationID, weeks_ago){
    selected_organization = OrganizationID;

    if (!weeks_ago) {
        weeks_ago = 0;
    }

    $.getJSON('/data/report/' + OrganizationID + '/' + weeks_ago, function (data) {
        thingsdata = JSON.parse(data.calculation);
        vueReport.urls = thingsdata["organization"]["urls"];
        vueReport.points = data.rating;
        vueReport.when = data.when;
        vueReport.name = data.name;
    });
}

function jumptoreport(){
    location.hash = "#yolo"; // you can only jump once to an anchor, unless you use a dummy
    location.hash = "#report";
}

function showreport(e){
    jumptoreport();
    var layer = e.target;
    showReportData(layer.feature.properties['OrganizationID'], $("#history")[0].value);
}




function onEachFeature(feature, layer) {
    layer.on({
        mouseover: highlightFeature,
        mouseout: resetHighlight,
        click: showreport
    });
}



map.attributionControl.addAttribution('Ratings &copy; <a href="http://faalkaart.nl/">Fail Map</a> <a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>');


var legend = L.control({position: 'bottomright'});

legend.onAdd = function (map) {

    var div = L.DomUtil.create('div', 'info legend'), labels = [];

    labels.push('<i style="background:' + getColor(0) + '"></i> Good');
    labels.push('<i style="background:' + getColor(200) + '"></i> Average');
    labels.push('<i style="background:' + getColor(400) + '"></i> Bad');
    labels.push('<i style="background:' + getColor("-") + '"></i> Unknown');

    div.innerHTML = labels.join('<br>');
    return div;
};

legend.addTo(map);