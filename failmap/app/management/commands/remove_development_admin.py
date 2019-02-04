import logging
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Deletes the shipped default admin user from this installation. Make sure you have another superuser."

    def handle(self, *args, **options):

        username = 'admin'

        # can't just remove as foreign keys fail
        users = User.objects.filter(username=username)
        for user in users:
            user.is_active = False
            user.is_superuser = False
            user.save()

        print("Development admin user has been deleted.")
        sys.stdout.write("Development admin user has been deleted.")
        sys.exit(0)
