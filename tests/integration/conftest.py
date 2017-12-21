import pytest
from django.conf import settings

from failmap_admin.celery import app


@pytest.fixture()
def celery_app():
    """Use project app and settings instead of generic test app for more reliable tests."""
    # test connection(settings) as default behaviour is to verify initial connection
    # indefinitely which is fine for production use but not when testing/debugging
    with app.connection() as conn:
        conn.ensure_connection(max_retries=1)

    return app


@pytest.fixture(scope='session')
def celery_includes():
    """Fix test worker behaviour lost due to using project app."""
    return ['celery.contrib.testing.tasks']


@pytest.fixture(scope='session')
def celery_worker_pool():
    """Align test worker settings with project settings."""
    return 'prefork'


@pytest.fixture(scope='session')
def celery_worker_parameters():
    """Align test worker settings with project settings."""
    return {
        'concurrency': settings.CELERY_WORKER_CONCURRENCY,
    }
