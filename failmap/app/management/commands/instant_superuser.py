import logging
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from failmap.app.admin import generate_password, generate_username

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Generates a new superuser instantly, echoes back the username password."

    # Note: this is OK, as the failmap command in server installations can only be called as root. And if you are root..

    def handle(self, *args, **options):

        username = generate_username().replace(" ", "-")
        first_name = username.split("-")[0]
        last_name = username.split("-")[1]

        password = generate_password()

        user = User.objects.create_superuser(username=username, email="", password=password)
        user.first_name = first_name
        user.last_name = last_name
        user.save()

        # simplest output only for command line parsing.
        # print("Username: '%s', Password: '%s'" % (username, password))

        # linux compatible only.
        sys.stdout.write("%s %s" % (username, password))
        sys.exit(0)
