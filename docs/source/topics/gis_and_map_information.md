Mapping Information / GeoJSON
=============================
Please go through the resources in order to understand how to add
districts, points and lines of interest to the map.

1. Learn about how maps work: https://www.youtube.com/watch?v=2lR7s1Y6Zig
2. What projections Open Street Maps uses: http://openstreetmapdata.com/info/projections
3. Fail map / Open Street Maps uses GeoJson, described at: http://geojson.org

A harder challenge is to get data from a country in GeoJSON. Some
countries publish a (large) map for the use with mapping tools (GIS
Tools). A free mapping tool to work with this is QGIS, available at
qgis.org

Any map you'll download will probably contain way too many details.
Next steps describe the process to convert a large map to something
smaller, so it uses (way) less data:

1. Download a map, for example administrative regions of the
Netherlands: https://www.pdok.nl/nl/producten/pdok-downloads/basis-registratie-kadaster/bestuurlijke-grenzen-actueel
2. Open the map in QGIS, it will look heavily distorted as an
unfamiliar (but correct) projection is used.
3. It's possible to change the projection on the fly. Look for the
tiny globe icon and choose something like "Mercator (EPSG 3857)"
4. After you're happy with the projection and "the world makes sense
again" remove complexities from the map.
5. Reducing complexities reduces the file size from 8 megabyte to
hundreds of kiloytes.
6. Vector > Geometry Tools > Simplify Geometries, enter 500.0000 or
something like that. Let the algorithm do it's job.
7. Now right click on the simplified layer and export it. You can
export it to GeoJSON that the fail map software understands. The
projection is called "WGS84 (EPSG 4326)".
8. Import the data into the database, a procedure not yet described.

### Wish: OSM only solution.
OSM uses the administrative regions etc, and it's possible to determine
addresses and such.

There are API's that let one search through the data and export the
right things. Yet this was not implemented yet. This would be the
easiest way to have updated mapping data from all around the world that
requires a lesser amount of special steps. (the data is always there,
from everywhere =)

There are converters that reduce OSM to GeoJSON (but don't reduce
complexity afaik):
1. https://tyrasd.github.io/osmtogeojson/

### Using Overpass:
http://overpass-turbo.eu/

Query all municipalities, this data is daily updated.

```overpass
[out:json][timeout:300];
area[name="Nederland"]->.gem;
relation(area.gem)["type"="boundary"][admin_level=8];
out geom;
```

(with way(r); it omits tags and is smaller)

This delivers a 52 megabyte file with all coordinates that make up a
municipality, with various tags:

```json
    "tags": {
        "admin_level": "8",
        "authoritative": "yes",
        "boundary": "administrative",
        "name": "Heemskerk",
        "population": "39303",
        "ref:gemeentecode": "396",
        "source": "dataportal.nl",
        "type": "boundary",
        "wikidata": "Q9926",
        "wikipedia": "nl:Heemskerk"
    }
```

The file also contains "markers" inside a region that show metadata.

The regions need to be reduced or simplified to have less data transferred.
Would overpass be able to do this?


### Running Dutch municipality merge of 2018
Get the latest dataset from the server, get it to your dev environment

```
# DEVELOPMENT ONLY: failmap create_dataset -o -> dataset_12mar2018.json
```

Place the dataset in the fixture folder.

Then flush the database:
```
# DEVELOPMENT ONLY: failmap clear_database
```

Load the data into the application
```
# DEVELOPMENT ONLY: failmap load_dataset dataset_12mar2018.json
```

First make sure the organizations have been created and merged.
```
failmap merge_organizations_2018
```

Then import the new regions for these organizations:
```
failmap update_coordinates --date=2018-01-01
```

The new organizations (of course) do not have a rating, the rating needs to be rebuilt:
```
failmap rebuild_ratings
```



### Other things
Additionally there is an awesome world map in GeoJSON, available here:
https://github.com/datasets/geo-countries/blob/master/data/countries.geojson



###
Vlag opvragen:
( area["ISO3166-1"="NL"][admin_level=2]; )->.a;
