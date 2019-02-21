import logging

from django.core.management.base import BaseCommand

from websecmap.hypersh.models import Credential

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Removes all images, containers and volumes on the current hyper.sh client.'

    def handle(self, *args, **options):

        creds = Credential.objects.all()
        for cred in creds:
            cred.task_nuke(cred)
