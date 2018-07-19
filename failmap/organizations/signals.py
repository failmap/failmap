# coding=UTF-8
# from __future__ import unicode_literals

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from failmap.organizations.models import Url
from failmap.scanners.scanner import onboard

log = logging.getLogger(__name__)


# post_save actions are blocking: don't block things
# post_save signals run WITHIN the transaction, so you'll have to break out using an on_commit
# Described here: https://www.vinta.com.br/blog/2016/database-concurrency-in-django-the-right-way/
@receiver(post_save, sender=Url)
def onboard_after_add(sender, instance, created, **kwargs):

    # only new record:
    if not created:
        return

    # only if not onboarded already
    if instance.onboarded:
        return

    # todo: this signal only comes from the admin interface, run this command when new urls are found elsewhere
    def compose():
        onboard.compose_task(urls_filter={"url": instance}).apply_async()

    # disabled this until the onboarding is fixed. Otherwise we'll get tons and tons of useless exceptions.
    # transaction.on_commit(compose)
