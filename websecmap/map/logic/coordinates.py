# This is a set of tools for easier manipulation of point data.

# Checks if the coordinates are in the country. If not, they are switched.
# countries are defined by "geofencing", where all coordinates should be in a certain box.
# note: some countries have overseas territories.


# lat is horizontal, long is vertical on the well known projections of the earth at least.
import logging

# these are rough bounding boxes, and have little to do with actual borders. It's to find out if a
# coordinate fits in a certain box, and thus a certain country... in a case where you already know the country.
from websecmap.organizations.models import Coordinate, Organization

log = logging.getLogger(__package__)


GEOFENCES = {
    "NL": [
        {
            "description": "The Netherlands",
            "topleft": {"lat": 53.814923, "lng": 2.975974},
            "bottomright": {"lat": 50.598581, "lng": 7.544157},
        },
        {
            # these are close together, but are legally different types of entities at the time of writing
            "description": "Aruba, Curaçao, Bonaire",
            "topleft": {"lat": 12.787964, "lng": -70.209741},
            "bottomright": {"lat": 11.792349, "lng": -67.971954},
        },
        {
            "description": "Saba, Sint Eustatius",
            "topleft": {"lat": 17.760588, "lng": -63.414997},
            "bottomright": {"lat": 17.319307, "lng": -62.923775},
        },
        {
            "description": "Sint Maarten",
            "topleft": {"lat": 18.072169, "lng": -63.245902},
            "bottomright": {"lat": 17.906288, "lng": -62.956277},
        },
    ]
}


def validate_point(coordinate):
    if coordinate.geojsontype != "Point":
        raise ValueError("Coordinate is not a Geojson Point.")


def repair_corrupted_coordinate(coordinate):
    # Some coordinates are stored as strings, which cannot be parsed correctly. They should be stored as arrays.

    validate_point(coordinate)
    a = coordinate.area

    if coordinate.area is None:
        organizations = Organization.objects.all().filter(coordinate=coordinate)

        log.error(
            f"Discovered a point without a coordinate: ID: {coordinate}. Used by the following "
            f"organizations: {organizations}."
        )

        log.info("Erroneous coordinate has been deleted.")
        coordinate.delete()
        return

    print(
        f"Inspecting coordinate: {coordinate}, "
        f"type: {coordinate.geojsontype}, area: {coordinate.area}, a[0]: {a[0]}."
    )

    if a[0] == "[":
        # the coordinate is a string, which is not valid. It should have been stored in a different way.
        # example string input: [4.8264312999999675, 52.3454862]
        arr = a.replace("[", "").replace("]", "").replace(",", "").split(" ")
        arr[0] = float(arr[0])
        arr[1] = float(arr[1])
        print(f"Repairing coordinate: {coordinate}, proposed fix: {arr}")

        coordinate.area = arr
        coordinate.save(update_fields=["area"])

    a = coordinate.area
    if a[0] == "[":
        raise ValueError(f"Coordinate {coordinate} cannot be fixed.")

    return coordinate


def attach_coordinate(organization, latitude, longitude):
    coordinate = Coordinate()
    coordinate.geojsontype = "Point"
    coordinate.organization = organization
    coordinate.area = [longitude, latitude]
    coordinate.edit_area = {"type": "Point", "coordinates": [longitude, latitude]}
    coordinate.save()


def switch_latlng(coordinate):
    validate_point(coordinate)

    a = coordinate.area

    coordinate.area = [a[1], a[0]]

    coordinate.edit_area = {"type": "Point", "coordinates": [a[1], a[0]]}

    coordinate.save()

    return coordinate


def move_coordinates_to_country(coordinates, country: str = "NL"):
    for coordinate in coordinates:
        if not coordinate_is_in_country(coordinate, "NL"):
            coordinate = switch_latlng(coordinate)
            if not coordinate_is_in_country(coordinate, "NL"):
                organizations = Organization.objects.all().filter(coordinate=coordinate)
                log.error(
                    f"Coordinate {coordinate} is not in {country} at all, even if we flip it's axis. "
                    f"This coordinate is being used by {organizations}. The coordinate area is: {coordinate.area}"
                    f" Is your geofence correct? Or are you missing parts of your country? "
                    f"(Overseas territories?)"
                )


