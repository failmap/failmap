import pytest
from django.contrib.auth.models import User

from ..celery import app
from .models import Job


@pytest.fixture
def celery(settings):
    """Common setup for running (simulated) celery tasks inside tests."""
    # don't let celery contact broker, execute tasks directly
    settings.CELERY_TASK_ALWAYS_EAGER = True


@app.task
def dummy(result=True):
    """Dummy celery task for testing."""
    if result:
        return 'result'


def test_job(db, mock, celery):
    """Test creating task wrapped in a job."""

    request = mock.Mock()
    user = User(username='testuser')
    user.save()
    request.user = user

    job = Job.create(dummy.s(), 'a-name', request)

    assert job.result_id
    assert job.status == 'completed'
    assert job.result == 'result'
    assert job.task == 'failmap.app.tests.dummy()'
    assert job.created_by == user
    assert str(job) == job.result_id


def test_job_no_result(db, celery):
    """Task returning no result should not break stuff."""

    job = Job.create(dummy.s(False), 'a-name', None)

    assert job.result_id
    assert job.status == 'completed'
    assert job.result == '-- task generated no result object --'
    assert job.task == 'failmap.app.tests.dummy(False)'
