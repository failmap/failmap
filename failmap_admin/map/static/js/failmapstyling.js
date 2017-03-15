// todo: create auto update feature...
//                              Y     X
var map = L.map('map').setView([52.15, 5.8], 8);

// mapbox handles 1600 visitors a day, for static data. Fortunately we can A cache the request, B use another map provider,
// C the map looks fine without tiles. Paying 500 a month for max 1M visitors still sucks. Ideal case is local tiles.

L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpandmbXliNDBjZWd2M2x6bDk3c2ZtOTkifQ._QA7i5Mpkd_m30IGElHziw', {
    maxZoom: 18,
    attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
    '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
    'Imagery © <a href="http://mapbox.com">Mapbox</a>',
    id: 'mapbox.light'
}).addTo(map);

// control that shows state info on hover
var info = L.control();

info.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
};

info.update = function (props) {
    this._div.innerHTML = '<h4>Failure of your overlords</h4>' +  (props ?
            '<br /><b>Gemeente: </b><span style="color: '+getColor(props.Overall)+'">' + props.OrganizationName + '</span>' +
            '<br /><b>Overall Grade: </b><span style="color: '+getColor(props.Overall)+'">' + props.Overall + '</span>' +
            '<br /><br /><b>TLS: </b><span style="color: '+getColor(props.TLS)+'">' + props.TLS +'</span>' +
            '<br /><br />Click for more information...'
            : 'Move your mouse over the map and cry...');
};

info.addTo(map);


// get color depending on population density value
function getColor(d) {
    return d == "F" ? '#bd0611' :
        d == "D"  ? '#bd4f4a' :
            d == "C"  ? '#fca87c' :
                d == "B"  ? '#fcc25a' :
                    d == "A-"   ? '#94fe7f' :
                        d == "A"   ? '#94fe7f' :
                            d == "A+"   ? '#25fe20' :
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
        color: '#666',
        dashArray: '',
        fillOpacity: 0.7
    });

    if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) {
        layer.bringToFront();
    }

    info.update(layer.feature.properties);
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

function onEachFeature(feature, layer) {
    layer.on({
        mouseover: highlightFeature,
        mouseout: resetHighlight,
        click: gotoLink
    });
}

geojson = L.geoJson(statesData, {
    style: style,
    onEachFeature: onEachFeature
}).addTo(map);


map.attributionControl.addAttribution('Ratings &copy; <a href="http://faalkaart.nl/">Fail Map</a> <a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>');


var legend = L.control({position: 'bottomright'});

legend.onAdd = function (map) {

    var div = L.DomUtil.create('div', 'info legend'), labels = [];

    labels.push('<i style="background:' + getColor("A+") + '"></i> Perfect');
    labels.push('<i style="background:' + getColor("A") + '"></i> Good');
    labels.push('<i style="background:' + getColor("A-") + '"></i> OK');
    labels.push('<i style="background:' + getColor("B") + '"></i> Substandard');
    labels.push('<i style="background:' + getColor("C") + '"></i> Crappy');
    labels.push('<i style="background:' + getColor("D") + '"></i> Terrible');
    labels.push('<i style="background:' + getColor("F") + '"></i> Fail');
    labels.push('<i style="background:' + getColor("?") + '"></i> Unknown');

    div.innerHTML = labels.join('<br>');
    return div;
};

legend.addTo(map);