def coordinate_is_in_country(coordinate, country: str = "NL"):
    validate_point(coordinate)

    if country not in GEOFENCES:
        raise ValueError("No geofence defined for your country. Create one and try again.")

    """
    Warning: Points in geojson are stored in lng,lat. Leaflet wants to show it the other way around.

    https://tools.ietf.org/html/rfc7946#section-3.1.2
    Point coordinates are in x, y order (easting, northing for projected
    coordinates, longitude, and latitude for geographic coordinates):

    https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem

    >> wouldn't call it a bug, just a matter of confusing and contradictory standards.
    >> When talking about geographic locations, we usually use Lat-long. This has been codified in the ISO 6709
        standard.
    >> When dealing with Cartesian coordinate geometry, we generally use X-Y. Many GIS systems, work with a Geographic
        Location as a special case of a 2 D coordinate point, where the X represents the longitude and Y represents
        the Latitude. This order of coordinates, is exactly opposite that of the regular Lat-long notion.
    >> Coming to your problem:

    >> The map.setView takes a l.LatLong as an input, where the first cordinate is a Latitude, and the second is
        Longitude.
    >> Hence when you want 52.23N, 4.97E, you pass in [52.23943, 4.97599]
    >> The GeoJSON standard says that for any point, the first parameter is the X Coordinate (i.e. Longitude) and
        second parameter is the Y coordinate (i.e. Latitude);
    >> Hence when you want 52.23N, 4.97E in GeoJSON, you need to pass [4.97599, 52.23943]
    >> For further reading, go through this Q&A
    """

    fences = GEOFENCES[country]

    lng = coordinate.area[0]
    lat = coordinate.area[1]

    for fence in fences:
        vertically_matching: False  # lng
        horizontally_matching: False  # lat

        # 0, 0 is somewhere near the middle of africa. Some parts are negative to positive, others vice versa
        if fence["topleft"]["lng"] > fence["bottomright"]["lng"]:
            vertically_matching = fence["topleft"]["lng"] > lng > fence["bottomright"]["lng"]

        if fence["bottomright"]["lng"] > fence["topleft"]["lng"]:
            vertically_matching = fence["bottomright"]["lng"] > lng > fence["topleft"]["lng"]

        if fence["topleft"]["lat"] > fence["bottomright"]["lat"]:
            horizontally_matching = fence["topleft"]["lat"] > lat > fence["bottomright"]["lat"]

        if fence["bottomright"]["lat"] > fence["topleft"]["lat"]:
            horizontally_matching = fence["bottomright"]["lat"] > lng > fence["topleft"]["lat"]

        if horizontally_matching and vertically_matching:
            return True

    return False


def dedupe_coordinates():
    # Some organizations have multiple of the same coordinates after they have been fixed. This might be because
    # of an incorrect import.

    organizations = Organization.objects.all()

    for organization in organizations:
        coordinates = list(Coordinate.objects.all().filter(geojsontype="Point", organization=organization))

        # there are more geojson types than coordinate...
        if not coordinates:
            continue

        # If there is only one point, then it's all good and nothing needs to be changed.
        if len(coordinates) == 1:
            continue

        # There is no check if the same point is being used by multiple organizations. This for the
        # simple reason that the importers all create their own explicit coordinates: there is no way that ALL
        # organizations will move to the same location at the same time. So each have their own coordinate.

        # todo: what if one has less precision than the other one? How do we figure that out, if that is a problem?
        if coordinates[0].area == coordinates[1].area:
            log.error(
                f"The first two coordinates of {organization} have the same location. "
                f"Both are {coordinates[1].area}. We've deleted the second one."
            )
            coordinates[1].delete()
