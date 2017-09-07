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
    this._div.innerHTML = '<h4>Map information</h4>' +  (metadata ?
            '<br />' + metadata.data_from_time + ''
            : '');

};
metadata.addTo(map);


var info = L.control();

info.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
};

info.update = function (props) {
    var sometext = "<h4>Failure of your overlords</h4>";

    if (props) {
        sometext += '<br /><b>Gemeente: </b>' + props.OrganizationName + '' +
            '<br /><b>Overall Grade: </b><span style="color: '+getColor(props.Overall)+'">' + props.Overall + '</span>' +
            '<br /><br /><b>Data from: </b>' + props.DataFrom + '';
        domainsDebounced(props.OrganizationID);
    } else {
        sometext += 'Move your mouse over the map and cry...';
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

var domainsDebounced = debounce(function(x) {
    $.getJSON('/data/report/' + x, function (data) {
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

function loadmap(weeknumber){
    $.getJSON('/data/map/' + weeknumber, function(json) {

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

// reloads the map and the top fail every hour, so you don't need to manually refresh anymore
var hourly = false;
function update_hourly() {
    if (hourly){
        loadmap(0); // todo: also set the timeslider to 0 again.
        loadtopfail();
        $("#history").val(0);
    }
    hourly = true; // first time don't run the code, so nothing surprising happens
    setTimeout(update_hourly,60*60*1000);
}



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
            idizetag: function (url){
                url = url.toLowerCase();
               return "#" + url.replace(/[^0-9a-z]/gi, '')
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
                    Math.round(this.data.data.now["green"] / this.data.data.now["total_organizations"] * 100) + "%";
            },

            redpercentage: function() {
                return (!this.data.data) ? "0%" :
                    Math.round(
                        ( this.data.data.now["red"]) / this.data.data.now["total_organizations"] * 100) + "%";
            },

            orangepercentage: function() {
                return (!this.data.data) ? "0%" :
                    Math.round(
                        (this.data.data.now["orange"]) / this.data.data.now["total_organizations"] * 100) + "%";
            },

            unknownpercentage: function() {
                return (!this.data.data) ? "0%" :
                    Math.round(this.data.data.now["no_rating"] / this.data.data.now["total_organizations"] * 100) + "%";
            }
        }
    });

    // move space and time ;)
    $("#history").on("change input", debounce(function() {
        loadmap(this.value);
        loadtopfail(this.value)
        loadstats(this.value);
    }, 250));

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
                location.hash = "#yolo"; // you can only jump once to an anchor, unless you use a dummy
                location.hash = "#report";
                $.getJSON('/data/report/' + OrganizationID, function (data) {
                    thingsdata = JSON.parse(data.calculation);
                    vueReport.urls = thingsdata["organization"]["urls"];
                    vueReport.points = data.rating;
                    vueReport.when = data.when;
                    vueReport.name = data.name;
                });
            }
        }
    });

    loadtopfail(0);
    loadstats(0);

});


function loadtopfail(weeknumber){
        $.getJSON('/data/topfail/' + weeknumber, function(data) {
        vueTopfail.top = data;
    });
}

function loadstats(weeknumber){
    $.getJSON('/data/stats/' + weeknumber, function(data) {
        vueStatistics.data = data;
    });
}

// we chose vue because of this:
// https://hackernoon.com/angular-vs-react-the-deal-breaker-7d76c04496bc
// also: reacts patent clause and mandatory jsx syntax ... NO
// The amount of components available for vue is limited. But we can mix it with traditional scripts
// Javascript will not update the values when altering the data, javascript cannot observe that.
function showreport(e){
    location.hash = "#yolo"; // you can only jump once to an anchor, unless you use a dummy
    location.hash = "#report";
    var layer = e.target;
    $.getJSON('/data/report/' + layer.feature.properties['OrganizationID'], function(data) {
        thingsdata = JSON.parse(data.calculation);
        vueReport.urls = thingsdata["organization"]["urls"];
        vueReport.points = data.rating;
        vueReport.when = data.when;
        vueReport.name = data.name;
    });

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