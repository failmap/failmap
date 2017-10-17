"""Test to run against the 'outside'."""
from django.conf import settings


@skipif(settings.DEBUG, 'requires compressor enabled')
def test_compressor_results(client):
    """Results of compressions should be available under static files."""

    response = client.get('/static/CACHE/manifest.json')
    assert response.status_code == 200
