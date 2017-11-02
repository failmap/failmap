# Extend django-uwsgi command to disable checks at startup.
# By creating the same command in a app that is loaded earlier than django_uwsgi we can
# override the settings of this command.

from django_uwsgi.management.commands.runuwsgi import Command

# During startup of a Django management command 'system checks' can be performed.
# https://docs.djangoproject.com/en/1.11/topics/checks/
# However some of these checks require a working database connection which cannot be
# guaranteed when the application container is started (database container might be initializing).
# For this reason the checks are disabled when running the WSGI server.

# Disable running system checks.
Command.requires_system_checks = False
