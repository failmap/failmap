import pytest
from django.contrib.auth.models import User

from websecmap.app.models import Job
from websecmap.celery import app


@pytest.fixture
def celery(settings):
    """Common setup for running (simulated) celery tasks inside tests."""
    # don't let celery contact broker, execute tasks directly
    settings.CELERY_TASK_ALWAYS_EAGER = True


@app.task(queue='default')
def dummy(result=True):
    """Dummy celery task for testing."""
    if result:
        return 'result'


def test_job(db, mocker, celery):
    """Test creating task wrapped in a job."""

    request = mocker.Mock()
    user = User(username='testuser')
    user.save()
    request.user = user

    job = Job.create(dummy.s(), 'a-name', request)

    assert job.result_id
    assert job.status == 'created'

    # result after task has been processed by celery
    job.refresh_from_db()
    assert job.status == 'completed'
    assert job.result == 'result'
    assert job.task == 'test_jobs.dummy()'
    assert job.created_by == user
    assert str(job) == 'a-name'


def test_job_no_result(db, celery):
    """Task returning no result should not break stuff."""

    job = Job.create(dummy.s(False), 'a-name', None)

    assert job.result_id
    assert job.status == 'created'

    # result after task has been processed by celery
    job.refresh_from_db()
    assert job.status == 'completed'
    assert job.result == '-- task generated no result object --'
    assert job.task == 'test_jobs.dummy(False)'

