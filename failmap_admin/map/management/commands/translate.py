# Some help to translate the django part.
# This tries to help you avoid remembering the "messages" mess from Django.
import logging

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Automatically updates any explicitly maintained translations. Helps you on your way."

    """
    # Replaces django-admin makemessages -a with explicitly maintained translation commands.

    # You should not have to remember those commands: they are a burden.
    # This command automatically updates any explicitly maintained translation for you.

    # Just use this command twice: first to create the translations, secondly to compile them.
    # In any case it does both, first makemessages and then compilmessages.

    # Languages are defined in settings.

    # Django uses language codes inconstently, in this project we always use two letter language codes until
    # something better comes along.
    # https://docs.djangoproject.com/en/1.11/topics/i18n/#term-language-code
    # Django should use one approach, preferably ditch their own invention of language codes
    # and just go for locales centrally defined, such as a list from ISO.
    """

    def handle(self, *args, **options):

        # try and find new strings for all languages
        call_command('makemessages', '-a')

        # django-admin compilemessages
        for language in settings.LANGUAGES:
            # -d djangojs =
            # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/#creating-message-files-from-js-code
            call_command('makemessages', '-d', 'djangojs', '-l', language[0])
            call_command('compilemessages', '-l', language[0])

        logger.info('You can find the locale files in ./locale/(language code)/LC_MESSAGES/django(js).po')
        logger.info('Compiled files are located in ./locale/(language code)/LC_MESSAGES/django(js).mo')
        logger.info('')
        logger.info('Run this command again to have your changes compiled.')
        logger.info('Remember to keep the amount of translations in javascript as low as possible.')
