import os

from django.conf import settings

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint, Screenshot
from websecmap.scanners.scanner.screenshot import (
    deserialize_image_to_image,
    determine_subdir,
    make_screenshot_with_browserless,
    save_screenshot,
)


def test_make_screenshot_with_browserless(requests_mock, db, current_path):
    with open(f"{current_path}/websecmap/scanners/tests/testdata/pixel.png", "rb") as file_handle:
        pixel = file_handle.read()

    requests_mock.post("https://example.com", content=pixel)

    data = make_screenshot_with_browserless("https://example.com", "basisbeveiliging.nl")

    # Note that the file is not binary.
    assert data == {
        "error_message": "",
        "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQIW2NgAAIAAAUAAR4f7BQAAAAASUVORK5CYII=",
        "screenshot_service": "https://example.com",
        "status_code": 200,
        "success": True,
        "url": "basisbeveiliging.nl",
    }

    # Check that we get an image:
    image_data = deserialize_image_to_image(data["screenshot"])
    assert image_data.size == (1, 1)

    org = Organization(**{"name": "test"})
    org.save()
    url = Url(**{"url": "example.com"})
    url.save()
    org.add_url(url.url)
    end = Endpoint(**{"url": url})
    end.save()

    assert Screenshot.objects.all().count() == 0
    save_screenshot(data, Endpoint.objects.all().first().id)
    assert Screenshot.objects.all().count() == 1

    subdir = determine_subdir(end.id)

    assert os.path.exists(f"{settings.MEDIA_ROOT}screenshots/{subdir}/{end.id}_latest.png")


def test_determine_subdir():

    assert "000" == determine_subdir(999)
    assert "000" == determine_subdir(0)
    assert "100" == determine_subdir(1000)
    assert "100" == determine_subdir(10000)
    assert "100" == determine_subdir(100000)
    assert "100" == determine_subdir(1000000)
