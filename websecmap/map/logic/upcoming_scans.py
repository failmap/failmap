from datetime import timedelta

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_celery_beat.models import PeriodicTask


def get_next_and_last_scans():
    def next(obj):
        z, y = obj.schedule.is_due(last_run_at=timezone.now())
        date = timezone.now() + timedelta(seconds=y)
        return date

    periodic_tasks = (
        PeriodicTask.objects.all()
        .filter(enabled=True)
        .exclude(
            # Don't show system tasks that are not in the knowledge-domain of the site user.
            name__contains="celery.backend_cleanup"
        )
        .exclude(
            # Don't show system tasks that are not in the knowledge-domain of the site user.
            name__contains="failmap"
        )
        .exclude(
            # Don't show system tasks that are not in the knowledge-domain of the site user.
            name__contains="hiddden"
        )
        .exclude(
            # Don't show tasks that are performed extremely frequently like onboarding.
            crontab__minute__in=["*/5", "*/1", "*/10", "*/15", "*/30"]
        )
    )
    next_scans = []  # upcoming scans
    last_scans = []  # scans performed in the past

    # get standardized task names.
    # do not add
    for periodic_task in periodic_tasks:
        scan = {}
        next_date = next(periodic_task)
        scan["name"] = mark_safe(periodic_task.name)
        scan["date"] = next_date
        scan["human_date"] = naturaltime(next_date).capitalize()
        # Tried cron_descriptor, but the text isn't as good as crontab guru.
        # the translations aren't that great, also doesn't match django locale.
        # scan['repetition'] = descripter.get_description(DescriptionTypeEnum.FULL)

        next_scans.append(scan)

    # ordering
    next_scans = sorted(next_scans, key=lambda k: k["date"], reverse=False)

    # last scans is not supportes, since celery doesn't store this information.
    data = {"next": next_scans, "last": last_scans}

    return data
