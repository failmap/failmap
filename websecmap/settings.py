"""Django settings for websecmap project.

You do not need to edit the settings listed below.

For example, you should not need to change the DEBUG setting here, ever. For this you can use
direnv, which will change your environment settings when you enter this projects directory.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""
import os

# required until fixed: https://github.com/jazzband/django-constance/issues/263
from collections import OrderedDict
from datetime import timedelta

import sentry_sdk
from django.utils.translation import gettext_lazy as _
from pkg_resources import get_distribution
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from websecmap.scanners.constance import add_scanner_fields, add_scanner_fieldsets

__version__ = get_distribution(__name__.split(".", 1)[0]).version

# this application can run in 3 modes: admin, interactive and frontend
# 'admin' exposes all routes and uses no caching. It should be restricted in access.
# 'interactive' does not expose administrative urls, but does allow write access. Access should be
# restricted but can be less restricted then admin.
# 'frontend' only exposes the visitor facing routes and serves with cache headers. It does not
# allow write access to the database. Access can be unrestricted but is preferably behind caching
# proxy.

# for usability default to most functional mode
APPLICATION_MODE = os.environ.get("APPLICATION_MODE", "admin")

ADMIN = bool(APPLICATION_MODE == "admin")
INTERACTIVE = bool(APPLICATION_MODE == "interactive")

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Changed BASE_DIR so templates need to include the module and such. The idea
# was that otherwise the wrong template could be used when they have the same name
# over different dirs. Is this correct?
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "ditisgeengeheimvriendachtjedatditeenwachtwoordwas")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(os.environ.get("DEBUG", False))

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",")

# allows easier testing on mobile and external devices. Makes your site reachable over the local network
# which is insecure. It's an acceptable risk.
if DEBUG:
    ALLOWED_HOSTS += ["*"]

# allow better debugging for these clients
# https://docs.djangoproject.com/en/1.11/ref/settings/#internal-ips
INTERNAL_IPS = ["localhost", "127.0.0.1", "::1"]

# Application definition

INSTALLED_APPS = [
    # needs to be before jet and admin to extend admin/base.html template
    "dal",
    "dal_select2",
    "constance",
    "constance.backends.database",
    "websecmap.app",
    "adminsortable2",
    # Jet admin dashboard
    "jet.dashboard",
    "jet",
    "nested_admin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "import_export",
    "websecmap.fail",
    "websecmap.organizations.apps.OrganizationsConfig",  # because some signals need this.
    "websecmap.scanners",
    "websecmap.reporting",
    "websecmap.map",
    "websecmap.game",
    "websecmap.api",
    "django_countries",
    "django.contrib.admindocs",
    "django.contrib.humanize",
    "compressor",
    "django_celery_beat",
    "proxy",
    "django_statsd",
    # needs GDAL_LIBRARY_PATH, used for ?
    # 'leaflet',
    # Has been removed due to build errors (gdal) and little to no need to actually manually
    # edit coordinated via the admin interface.
    # 'djgeojson',
    "crispy_forms",  # for the game
    # django helpdesk requirements:
    # We don't use this yet, as it had issues during build.
    # 'django.contrib.sites',  # Required for determining domain url for use in emails
    # 'markdown_deux',  # Required for Knowledgebase item formatting
    # 'bootstrapform',  # Required for nicer formatting of forms with the default templates
    # 'helpdesk',  # This is us!
    # 'mapwidgets', # we don't support gdal, as it's not in alpine stable yet.
    "colorful",
    "django_select2",
    # others:
    # 'mapwidgets',  no gdal available yet, try again later
    # 'cachalot',  # query cache, is not faster.
    # 'silk'  # works great for debugging.
]

try:
    # hack to disable django_uwsgi app as it currently conflicts with compressor
    # https://github.com/django-compressor/django-compressor/issues/881
    if not os.environ.get("COMPRESS", False):
        import django_uwsgi  # NOQA

        INSTALLED_APPS += [
            "django_uwsgi",
        ]
except ImportError:
    # only configure uwsgi app if installed (ie: production environment)
    pass

# don't run this in production
try:
    import django_extensions  # NOQA

    INSTALLED_APPS += ["django_extensions"]
except ImportError:
    pass

MIDDLEWARE = [
    "django_statsd.middleware.GraphiteRequestTimingMiddleware",
    "django_statsd.middleware.GraphiteMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # based on cookie or based on user agent. So people with Dutch browsers will see the Dutch version(?).
    # This project is going to be used in a variety of countries, with multiple languages, so auto-setting this
    # makes sense over having a fixed single option.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/#how-django-discovers-language-preference
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.admindocs.middleware.XViewMiddleware",  # admindocs
]

# if loadbalancer/proxy provides authetication (eg: basic auth) trust it to provide the user
# https://docs.djangoproject.com/en/dev/howto/auth-remote-user
if os.environ.get("USE_REMOTE_USER", False):
    MIDDLEWARE.append("websecmap.app.middleware.remote_user.CustomRemoteUserMiddleware")
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.RemoteUserBackend",
        # fallback to traditional auth if no REMOTE_USER is provided
        "django.contrib.auth.backends.ModelBackend",
    ]

ROOT_URLCONF = "websecmap.urls"

# template needed for admin template
# this step is missing in the django jet tutorial, maybe because it's fairly common.

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR + "/",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "constance.context_processors.config",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "websecmap.wsgi.application"

# Assume traffic is proxied from frontend loadbalancers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases
# hopefully fixes helpdesk issue https://github.com/django-helpdesk/django-helpdesk/issues/184
# These settings also make sense if you don't use helpdesk, so they are still here.
DATABASE_OPTIONS = {
    "mysql": {
        "init_command": "SET character_set_connection=utf8,"
        "collation_connection=utf8_unicode_ci,"
        "sql_mode='STRICT_ALL_TABLES';"
    },
}
DB_ENGINE = os.environ.get("DB_ENGINE", "mysql")
DATABASE_ENGINES = {
    "mysql": "websecmap.app.backends.mysql",
}
DATABASES_SETTINGS = {
    # persisten local database used during development (runserver)
    "dev": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DB_NAME", "db.sqlite3"),
    },
    # sqlite memory database for running tests without
    "test": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DB_NAME", "db.sqlite3"),
    },
    # for production get database settings from environment (eg: docker)
    "production": {
        "ENGINE": DATABASE_ENGINES.get(DB_ENGINE, "django.db.backends." + DB_ENGINE),
        "NAME": os.environ.get("DB_NAME", "failmap"),
        "USER": os.environ.get("DB_USER", "failmap"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "failmap"),
        "HOST": os.environ.get("DB_HOST", "mysql"),
        "OPTIONS": DATABASE_OPTIONS.get(os.environ.get("DB_ENGINE", "mysql"), {}),
    },
}
# allow database to be selected through environment variables
DATABASE = os.environ.get("DJANGO_DATABASE", "dev")
DATABASES = {"default": DATABASES_SETTINGS[DATABASE]}

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# Fallback language.
# Language is depending on user agent
# https://docs.djangoproject.com/en/2.1/ref/settings/#language-code
LANGUAGE_CODE = "en"
# Less text is better :) See: https://www.youtube.com/watch?v=0j74jcxSunY

LANGUAGE_COOKIE_NAME = "language"

TIME_ZONE = "UTC"

USE_I18N = True
USE_L10N = True

# Loaddata will show a massive amount of warnings, therefore use load-dataset. load-dataset will
# do exactly the same as loaddata, but will overwrite below flag preventing warnings.
USE_TZ = True

# https://docs.djangoproject.com/en/1.11/topics/i18n/translation/#how-django-discovers-translations
# In all cases the name of the directory containing the translation is expected to be named using
# locale name notation. E.g. de, pt_BR, es_AR, etc.
LOCALE_PATHS = ["locale"]


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATIC_URL = "/static/"

# Absolute path to aggregate to and serve static file from.
if DEBUG:
    STATIC_ROOT = "static"
else:
    STATIC_ROOT = "/srv/websecmap/static/"

TEST_RUNNER = "websecmap.testrunner.PytestTestRunner"

# From the Jet documentation, a different color for a different season.
JET_THEMES = [
    {
        "theme": "default",  # theme folder name
        "color": "#47bac1",  # color of the theme's button in user menu
        "title": "Default",  # theme title
    },
    {"theme": "green", "color": "#44b78b", "title": "Green"},
    {"theme": "light-green", "color": "#2faa60", "title": "Light Green"},
    {"theme": "light-violet", "color": "#a464c4", "title": "Light Violet"},
    {"theme": "light-blue", "color": "#5EADDE", "title": "Light Blue"},
    {"theme": "light-gray", "color": "#222", "title": "Light Gray"},
]

# see: https://github.com/geex-arts/django-jet/blob/
#   fea07040229d1b56800a7b8e6234e5f9419e2114/docs/config_file.rst
# required for custom modules
JET_APP_INDEX_DASHBOARD = "websecmap.app.dashboard.CustomAppIndexDashboard"

# Customize the Dashboard index page remove unneeded panels (eg: feeds) and add usefull stuff (actions).
JET_INDEX_DASHBOARD = "websecmap.app.dashboard.CustomIndexDashboard"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",  # sys.stdout
            "formatter": "color",
        },
    },
    "formatters": {
        "debug": {
            "format": "%(asctime)s\t%(levelname)-8s - %(filename)-20s:%(lineno)-4s - " "%(funcName)20s() - %(message)s",
        },
        "color": {
            "()": "colorlog.ColoredFormatter",
            # to get the name of the logger a message came from, add %(name)s.
            "format": "%(log_color)s%(asctime)s\t%(levelname)-8s - " "%(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "log_colors": {
                "DEBUG": "green",
                "INFO": "white",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
    },
    "loggers": {
        # Default Django logging, we expect django to work, and therefore only show INFO messages.
        # It can be smart to sometimes want to see what's going on here, but not all the time.
        # https://docs.djangoproject.com/en/2.1/topics/logging/#django-s-logging-extensions
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        # We expect to be able to debug websecmap all of the time.
        "websecmap": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "DEBUG"),
        },
        # disable verbose task logging (ie: "received task...", "...succeeded in...")
        "celery.app.trace": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "DEBUG") if DEBUG else "ERROR",
        },
        "celery.worker.strategy": {
            "level": "INFO" if DEBUG else "ERROR",
        },
    },
}

# Add a slash at the end so we know it's a directory. Tries to somewhat prevents doing things in root.
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.abspath(os.path.dirname(__file__)) + "/")
VENDOR_DIR = os.environ.get("VENDOR_DIR", os.path.abspath(os.path.dirname(__file__) + "/../vendor/") + "/")

# the tools dir in this case are very small tools that build upon external dependencies, such as dnscheck.
# only use this if the vendor dir does not provide the needed command(s) in a simple way
TOOLS_DIR = os.environ.get("TOOLS_DIR", os.path.abspath(os.path.dirname(__file__) + "/../tools/") + "/")

# A number of tools and outputs are grouped to easier have access to all of them.
# Our vendor directory contains a number of small tools that are hard to install otherwise.

TOOLS = {
    "theHarvester": {
        "executable": VENDOR_DIR + os.environ.get("THEHARVESTER_EXECUTABLE", "theHarvester/theHarvester.py"),
        "output_dir": OUTPUT_DIR + os.environ.get("THEHARVESTER_OUTPUT_DIR", "scanners/resources/output/theHarvester/"),
    },
    "dnsrecon": {
        "executable": VENDOR_DIR + os.environ.get("DNSRECON_EXECUTABLE", "dnsrecon/dnsrecon.py"),
        "output_dir": OUTPUT_DIR + os.environ.get("DNSRECON_OUTPUT_DIR", "scanners/resources/output/dnsrecon/"),
        # The most important wordlists are auto-generated by this software, and are thus output.
        "wordlist_dir": OUTPUT_DIR + os.environ.get("DNSRECON_WORDLIST_DIR", "scanners/resources/wordlists/"),
    },
    "openstreetmap": {
        "output_dir": OUTPUT_DIR
        + os.environ.get("OPENSTREETMAP_OUTPUT_DIR", "scanners/resources/output/openstreetmap/"),
    },
    "organizations": {
        "import_data_dir": OUTPUT_DIR
        + os.environ.get("ORGANIZATION_IMPORT_DATA_DIR", "scanners/resources/data/organizations/"),
    },
    "sslscan": {
        # this is beta functionality and not supported in production
        # these are installed system wide and don't require a path (they might when development continues)
        "executable": {
            "Darwin": "sslscan",
            "Linux": "sslscan",
        },
        "report_output_dir": OUTPUT_DIR + "scanners/resources/output/sslscan/",
    },
    "openssl": {
        # this is beta functionality and not supported in production
        # these are installed system wide and don't require a path  (they might when development continues)
        "executable": {
            "Darwin": "openssl",
            "Linux": "openssl",
        },
    },
    "TLS": {
        # this is beta functionality and not supported in production
        "cve_2016_2107": VENDOR_DIR + "CVE-2016-2107-padding-oracle/main.go",
        "cve_2016_9244": VENDOR_DIR + "CVE-2016-9244-ticketbleed/ticketbleed.go",
        "cert_chain_resolver": {
            "Darwin": VENDOR_DIR + "cert-chain-resolver/cert-chain-resolver-darwin",
            "Linux": VENDOR_DIR + "cert-chain-resolver/cert-chain-resolver-linux",
        },
        "tls_check_output_dir": OUTPUT_DIR
        + os.environ.get("TLSCHECK_OUTPUT_DIR", "scanners/resources/output/tls_check/"),
    },
    "dnscheck": {"executable": TOOLS_DIR + "dnssec.pl"},
    "osaft": {
        "json": VENDOR_DIR + "osaft/JSON-array.awk",
    },
}

# Compression
# Django-compressor is used to compress css and js files in production
# During development this is disabled as it does not provide any feature there
# Django-compressor configuration defaults take care of this.
# https://django-compressor.readthedocs.io/en/latest/usage/
# which plugins to use to find static files
STATICFILES_FINDERS = (
    # default static files finders
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    # other finders..
    "compressor.finders.CompressorFinder",
)

COMPRESS_CSS_FILTERS = ["compressor.filters.cssmin.CSSCompressorFilter"]

# Slimit doesn't work with vue. Tried two versions. Had to rewrite some other stuff.
# Now using the default, so not explicitly adding that to the settings
# COMPRESS_JS_FILTERS = ['compressor.filters.jsmin.JSMinFilter']

# Brotli compress storage gives some issues.
# This creates the original compressed and a gzipped compressed file.
COMPRESS_STORAGE = "compressor.storage.GzipCompressorFileStorage"

# Disable caching during development and production.
# Django only emits caching headers, the webserver/caching-proxy makes sure the rest of the caching is handled.


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Enable static file (js/css) compression when not running debug
# https://django-compressor.readthedocs.io/en/latest/settings/#django.conf.settings.COMPRESS_OFFLINE
COMPRESS_OFFLINE = not DEBUG
# https://django-compressor.readthedocs.io/en/latest/settings/#django.conf.settings.COMPRESS_ENABLED
# Enabled when debug is off by default.

#####
# Celery 4.0 settings
#
# From the manual: https://docs.celeryproject.org/en/stable/django/first-steps-with-django.html#using-celery-with-django
# The uppercase name-space means that all Celery configuration options must be specified in uppercase instead of
# lowercase, and start with CELERY_, so for example the task_always_eager setting becomes CELERY_TASK_ALWAYS_EAGER,
# nd the broker_url setting becomes CELERY_BROKER_URL. This also applies to the workers settings, for instance,
# the worker_concurrency setting becomes CELERY_WORKER_CONCURRENCY.
#
# Pickle can work, but you need to use certificates to communicate (to verify the right origin)
# It's preferable not to use pickle, yet it's overly convenient as the normal serializer can not
# even serialize dicts.
# http://docs.celeryproject.org/en/latest/userguide/configuration.html

# Using json instead of pickle to reduce memory overhead and reduce attack surface
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_SERIALIZER = "json"
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_EVENT_SERIALIZER = "json"


CELERY_BROKER_URL = os.environ.get("BROKER", "redis://localhost:6379/0")
CELERY_ENABLE_UTC = True

# Any data transfered with pickle needs to be over tls... you can inject arbitrary objects with
# this stuff... message signing makes it a bit better, not perfect as it peels the onion.
# see: https://blog.nelhage.com/2011/03/exploiting-pickle/
# Yet pickle is the only convenient way of transporting objects without having to lean in all kinds
# of directions to get the job done. Intermediate tables to store results could be an option.
CELERY_TIMEZONE = "UTC"

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# how many times to retry connecting to the broker after failure: this is the cause of non-reconnecting
# workers. So this will be set to infinite and it will retry ad infinitum
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 400
CELERY_RESULT_EXPIRES = timedelta(hours=4)

# Use the value of 2 for celery prefetch multiplier. Previous was 1. The
# assumption is that 1 will block a worker thread until the current (rate
# limited) task is completed. When using 2 (or higher) the assumption is that
# celery will drop further rate limited task from the internal worker queue and
# fetch other tasks tasks that could be executed (spooling other rate limited
# tasks through in the process but to no hard except for a slight drop in
# overall throughput/performance). A to high value for the prefetch multiplier
# might result in high priority tasks not being picked up as Celery does not
# seem to do prioritisation in worker queues but only on the broker
# queues. The value of 2 is currently selected because it higher than 1,
# behaviour needs to be observed to decide if raising this results in
# further improvements without impacting the priority feature.
CELERY_WORKER_PREFETCH_MULTIPLIER = 2

# numer of tasks to be executed in parallel by celery
CELERY_WORKER_CONCURRENCY = 10

# Workers will scale up and scale down depending on the number of tasks
# available. To prevent workers from scaling down while still doing work,
# the ACKS_LATE setting is used. This insures that a task is removed from
# the task queue after the task is performed. This might result in some
# issues where tasks that don't finish or crash keep being executed:
# thus for tasks that are not programmed perfectly it will raise a number
# of repeated exceptions which will need to be debugged.
CELERY_TASK_ACKS_LATE = True

"""
This number can be tweaked depending on the number of threads/green-threads (eventlet/gevent) using a connection.
For example running eventlet with 1000 greenlets that use a connection to the broker, contention can arise and you
should consider increasing the limit.
We use 20 greenthreads or so. The error we see is:
redis.exceptions.ConnectionError: Error 104 while writing to socket. Connection reset by peer.
The error is not visible when running a single task or just a scan, or progressing the individual task where the crash
occurs. So probably connection limits are the issue.
"""
CELERY_BROKER_POOL_LIMIT = 30

#
# End of celery settings
#####

# Settings for statsd metrics collection. Statsd defaults over UDP port 8125.
# https://django-statsd.readthedocs.io/en/latest/#celery-signals-integration
STATSD_HOST = os.environ.get("STATSD_HOST", "127.0.0.1")
STATSD_PORT = os.environ.get("STATSD_PORT", "8125")
# add tag support via statshog
STATSD_TELEGRAF = True
STATSD_CLIENT = "statshog"

STATSD_PREFIX = ""

# register hooks for selery tasks
STATSD_CELERY_SIGNALS = True
# send database query metric (in production, in development we have debug toolbar for this)
if not DEBUG:
    STATSD_PATCHES = [
        "django_statsd.patches.db",
    ]

# enable some features during debug
if DEBUG:
    # We expect the debug toolbar always to be available in debug environments.
    import debug_toolbar

    INSTALLED_APPS.insert(0, "debug_toolbar")

    # The order of MIDDLEWARE is important. You should include the Debug Toolbar middleware as early as possible
    # in the list. However, it must come after any other middleware that encodes the response’s content,
    # such as GZipMiddleware.
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

    import debug_toolbar.settings

    DEBUG_TOOLBAR_PANELS = (
        [
            "ddt_request_history.panels.request_history.RequestHistoryPanel",
        ]
        + debug_toolbar.settings.PANELS_DEFAULTS
        + [
            "django_statsd.panel.StatsdPanel",
        ]
    )
    # send statsd metrics to debug_toolbar
    STATSD_CLIENT = "django_statsd.clients.toolbar"


# if sentry DSN is provided register raven to emit events on exceptions
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    # new sentry_sdk implementation, with hopes to also get exceptions from workers.
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[CeleryIntegration(), DjangoIntegration()],
        release=__version__,
        send_default_pii=False,
    )

    # INSTALLED_APPS += ('raven.contrib.django.raven_compat',)

    # add sentry ID to request for inclusion in templates
    # https://docs.sentry.io/clients/python/integrations/django/#message-references
    # Not (yet) supported, or renamed in the new sentry_sdk. Cannot find a replacement for this feature.
    # MIDDLEWARE.insert(1, 'raven.contrib.django.raven_compat.middleware.SentryResponseErrorIdMiddleware')

    # Celery specific handlers
    # client = raven.Client(SENTRY_DSN)

    # raven.contrib.celery.register_logger_signal(client)
    # raven.contrib.celery.register_signal(client)

# set javascript sentry token if provided
SENTRY_TOKEN = os.environ.get("SENTRY_TOKEN", "")

SENTRY_ORGANIZATION = "internet-cleanup-foundation"
SENTRY_PROJECT = "faalkaart"
SENTRY_PROJECT_URL = "https://sentry.io/%s/%s" % (SENTRY_ORGANIZATION, SENTRY_PROJECT)

# Some workers or (development) environments don't support both IP networks
# Note that not supporting either protocols can result in all endpoints being killed as they are unreachable by scanners
# We don't check these settings anywhere for sanity as some workers might not need a network at all.
# The defaults stem from our live environment, where we've set IPv4 being present on all containers and workers.
NETWORK_SUPPORTS_IPV4 = os.environ.get("NETWORK_SUPPORTS_IPV4", True)
NETWORK_SUPPORTS_IPV6 = os.environ.get("NETWORK_SUPPORTS_IPV6", False)

# atomic imports: fail completely, not half
IMPORT_EXPORT_USE_TRANSACTIONS = True

#########
# Begin constance settigns
# runtime configuration from database
# https://django-constance.readthedocs.io/en/latest/
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"


CONSTANCE_ADDITIONAL_FIELDS = {
    "yes_no_null_select": [
        "django.forms.fields.ChoiceField",
        {"widget": "django.forms.Select", "choices": ((None, "-----"), ("1", "Yes"), ("0", "No"))},
    ],
    # Todo: no validation options, that is offloaded to the widget?
    "json": [
        "django.forms.fields.CharField",
        {"widget": "django.forms.Textarea"},
    ],
}


CONSTANCE_CONFIG = {
    "COMMENTS": (
        "",
        "Here you can explain why some settings are set to a specific value. This can help when there is a "
        "sudden change. For example: a scanner stops working, there are issues with certain features and etcetera. "
        "<br /><br />If you manage these options with multiple people, make sure to contact everyone and leave "
        "contact information in this field. The value of this field will not be published on the website. ",
        str,
    ),
    "SHOW_ANNOUNCEMENT": (
        False,
        "Shows an announcement bar at the top of the website. This allows you to communicate about new features or "
        "upcoming fairs / meetings and etcetera.",
        bool,
    ),
    "ANNOUNCEMENT": (
        "",
        "The text that you want to announce. You can make use of HTML, Javascript and CSS to include anything you "
        "want. For example a link to a meeting, a new feature or a news message.",
        str,
    ),
    "PROJECT_WEBSITE": (
        "",
        "The url where this site is located. Without trailing slash. Eg: https://example.com."
        "<br><br> This is used in a couple of places on the website, in RSS feeds and other locations that need to "
        "point to the url of this site. The URL of this website cannot be determined automatically, unfortunately,"
        "so please set it yourself.",
        str,
    ),
    "PROJECT_NAME": (
        "",
        "The name of this mapping project, used for branding and promotion."
        "<br><br>For example: in the Netherlands the title Faalkaart is used. This has changed over time to "
        "Basis Beveiliging. The name will be shown at the bottom of the website.",
        str,
    ),
    "PROJECT_COUNTRY": (
        "NL",
        "Two letter ISO3316-2 code of the country that should be shown when there is absolutely no information "
        "to show on the map. This is overridden by the default Map Configuration.",
        str,
    ),
    "PROJECT_TAGLINE": ("", "Tagline for this project.", str),
    "PROJECT_MAIL": ("", "The address where people can contact for more info about this project.", str),
    "PROJECT_ISSUE_MAIL": (
        "",
        "The address where people can mail when they encounter issues, for example when they "
        "are using the incorrect findings button.",
        str,
    ),
    "PROJECT_TWITTER": ("", "The twitter address where people can follow this project. Include the @!", str),
    "PROJECT_FACEBOOK": (
        "",
        "The facebook address where people can follow this project. Has to be a complete url.",
        str,
    ),
    "GOOGLE_MAPS_API_KEY": (
        "AIzaSyBXJbEUxGW1dAB4hJOlmKdYelfoRY6_fjo",
        "This API key is used for geocoding services. Geocoding converts an address to a point on the map. <br><br>"
        "This is done in the DataSet import feature, as well as the game. If plan to use either, enter this key."
        "<br><br> You can request a Key at the Google Developer console, "
        '<a href="https://developers.google.com/maps/documentation/javascript/get-api-key"  target="_blank">here</a>.'
        "<br><br>"
        "Using geocoding services is not free. The first year a credit is given of 400 euro, which is enough to "
        "geocode thousands of addresses.",
        str,
    ),
    "MAPBOX_ACCESS_TOKEN": (
        "pk.eyJ1IjoibXJmYWlsIiwiYSI6ImNqMHRlNXloczAwMWQyd3FxY3JkMnUxb3EifQ.9nJBaedxrry91O1d90wfuw",
        "Mapbox provides the tiles shown on the map. This makes the map look like a map. Mapbox provides a number of"
        " tilesets and one is preconfigured to look well. Using mapbox tiles isn't free. Yet it requires a serious "
        "amount of visitors before it starts to cost money.<br><br>"
        "You can request a new mapbox key "
        '<a href="https://docs.mapbox.com/help/how-mapbox-works/access-tokens/" target="_blank">here</a>.',
        str,
    ),
    "WAMBACHERS_OSM_CLIKEY": (
        "c0e3473f-6ba2-4571-9331-4b3084022021",
        "Using this key replaces import from Open Street Maps with a specialized service. Using this serivce you will "
        "have nicer looking maps. The big difference is that all major waters and seas have been cut out, so only "
        "land mass is visible. This will make your country more recognizable if your country is near a sea or contains "
        "a large water body. Sea boarders usually span a few dozen kilometers outside of the land mass. <br /><br />"
        "Obtaining this key can be a bit tricky. First, go here: "
        '<a href="https://wambachers-osm.website/boundaries/"  target="_blank">wambachers-osm.website</a>. '
        "Then sign into Open Street "
        "Maps using the bottom at the top right of the page. After signing in, return to the wambacher site and "
        'use the form at the bottom of the page. Make sure the CLI checkmarked is set. When hitting the "download" '
        "button, a link will appear containing your unique key. Paste this key here.<br /><br />"
        "When using this service, please donate, as every query you do costs server and hosting capacity. A suitable"
        "amount of money is &euro;13.37 or &euro;42.",
        str,
    ),
    "RESPONSIBLE_ORGANIZATION_NAME": ("", "The name of the organization running this project.", str),
    "RESPONSIBLE_ORGANIZATION_PROMO_TEXT": (
        "",
        "Some text promoting this organization and its mission. This text will" " not be translated.",
        str,
    ),
    "RESPONSIBLE_ORGANIZATION_WEBSITE": ("", "The name of the organization running this project.", str),
    "RESPONSIBLE_ORGANIZATION_MAIL": ("", "The name of the organization running this project.", str),
    "RESPONSIBLE_ORGANIZATION_TWITTER": (
        "",
        "The twitter address where people can follow this project. Include " "the @!",
        str,
    ),
    "RESPONSIBLE_ORGANIZATION_FACEBOOK": (
        "",
        "The facebook address where people can follow this project. Make sure" " this is a complete url.",
        str,
    ),
    "RESPONSIBLE_ORGANIZATION_LINKEDIN": ("", "Linkedin page url.", str),
    "RESPONSIBLE_ORGANIZATION_WHATSAPP": ("", "Whatsapp number.", str),
    "RESPONSIBLE_ORGANIZATION_PHONE": ("", "Phone number, displayed as a sip:// addres.", str),
    "SHOW_INTRO": (
        True,
        "Shows an introduction text that explains what this site is and what it does. This text "
        "might not have been translated to your language yet, which means an English text is shown."
        "",
        bool,
    ),
    "SHOW_CHARTS": (
        True,
        "Shows the list of charts. Those are the lists of all good / bad organizations ordered "
        "by how good or bad they are doing.",
        bool,
    ),
    "SHOW_EXTENSIVE_STATISTICS": (
        True,
        "Shows extended statistics: these are bars of how well things are going " "now and in the past months.",
        bool,
    ),
    "SHOW_STATS_GRAPHS": (
        True,
        "Shows graphs in extended statistics. " "Extended statistics needs to be enabled for this to have effect.",
        bool,
    ),
    "SHOW_STATS_IMPROVEMENTS": (
        True,
        "Shows improvements in extended statistics. "
        "Extended statistics needs to be enabled for this to have effect.",
        bool,
    ),
    "SHOW_STATS_NUMBERS": (
        True,
        "Shows numbers in extended statistics. " "Extended statistics needs to be enabled for this to have effect.",
        bool,
    ),
    "SHOW_STATS_CHANGES": (
        True,
        "Shows changes in extended statistics. " "Extended statistics needs to be enabled for this to have effect.",
        bool,
    ),
    "SHOW_DATASETS": (
        True,
        "Shows dataset downloads. Note: dataset downloads are always available, even if they "
        "are not shown on the website.",
        bool,
    ),
    "SHOW_COMPLY_OR_EXPLAIN": (
        False,
        "Comply or explain allows organizations to explain findings publicly. This is shown on the website and in "
        "reports. The explanation is shown next to the crossed-out original finding. This helps organizations "
        "to explain why things aren't optimal yet. <br><br>"
        "Note that using this adds a significant amount of administrative work. This will be eased with the "
        "upcoming PRO features. Yet, if your organization or group is up for some administrative work "
        "it will be fine. It isn't hard, it just has to be done.",
        bool,
    ),
    "SHOW_COMPLY_OR_EXPLAIN_DISCUSS": (
        False,
        "Shows a link to the comply or explain discussion forum. The url of this forum can be edited below.",
        bool,
    ),
    "SHOW_TICKER": (
        False,
        "Shows stock-ticker with updates in the past month. This is a very distracting feature that works "
        "really well at fairs as an eye catcher. Use this in combination with the command below to not"
        " show the ticker to every visitor, but only when clicking a specific link.",
        bool,
    ),
    "TICKER_SLOGAN": ("WEB SECURITY MAP - MONITOR YOUR GOVERNMENT", "Text to show between every 10 changes.", str),
    "TICKER_VISIBLE_VIA_JS_COMMAND": (
        False,
        "Adds a Show/Hide ticker link at the bottom of the page. It will start scrolling after a second" " or two.",
        bool,
    ),
    "SHOW_SCAN_SCHEDULE": (False, "Shows list of upcoming scans, so everyone knows what scan is due next.", bool),
    "SHOW_SERVICES": (True, "Show table with how many services are scanned. Requires SHOW_STATS_NUMBERS.", bool),
    "SHOW_DONATION": (True, "Show donation buttons and links on the site.", bool),
    "COMPLY_OR_EXPLAIN_DISCUSSION_FORUM_LINK": (
        "",
        "A link where comply or explain items can be discussed. This might prevent a number of duplicate entries.",
        str,
    ),
    "COMPLY_OR_EXPLAIN_EMAIL_ADDRESS": ("", "E-mail where to receive explanations.", str),
    "SCAN_AT_ALL": (
        True,
        "This quickly enables or disabled all scans. Note that scans in the scan queue will still be processed.",
        bool,
    ),
    "SCAN_PROXY_TESTING_URL": ("", "Server where you can see scans through a proxy.", str),
    "INTERNET_NL_API_USERNAME": (
        "",
        "Username for the internet.nl API. You can request one via the contact "
        "options on their site, https://internet.nl.",
        str,
    ),
    "INTERNET_NL_API_PASSWORD": ("", "Password for the internet.nl API", str),
    "INTERNET_NL_API_URL": (
        "https://batch.internet.nl/api/batch/v2",
        "The internet address for the Internet.nl API installation. Defaults to a version from " "2020.",
        str,
    ),
    "INTERNET_NL_MAXIMUM_URLS": (1000, "The maximum amount of domains per scan.", int),
    # scanning pre-requisites
    "CONNECTIVITY_TEST_DOMAIN": (
        "faalkaart.nl",
        "A server that is reachable over IPv4. This is used by a worker to determine what kind of scans it can do. "
        "Enter an address that you own or manage.",
        str,
    ),
    "IPV6_TEST_DOMAIN": (
        "ip6.nl",
        "A server that is reachable over IPv6. This is used by a worker to determine "
        "what kind of scans it can do. Enter an address that you own or manage.",
        str,
    ),
    "GITTER_CHAT_ENABLE": (
        False,
        "Show a chat button on the bottom-right of the website. This chat uses Gitter Chat.",
        bool,
    ),
    "GITTER_CHAT_CHANNEL": (
        "internet-cleanup-foundation/support",
        "Name of the channel chat takes place. You might need to create a channel on gitter."
        'You can do so, <a href="https://gitter.im" target="_blank">here</a>.',
        str,
    ),
    "SCANNER_NAMESERVERS": (
        '["1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222", "8.26.56.26"]',
        "Nameservers used during scans (dns endpoints and subdomains). This string is loaded as JSON, but not validated"
        "due to limitations of this settings library. Be careful when editing(!). This information is cached and loaded"
        "only once every 10 minutes.",
        "json",
    ),
    "ENABLE_PRO": (False, "Todo: implement.", bool),
    "PRO_REPLY_TO_MAIL_ADDRESS": ("", "Reply mail address used when sending PRO mails.", str),
    # django mail settings, but managed dynamically
    "PRO_EMAIL_HOST": ("", "See django mail settings.", str),
    "PRO_EMAIL_PORT": ("", "See django mail settings.", str),
    "PRO_EMAIL_USERNAME": ("", "See django mail settings.", str),
    "PRO_EMAIL_PASSWORD": ("", "See django mail settings.", str),
    "PRO_EMAIL_USE_TLS": ("", "See django mail settings.", str),
    "PRO_EMAIL_USE_SSL": ("", "See django mail settings.", str),
    "PRO_EMAIL_SSL_KEYFILE": ("", "See django mail settings.", str),
    "PRO_EMAIL_SSL_CERTFILE": ("", "See django mail settings.", str),
    # Screenshots:
    "SCREENSHOT_API_URL_V4": ("http://screenshot_v4:1337", "Use this service to create a screenshot over v4.", str),
    "SCREENSHOT_API_URL_V6": ("http://screenshot_v6:1337", "Use this service to create a screenshot over v6.", str),
    # tilanus zorgkaart nederland:
    "ZORGKAART_ENDPOINT": ("https://", "Endpoint of the zorgkaart service.", str),
    "ZORGKAART_USERNAME": ("", "Username to connect to the zorgkaart service.", str),
    "ZORGKAART_PASSWORD": ("", "Password to connect to the zorgkaart service.", str),
    "ZORGKAART_FILTER": ("{}", "Filter options, stored as string.", str),
    "PLUS_SHOW_INFO": (False, "Show information about optional services.", bool),
}

CONSTANCE_CONFIG = add_scanner_fields(CONSTANCE_CONFIG)

CONSTANCE_CONFIG_FIELDSETS = OrderedDict(
    [
        ("General", ("COMMENTS", "PROJECT_WEBSITE", "SHOW_ANNOUNCEMENT", "ANNOUNCEMENT")),
        (
            "Keys to External Services",
            (
                "MAPBOX_ACCESS_TOKEN",
                "WAMBACHERS_OSM_CLIKEY",
                "GOOGLE_MAPS_API_KEY",
            ),
        ),
        (
            "Project information: how you call this installation publicly",
            (
                "PROJECT_NAME",
                "PROJECT_TAGLINE",
                "PROJECT_COUNTRY",
                "PROJECT_MAIL",
                "PROJECT_ISSUE_MAIL",
                "PROJECT_TWITTER",
                "PROJECT_FACEBOOK",
            ),
        ),
        (
            "Contact information of your organization",
            (
                "RESPONSIBLE_ORGANIZATION_NAME",
                "RESPONSIBLE_ORGANIZATION_PROMO_TEXT",
                "RESPONSIBLE_ORGANIZATION_WEBSITE",
                "RESPONSIBLE_ORGANIZATION_MAIL",
                "RESPONSIBLE_ORGANIZATION_TWITTER",
                "RESPONSIBLE_ORGANIZATION_FACEBOOK",
                "RESPONSIBLE_ORGANIZATION_LINKEDIN",
                "RESPONSIBLE_ORGANIZATION_WHATSAPP",
                "RESPONSIBLE_ORGANIZATION_PHONE",
            ),
        ),
        ("Chat and support options (using gitter)", ("GITTER_CHAT_ENABLE", "GITTER_CHAT_CHANNEL")),
        (
            "Comply or Explain",
            (
                "SHOW_COMPLY_OR_EXPLAIN",
                "SHOW_COMPLY_OR_EXPLAIN_DISCUSS",
                "COMPLY_OR_EXPLAIN_DISCUSSION_FORUM_LINK",
                "COMPLY_OR_EXPLAIN_EMAIL_ADDRESS",
            ),
        ),
        (
            "What to show on the website",
            (
                "SHOW_INTRO",
                "SHOW_CHARTS",
                "SHOW_EXTENSIVE_STATISTICS",
                "SHOW_DATASETS",
                "SHOW_STATS_GRAPHS",
                "SHOW_STATS_IMPROVEMENTS",
                "SHOW_STATS_NUMBERS",
                "SHOW_SERVICES",
                "SHOW_STATS_CHANGES",
                "SHOW_SCAN_SCHEDULE",
                "SHOW_DONATION",
            ),
        ),
        (
            "Scanning preferences",
            ("SCANNER_NAMESERVERS",),
        ),
        (
            "Plus",
            ("PLUS_SHOW_INFO",),
        ),
    ]
)


CONSTANCE_CONFIG_FIELDSETS = add_scanner_fieldsets(CONSTANCE_CONFIG_FIELDSETS)

CONSTANCE_CONFIG_FIELDSETS.update(
    [
        ("Fair / Stand options", ("SHOW_TICKER", "TICKER_SLOGAN", "TICKER_VISIBLE_VIA_JS_COMMAND")),
        (
            "Developer configuration. For debugging and verification",
            (
                "CONNECTIVITY_TEST_DOMAIN",
                "IPV6_TEST_DOMAIN",
                "SCAN_PROXY_TESTING_URL",
            ),
        ),
        (
            "Internet.nl Scans",
            ("INTERNET_NL_API_USERNAME", "INTERNET_NL_API_PASSWORD", "INTERNET_NL_API_URL", "INTERNET_NL_MAXIMUM_URLS"),
        ),
        ("Screenshot service options", ("SCREENSHOT_API_URL_V4", "SCREENSHOT_API_URL_V6")),
        ('<span class="beta">beta</span> Pro (in development)', ("ENABLE_PRO", "PRO_REPLY_TO_MAIL_ADDRESS")),
        (
            '<span class="beta">beta</span> Pro Mail Settings (in development)',
            (
                "PRO_EMAIL_HOST",
                "PRO_EMAIL_PORT",
                "PRO_EMAIL_USERNAME",
                "PRO_EMAIL_PASSWORD",
                "PRO_EMAIL_USE_TLS",
                "PRO_EMAIL_USE_SSL",
                "PRO_EMAIL_SSL_KEYFILE",
                "PRO_EMAIL_SSL_CERTFILE",
            ),
        ),
        (
            '<span class="beta">beta</span> Zorgkaart Nederland (Tilanus)',
            ("ZORGKAART_ENDPOINT", "ZORGKAART_USERNAME", "ZORGKAART_PASSWORD", "ZORGKAART_FILTER"),
        ),
    ]
)

# try / except: Prevent QA to move the import to the top of the file before the apps are loaded.
try:
    from websecmap.app.constance import validate_constance_configuration

    validate_constance_configuration(CONSTANCE_CONFIG, CONSTANCE_CONFIG_FIELDSETS)
except EnvironmentError as e:
    raise EnvironmentError(e)

# End constance settings
########

# https://docs.djangoproject.com/en/1.11/ref/settings/#data-upload-max-number-fields
# The default is far too low with various inlines (even on the test dataset).
# Yes, we happily exceed 1000 fields anyday. No problem :)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 4242

########
# Begin game settings:
# login on the frontpage should redirect to the game landingpage
LOGIN_REDIRECT_URL = "/game/"
LOGIN_URL = "/authentication/login/"
LOGOUT_REDIRECT_URL = "/"

CRISPY_TEMPLATE_PACK = "bootstrap3"

# End game settigns
#######

#######
# Begin helpdesk settings:
# Helpdesk removed.
# Unfortunately we cannot manage these settings with constance. And therefore you should be still editing
# this file. We're sorry.
# SITE_ID = 1  # For django-helpdesk. We only run one site...

# helps against spam, will leak all your data, so be careful. Spam could be protected against on your mailserver...
# AKISMET_API_KEY = os.environ.get('AKISMET_API_KEY', '')
# TYPEPAD_ANTISPAM_API_KEY = os.environ.get('TYPEPAD_ANTISPAM_API_KEY', '')

# If you use another server for sending mail, see config example here:
# http://django-helpdesk.readthedocs.io/en/0.2.x/configuration.html
# EMAIL_HOST = 'XXXXX'
# EMAIL_HOST_USER = 'YYYYYY@ZZZZ.PPP'
# EMAIL_HOST_PASSWORD = '123456'
# Make sure the MEDIA_ROOT is NOT readable from the webserver directly. So no https://bla/media.
# End of helpdesk settings
#######


#######
# begin django jet menu configuration
# This helps making various resources and fewer used features less visible.

# The following items are hidden on purpose:
# core.site (we only have one site)
# scanners.state, will be deprecated and removed (if not already)
# See: http://jet.readthedocs.io/en/latest/config_file.html#custom-menu
# Permissions are AND-ed together.
# admin (a nonsense permission) has been added everywhere to avoid "empty arrows" when signing in with a role with
# limited permissions.
# For the default labels, see: https://docs.djangoproject.com/en/2.1/topics/auth/default/#topic-authorization

JET_SIDE_MENU_ITEMS = [  # A list of application or custom item dicts
    {
        "label": _("👤 User"),
        "items": [
            {"name": "auth.user"},
        ],
    },
    {
        "label": _("🎛️ Configuration"),
        "items": [
            {"name": "constance.config", "label": "Site & Scanning Configuration"},
            {"name": "map.configuration", "label": "Displayed Countries / Areas"},
            {"name": "map.landingpage", "label": "Landing Pages / Redirects"},
            {"name": "django_celery_beat.periodictask", "label": "Scheduled Scans & Tasks"},
            {"name": "scanners.scanproxy", "label": "TLS Scan Proxies"},
        ],
    },
    {
        "label": _("💽 Import New Data"),
        "items": [
            {"name": "map.administrativeregion", "label": _("Open Street Map & Wikidata")},
            {"name": "organizations.dataset", "label": "Spreadsheet Import"},
        ],
    },
    {
        "label": _("🌍 Core Data"),
        "items": [
            {"name": "organizations.organization", "label": "Organizations"},
            {"name": "organizations.url", "label": "Urls"},
            {"name": "organizations.organizationtype"},
        ],
    },
    {
        "label": _("🤖 Generated Map Data"),
        "items": [
            {"name": "organizations.coordinate", "label": "Imported Map Coordinates"},
            {"name": "map.mapdatacache", "label": "Map Data Cache"},
            {"name": "map.vulnerabilitystatistic", "label": "Vulnerability Statistics"},
            {"name": "map.highlevelstatistic", "label": "Organization statistics"},
        ],
    },
    {
        "label": _("🔬 Generated Scans"),
        "items": [
            {"name": "scanners.plannedscan", "label": "Planned Scans"},
            {"name": "scanners.plannedscanstatistic", "label": "Planned Scans Stats"},
            {"name": "scanners.endpoint", "label": "Endpoints"},
            {"name": "scanners.endpointgenericscan", "label": "Endpoint Scans & Explanations"},
            {
                "label": "- By Last Scan Moment (newest)",
                "url": "/admin/scanners/endpointgenericscan/?o=-5.-6",
                "url_blank": False,
            },
            {
                "label": "- Possibly outdated scans",
                "url": "/admin/scanners/endpointgenericscan/"
                "?endpoint__is_dead__exact=0&endpoint__url__is_dead__exact=0&is_the_latest_scan__exact=1&o=5.-6",
                "url_blank": False,
            },
            {"name": "scanners.urlgenericscan", "label": "URL Scans"},
            {"name": "scanners.internetnlv2scan", "label": "Internet.nl API V2 Scan Tasks"},
            {"name": "scanners.internetnlv2statelog", "label": "Internet.nl API V2 Scan Log"},
            {"name": "scanners.screenshot", "label": "Screenshots"},
        ],
    },
    {
        "label": _("📊 Generated Reports"),
        "items": [
            {"name": "reporting.urlreport"},
            {"name": "map.organizationreport"},
            {"name": "map.maphealthreport"},
        ],
    },
    {
        "label": _("🐒 API"),
        "items": [
            {"name": "api.sidnupload"},
        ],
    },
    {
        "label": _("🐞 Debug"),
        "items": [
            {"name": "app.job", "label": "Performed scheduled tasks"},
            {"name": "scanners.tlsqualysscratchpad", "label": "Qualys Scans Debug"},
            {"name": "scanners.endpointgenericscanscratchpad", "label": "Endpoint Scans Debug"},
        ],
    },
    {
        "label": _("👾️ The Game (beta)"),
        "items": [
            {"name": "game.contest"},
            {"name": "game.team"},
            {"name": "game.organizationsubmission"},
            {
                "label": _("New organizations"),
                "url": "/admin/game/organizationsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-5",
                "url_blank": False,
            },
            {"name": "game.urlsubmission"},
            {
                "label": _("New urls"),
                "url": "/admin/game/urlsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-6.2.3",
                "url_blank": False,
            },
        ],
    },
]

JET_SIDE_MENU_COMPACT = True

# end django jet menu configuration
########

########
# Begin Cacheops
#         # django cacheops doesn't work with raw.
#         # too bad https://github.com/Suor/django-cacheops
#         # it's the elephant in the room in the documentation: all are explained except this one.

# Cacheops has been added to improve the retrieval of graphs-queries. At the time of writing it's only in use
# there using a hack to improve querying speed.

# It was not an option to rewrite queries to tailor to specific caching schemes per database vendor, django ORM also
# does not support that.

# It's a hack because out of the box cacheops doesn't support raw querysets (the only caveat without explanation).
# But we just need the list of data for displaying, thus we can wrap that in a function and use function result caching
#
# Note that lru_cache from functools does not support lists or complex types, while cahcheops does.
#
# I've chosen cacheops because it's actively maintained and has a lot of commits, while it's backlog is clean.
# Another reason is that it doesn't affect anything, except what you explicitly cache. So behaviour of the rest of the
# application is unchanged.

# If redis is not available, that is not a problem. For example: certain development scenario's or when redis fails.
# in that case a limited set of functions are performed without caching (and thus slower) but without crashes.
# If it's too slow, the webserver will kill it anyway, or in dev environments it will take longer.
# CACHEOPS_DEGRADE_ON_FAILURE = True

# CACHEOPS_REDIS = {
#     'host': 'localhost',  # redis-server is on same machine
#     'port': 6379,        # default redis port
#     'db': 1,             # SELECT non-default redis database
#                          # using separate redis db or redis instance
#                          # is highly recommended
#
#     'socket_timeout': 3,   # connection timeout in seconds, optional
# }
# End cacheops
########

####
# PRO settings
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    # Mail settings are managed in constance for easier mainteneance.
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


# Allow file uploads in datasets:
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", os.path.abspath(os.path.dirname(__file__)) + "/uploads/")

DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# this parameter is used in severity calculation to determine if this is a websecmap installation or
# something else, like an internet.nl dashboard. In case of websecmap, severities are adjusted.
# This flag will probably not be present in other installations by default.
APPLICATION_NAME = "websecmap"

"""
Django Jet 3:
From Django 3.0 the default value of the X_FRAME_OPTIONS setting was changed from SAMEORIGIN to DENY. This can
cause errors for popups such as for the Field Lookup Popup. To solve this you should add the following to your
Django project settings.py file:
Todo: Only needed for /admin urls, not for other urls: it's fine when people embed the map, desired even!
"""
X_FRAME_OPTIONS = "SAMEORIGIN"
