# Some help to translate the django part.
# This tries to help you avoid remembering the "messages" mess from Django.
import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Automatically updates any explicitly maintained translations. Helps you on your way."

    # replaces django-admin makemessages -a with explicitly maintained translations.
    # You should not have to remember these commands: they are a burden.
    # This command automatically updates any explicitly maintained translation for you.

    # Annoyingly, the django config uses language codes, see:
    # https://docs.djangoproject.com/en/1.11/topics/i18n/#term-language-code
    # and this should use locales, according to the documentation, which is confusing.
    # Django should use one approach, preferably ditch their own invention of language codes
    # and just go for locales of some ISO list.

    # Django's translation is a terrible mess to begin with. Perhaps we should move to vue trans.

    def handle(self, *args, **options):

        # django-admin compilemessages
        call_command('makemessages', '-l', 'nl')
        call_command('makemessages', '-l', 'en')
        call_command('compilemessages', '-l', 'nl')
        call_command('compilemessages', '-l', 'en')

        logger.debug('You can find the locale files in ./locale/--/LC_MESSAGES/django.po')
        logger.debug('Compiled files are located in ./locale/--/LC_MESSAGES/django.mo')
        logger.debug('Run this command again to have your updates compiled.')
