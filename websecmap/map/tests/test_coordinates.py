from websecmap.map.logic.coordinates import coordinate_is_in_country
from websecmap.organizations.models import Coordinate


def test_coordinates():
    # Geojson is lng, lat format.

    # https://en.wikipedia.org/wiki/Kingdom_of_the_Netherlands

    # Amsterdam, capital of the Netherlands
    assert coordinate_is_in_country(Coordinate(area=[4.895168, 52.370216], geojsontype="Point"), "NL") is True

    # Philipsburg, Sint Maarten
    assert coordinate_is_in_country(Coordinate(area=[-63.047735, 18.025347], geojsontype="Point"), "NL") is True

    # Oranjestad, Aruba
    assert coordinate_is_in_country(Coordinate(area=[-70.034600, 12.523765], geojsontype="Point"), "NL") is True

    # Some parts of the Dutch Empire, that used to be Dutch, but certainly are not now...
    # https://en.wikipedia.org/wiki/Dutch_Empire

    # New York
    assert coordinate_is_in_country(Coordinate(area=[-74.005974, 40.712776], geojsontype="Point"), "NL") is False

    # Capetown
    assert coordinate_is_in_country(Coordinate(area=[18.424055, -33.924870], geojsontype="Point"), "NL") is False

    # Jakarta
    assert coordinate_is_in_country(Coordinate(area=[106.865036, -6.175110], geojsontype="Point"), "NL") is False
