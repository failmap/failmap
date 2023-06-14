from websecmap.scanners.models import Endpoint


def test_statsd_endpoint_save(caplog, db):
    # tests if signals are set up and that the right messages are sent.

    endpoint = Endpoint(**{"port": 80, "protocol": "http", "ip_version": 4})
    endpoint.is_dead = False
    endpoint.save()
    assert endpoint.pk is not None

    assert "endpoint_created" in caplog.text
    caplog.clear()

    endpoint.is_dead = True
    endpoint.save()
    assert "endpoint_killed" in caplog.text

    endpoint.is_dead = False
    endpoint.save()
    assert "endpoint_revived" in caplog.text
