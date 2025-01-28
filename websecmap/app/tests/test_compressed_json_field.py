import pytest
from django.db import connection

from websecmap.app.models import CompressedJSONFieldTest


@pytest.mark.filterwarnings("ignore:app.CompressedJSONFieldTest.data failed to load invalid json")
def test_compressedjsonfield(db):
    json_data = {"hello": "world", "2": 2, "nested": {"hello": "world"}, "none": None}

    x = CompressedJSONFieldTest()
    x.data = json_data
    x.save()

    # directly check the database without django to see if the value is actually compressed
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM app_compressedjsonfieldtest WHERE id = %s", [x.id])
        row = cursor.fetchone()

        assert row[0] != json_data
        assert row[0] != ""
        # see if there is any compression
        assert row[0][0] != "{"
        # see if there is some compression
        assert bytes(row[0][:4]) == b"\x1f\x8b\x08\x00"

    my_data = CompressedJSONFieldTest.objects.get(id=x.id)
    assert my_data.data == json_data

    # write some garbage in the database which is not json, this should be returned as a string due to fallback
    # of the json string. This is just some uncompressed json, so it should fallback to json:

    with connection.cursor() as cursor:
        cursor.execute("UPDATE app_compressedjsonfieldtest SET data = %s WHERE id = %s", ['{"hello": "world"}', x.id])

    my_data = CompressedJSONFieldTest.objects.get(id=x.id)
    assert my_data.data == {"hello": "world"}

    # and if it's truly junk, it just falls back to text.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE app_compressedjsonfieldtest SET data = %s WHERE id = %s", ["truly junk data", x.id])

    my_data = CompressedJSONFieldTest.objects.get(id=x.id)
    assert my_data.data == "truly junk data"

    # it should be able to deal with null values.
    x = CompressedJSONFieldTest()
    x.data = None
    x.save()
    assert x.data is None

    x = CompressedJSONFieldTest()
    x.data = {}
    x.save()
    assert x.data == {}

    # and update existing nulls:
    with connection.cursor() as cursor:
        cursor.execute("UPDATE app_compressedjsonfieldtest SET data = null WHERE id = %s", [x.id])

    my_data = CompressedJSONFieldTest.objects.get(id=x.id)
    my_data.save()
