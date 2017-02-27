# http://docs.celeryproject.org/en/latest/userguide/testing.html

import pytest
from failmap_admin.scanners.models import ScansBla
from failmap_admin.scanners.scanners import blascanner


def test_blascanner():
    """Test the blascanner success result."""

    assert blascanner('domain')['rating'] in ['A', 'B', 'C']


def test_blascanner_failure():
    """Test if blascanner preditably fails."""

    with pytest.raises(Exception):
        blascanner('fail.domain')


def test_blascanner_task(settings, db, celery_worker):
    """Test blascanner using celery tasks."""

    # during tests don't require a queue broker
    settings.CELERY_BROKER_URL = 'memory://'

    scan = ScansBla(url='example.com')
    scan.save()

    assert scan.state == 'PENDING'
