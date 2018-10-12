"""Django settings for failmap project.

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

import raven
import raven.contrib.celery
from django.utils.translation import gettext_lazy as _
from pkg_resources import get_distribution

__version__ = get_distribution(__name__.split('.', 1)[0]).version

# this application can run in 3 modes: admin, interactive and frontend
# 'admin' exposes all routes and uses no caching. It should be restricted in access.
# 'interactive' does not expose administrative urls, but does allow write access. Access should be
# restricted but can be less restricted then admin.
# 'frontend' only exposes the visitor facing routes and serves with cache headers. It does not
# allow write access to the database. Access can be unrestricted but is preferably behind caching
# proxy.

# for usability default to most functional mode
APPLICATION_MODE = os.environ.get('APPLICATION_MODE', 'admin')

ADMIN = bool(APPLICATION_MODE == 'admin')
INTERACTIVE = bool(APPLICATION_MODE == 'interactive')

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Changed BASE_DIR so templates need to include the module and such. The idea
# was that otherwise the wrong template could be used when they have the same name
# over different dirs. Is this correct?
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'ditisgeengeheimvriendachtjedatditeenwachtwoordwas')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', False)

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,::1,100.66.10.138,100.66.10.142').split(',')

# allow better debugging for these clients
# https://docs.djangoproject.com/en/1.11/ref/settings/#internal-ips
INTERNAL_IPS = ['localhost', '127.0.0.1', '::1']

# Application definition

INSTALLED_APPS = [
    # needs to be before jet and admin to extend admin/base.html template
    'dal',
    'dal_select2',
    'failmap.app',
    'failmap.hypersh',
    'django_fsm_log',
    'adminsortable2',
    # Jet admin dashboard
    'jet.dashboard',
    'jet',
    'nested_admin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
    'failmap.fail',
    'failmap.organizations.apps.OrganizationsConfig',  # because some signals need this.
    'failmap.scanners',
    'failmap.map',
    'failmap.game',
    'failmap.monitoryour',
    'django_countries',
    'django.contrib.admindocs',
    'django.contrib.humanize',
    'compressor',
    'django_celery_beat',
    'proxy',
    'django_statsd',
    'constance',
    'constance.backends.database',
    'leaflet',
    'djgeojson',
    'crispy_forms',  # for the game

    # django helpdesk requirements:
    'django.contrib.sites',  # Required for determining domain url for use in emails
    'markdown_deux',  # Required for Knowledgebase item formatting
    'bootstrapform',  # Required for nicer formatting of forms with the default templates
    'helpdesk',  # This is us!

    # 'mapwidgets', # we don't support gdal, as it's not in alpine stable yet.
    'colorful',
    'django_select2',
    # others:
    # 'mapwidgets',  no gdal available yet, try again later
    # 'cachalot',  # query cache, is not faster.
    # 'silk'  # works great for debugging.
]

try:
    # hack to disable django_uwsgi app as it currently conflicts with compressor
    # https://github.com/django-compressor/django-compressor/issues/881
    if not os.environ.get('COMPRESS', False):
        import django_uwsgi  # NOQA

        INSTALLED_APPS += ['django_uwsgi', ]
except ImportError:
    # only configure uwsgi app if installed (ie: production environment)
    pass

# don't run this in production
try:
    import django_extensions  # NOQA

    INSTALLED_APPS += ['django_extensions']
except ImportError:
    pass

MIDDLEWARE = [
    'django_statsd.middleware.GraphiteRequestTimingMiddleware',
    'django_statsd.middleware.GraphiteMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',

    # based on cookie or based on user agent. So people with Dutch browsers will see the Dutch version(?).
    # This project is going to be used in a variety of countries, with multiple languages, so auto-setting this
    # makes sense over having a fixed single option.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/#how-django-discovers-language-preference
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.contrib.admindocs.middleware.XViewMiddleware',  # admindocs
]

if DEBUG:
    # usage:
    # http://localhost:8000/data/vulnstats/NL/municipality/0?prof&count=100000&sort=cumtime
    MIDDLEWARE += ['django_cprofile_middleware.middleware.ProfilerMiddleware']

ROOT_URLCONF = 'failmap.urls'

# template needed for admin template
# this step is missing in the django jet tutorial, maybe because it's fairly common.

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + '/',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'constance.context_processors.config',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'failmap.wsgi.application'

# Assume traffic is proxied from frontend loadbalancers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases
# hopefully fixes helpdesk issue https://github.com/django-helpdesk/django-helpdesk/issues/184
DATABASE_OPTIONS = {
    'mysql': {'init_command': "SET character_set_connection=utf8,"
                              "collation_connection=utf8_unicode_ci,"
                              "sql_mode='STRICT_ALL_TABLES';"},

}
DB_ENGINE = os.environ.get('DB_ENGINE', 'mysql')
DATABASE_ENGINES = {
    'mysql': 'failmap.app.backends.mysql',
}
DATABASES_SETTINGS = {
    # persisten local database used during development (runserver)
    'dev': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DB_NAME', 'db.sqlite3'),
    },
    # sqlite memory database for running tests without
    'test': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DB_NAME', 'db.sqlite3'),
    },
    # for production get database settings from environment (eg: docker)
    'production': {
        'ENGINE': DATABASE_ENGINES.get(DB_ENGINE, 'django.db.backends.' + DB_ENGINE),
        'NAME': os.environ.get('DB_NAME', 'failmap'),
        'USER': os.environ.get('DB_USER', 'failmap'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'failmap'),
        'HOST': os.environ.get('DB_HOST', 'mysql'),
        'OPTIONS': DATABASE_OPTIONS.get(os.environ.get('DB_ENGINE', 'mysql'), {})
    }
}
# allow database to be selected through environment variables
DATABASE = os.environ.get('DJANGO_DATABASE', 'dev')
DATABASES = {'default': DATABASES_SETTINGS[DATABASE]}

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

# Go to admin: language_code = language_code.replace('_', '-').lower()
# AttributeError: 'NoneType' object has no attribute 'replace'
# while settings are loaded and Django uses LANGUAGE_CODE as default. What overrides this?
# a possible undesired solution, http://source.mihelac.org/2009/11/12/django-set-language-for-admin/

# http://stackoverflow.com/questions/1832709/django-how-to-make-translation-work
# shoddy documentation on dashes and underscores... different than the "ll" suggestion.
# LANGUAGE_CODE = 'en-gb'
# Less text is better :) See: https://www.youtube.com/watch?v=0j74jcxSunY
LANGUAGES = (
    ('en', 'English'),
    ('nl', 'Dutch'),
    # This helps to find missing translations. Using this language the goal is to replace all text
    # strings with a single rainbow. In the end there should be no text, only rainbows! 🌈
    ('rainbowsandunicorns', '🌈'),
)

# There is no 🌈🦄 translation for humanize. Instead you'll get the english fallback values.
# language is now depending on the user agent.
# LANGUAGE_CODE = 'en'

LANGUAGE_COOKIE_NAME = 'language'

TIME_ZONE = 'UTC'

USE_I18N = True
USE_L10N = True

# Loaddata will show a massive amount of warnings, therefore use load-dataset. load-dataset will
# do exactly the same as loaddata, but will overwrite below flag preventing warnings.
USE_TZ = True

# https://docs.djangoproject.com/en/1.11/topics/i18n/translation/#how-django-discovers-translations
# In all cases the name of the directory containing the translation is expected to be named using
# locale name notation. E.g. de, pt_BR, es_AR, etc.
LOCALE_PATHS = ['locale']


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATIC_URL = '/static/'

# Absolute path to aggregate to and serve static file from.
if DEBUG:
    STATIC_ROOT = 'static'
else:
    STATIC_ROOT = '/srv/failmap/static/'

TEST_RUNNER = 'failmap.testrunner.PytestTestRunner'

# From the Jet documentation, a different color for a different season.
JET_THEMES = [
    {
        'theme': 'default',  # theme folder name
        'color': '#47bac1',  # color of the theme's button in user menu
        'title': 'Default'  # theme title
    },
    {
        'theme': 'green',
        'color': '#44b78b',
        'title': 'Green'
    },
    {
        'theme': 'light-green',
        'color': '#2faa60',
        'title': 'Light Green'
    },
    {
        'theme': 'light-violet',
        'color': '#a464c4',
        'title': 'Light Violet'
    },
    {
        'theme': 'light-blue',
        'color': '#5EADDE',
        'title': 'Light Blue'
    },
    {
        'theme': 'light-gray',
        'color': '#222',
        'title': 'Light Gray'
    }
]

# see: https://github.com/geex-arts/django-jet/blob/
#   fea07040229d1b56800a7b8e6234e5f9419e2114/docs/config_file.rst
# required for custom modules
JET_APP_INDEX_DASHBOARD = 'failmap.app.dashboard.CustomAppIndexDashboard'

# Customize the Dashboard index page remove unneeded panels (eg: feeds) and add usefull stuff (actions).
JET_INDEX_DASHBOARD = 'failmap.app.dashboard.CustomIndexDashboard'

# expand menu items by default for quick access
JET_SIDE_MENU_COMPACT = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',  # sys.stdout
            'formatter': 'color',
        },
    },
    'formatters': {
        'debug': {
            'format': '%(asctime)s\t%(levelname)-8s - %(filename)-20s:%(lineno)-4s - '
                      '%(funcName)20s() - %(message)s',
        },
        'color': {
            '()': 'colorlog.ColoredFormatter',
            'format': '%(log_color)s%(asctime)s\t%(levelname)-8s - '
                      '%(message)s',
            'datefmt': '%Y-%m-%d %H:%M',
            'log_colors': {
                'DEBUG': 'green',
                'INFO': 'white',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
        }
    },
    'loggers': {
        '': {
            'handlers': ['console'],  # used when there is no log defined or loaded.
            'level': os.getenv('DJANGO_LOG_LEVEL', 'DEBUG'),
        },
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
    },
}

# Add a slash at the end so we know it's a directory. Tries to somewhat prevents doing things in root.
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', os.path.abspath(os.path.dirname(__file__)) + '/')
VENDOR_DIR = os.environ.get('VENDOR_DIR', os.path.abspath(os.path.dirname(__file__) + '/../vendor/') + '/')

# the tools dir in this case are very small tools that build upon external dependencies, such as dnscheck.
# only use this if the vendor dir does not provide the needed command(s) in a simple way
TOOLS_DIR = os.environ.get('TOOLS_DIR', os.path.abspath(os.path.dirname(__file__) + '/../tools/') + '/')

# A number of tools and outputs are grouped to easier have access to all of them.
# Our vendor directory contains a number of small tools that are hard to install otherwise.

TOOLS = {
    # Chrome and firefox are special cases: they install very easily and therefore don't need further grouping.
    'chrome': {
        'executable': {
            # os.platform is used to see what binaries should be used on a worker.
            'Darwin': os.environ.get(
                'CHROME_EXECUTABLE_DARWIN', "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            'Linux': os.environ.get(
                'CHROME_EXECUTABLE_LINUX', ""),
        },
        'screenshot_output_dir': OUTPUT_DIR + os.environ.get(
            'CHROME_SCREENSHOT_OUTPUT_DIR', 'map/static/images/screenshots/'),
    },
    # Chrome and firefox are special cases: they install very easily and therefore don't need further grouping.
    'firefox': {
        'executable': {
            # os.platform is used to see what binaries should be used on a worker.
            'Darwin': os.environ.get(
                'FIREFOX_EXECUTABLE_DARWIN', "/Applications/Firefox.app/Contents/MacOS/firefox"),
            'Linux': os.environ.get(
                'FIREFOX_EXECUTABLE_LINUX', ""),
        },
        'screenshot_output_dir': OUTPUT_DIR + os.environ.get(
            'FIREFOX_SCREENSHOT_OUTPUT_DIR', 'map/static/images/screenshots/'),
    },
    'theHarvester': {
        'executable': VENDOR_DIR + os.environ.get('THEHARVESTER_EXECUTABLE', "theHarvester/theHarvester.py"),
        'output_dir': OUTPUT_DIR + os.environ.get('THEHARVESTER_OUTPUT_DIR', "scanners/resources/output/theHarvester/"),
    },
    'dnsrecon': {
        'executable': VENDOR_DIR + os.environ.get('DNSRECON_EXECUTABLE', "dnsrecon/dnsrecon.py"),
        'output_dir': OUTPUT_DIR + os.environ.get('DNSRECON_OUTPUT_DIR', "scanners/resources/output/dnsrecon/"),

        # The most important wordlists are auto-generated by this software, and are thus output.
        'wordlist_dir': OUTPUT_DIR + os.environ.get('DNSRECON_WORDLIST_DIR', "scanners/resources/wordlists/"),
    },
    'openstreetmap': {
        'output_dir': OUTPUT_DIR + os.environ.get('OPENSTREETMAP_OUTPUT_DIR',
                                                  "scanners/resources/output/openstreetmap/"),
    },
    'sslscan': {
        # this is beta functionality and not supported in production
        # these are installed system wide and don't require a path (they might when development continues)
        'executable': {
            'Darwin': 'sslscan',
            'Linux': 'sslscan',
        },
        'report_output_dir': OUTPUT_DIR + "scanners/resources/output/sslscan/",
    },
    'openssl': {
        # this is beta functionality and not supported in production
        # these are installed system wide and don't require a path  (they might when development continues)
        'executable': {
            'Darwin': 'openssl',
            'Linux': 'openssl',
        },
    },
    'TLS': {
        # this is beta functionality and not supported in production
        'cve_2016_2107': VENDOR_DIR + 'CVE-2016-2107-padding-oracle/main.go',
        'cve_2016_9244': VENDOR_DIR + 'CVE-2016-9244-ticketbleed/ticketbleed.go',
        'cert_chain_resolver': {
            'Darwin': VENDOR_DIR + 'cert-chain-resolver/cert-chain-resolver-darwin',
            'Linux': VENDOR_DIR + 'cert-chain-resolver/cert-chain-resolver-linux',
        },
        'tls_check_output_dir': OUTPUT_DIR + os.environ.get('TLSCHECK_OUTPUT_DIR',
                                                            'scanners/resources/output/tls_check/'),
    },
    'dnscheck': {
        'executable': TOOLS_DIR + 'dnssec.pl'
    },
    'osaft': {
        'json': VENDOR_DIR + 'osaft/JSON-array.awk',
    }
}

# Compression
# Django-compressor is used to compress css and js files in production
# During development this is disabled as it does not provide any feature there
# Django-compressor configuration defaults take care of this.
# https://django-compressor.readthedocs.io/en/latest/usage/
# which plugins to use to find static files
STATICFILES_FINDERS = (
    # default static files finders
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # other finders..
    'compressor.finders.CompressorFinder',
)

COMPRESS_CSS_FILTERS = ['compressor.filters.cssmin.CSSCompressorFilter']

# Slimit doesn't work with vue. Tried two versions. Had to rewrite some other stuff.
# Now using the default, so not explicitly adding that to the settings
# COMPRESS_JS_FILTERS = ['compressor.filters.jsmin.JSMinFilter']

# Brotli compress storage gives some issues.
# This creates the original compressed and a gzipped compressed file.
COMPRESS_STORAGE = (
    'compressor.storage.GzipCompressorFileStorage'
)

# Disable caching during development and production.
# Django only emits caching headers, the webserver/caching-proxy makes sure the rest of the caching is handled.


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Enable static file (js/css) compression when not running debug
# https://django-compressor.readthedocs.io/en/latest/settings/#django.conf.settings.COMPRESS_OFFLINE
COMPRESS_OFFLINE = not DEBUG
# https://django-compressor.readthedocs.io/en/latest/settings/#django.conf.settings.COMPRESS_ENABLED
# Enabled when debug is off by default.

# Celery 4.0 settings
# Pickle can work, but you need to use certificates to communicate (to verify the right origin)
# It's preferable not to use pickle, yet it's overly convenient as the normal serializer can not
# even serialize dicts.
# http://docs.celeryproject.org/en/latest/userguide/configuration.html
CELERY_accept_content = ['pickle', 'yaml']
CELERY_task_serializer = 'pickle'
CELERY_result_serializer = 'pickle'


# Celery config
CELERY_BROKER_URL = os.environ.get('BROKER', 'redis://localhost:6379/0')
ENABLE_UTC = True

# Any data transfered with pickle needs to be over tls... you can inject arbitrary objects with
# this stuff... message signing makes it a bit better, not perfect as it peels the onion.
# this stuff... message signing makes it a bit better, not perfect as it peels the onion.
# see: https://blog.nelhage.com/2011/03/exploiting-pickle/
# Yet pickle is the only convenient way of transporting objects without having to lean in all kinds
# of directions to get the job done. Intermediate tables to store results could be an option.
CELERY_ACCEPT_CONTENT = ['pickle']
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'
CELERY_TIMEZONE = 'UTC'

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

CELERY_BROKER_CONNECTION_MAX_RETRIES = 1
CELERY_BROKER_CONNECTION_RETRY = False
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

# Settings for statsd metrics collection. Statsd defaults over UDP port 8125.
# https://django-statsd.readthedocs.io/en/latest/#celery-signals-integration
STATSD_HOST = os.environ.get('STATSD_HOST', '127.0.0.1')
STATSD_PREFIX = 'failmap'
# register hooks for selery tasks
STATSD_CELERY_SIGNALS = True
# send database query metric (in production, in development we have debug toolbar for this)
if not DEBUG:
    STATSD_PATCHES = ['django_statsd.patches.db', ]

# enable some features during debug
if DEBUG:
    # enable debug toolbar if available
    try:
        import debug_toolbar

        INSTALLED_APPS.append('debug_toolbar')
        MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')

        import debug_toolbar.settings

        DEBUG_TOOLBAR_PANELS = [
            'ddt_request_history.panels.request_history.RequestHistoryPanel',
        ] + debug_toolbar.settings.PANELS_DEFAULTS + [
            'django_statsd.panel.StatsdPanel',
        ]
        # send statsd metrics to debug_toolbar
        STATSD_CLIENT = 'django_statsd.clients.toolbar'
    except ImportError:
        pass

# if sentry DSN is provided register raven to emit events on exceptions
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    INSTALLED_APPS += ('raven.contrib.django.raven_compat',)
    RAVEN_CONFIG = {
        'dsn': SENTRY_DSN,
        'release': __version__,
    }
    # add sentry ID to request for inclusion in templates
    # https://docs.sentry.io/clients/python/integrations/django/#message-references
    MIDDLEWARE.insert(0, 'raven.contrib.django.raven_compat.middleware.SentryResponseErrorIdMiddleware')

    # Celery specific handlers
    client = raven.Client(SENTRY_DSN)
    raven.contrib.celery.register_logger_signal(client)
    raven.contrib.celery.register_signal(client)

# set javascript sentry token if provided
SENTRY_TOKEN = os.environ.get('SENTRY_TOKEN', '')

SENTRY_ORGANIZATION = 'internet-cleanup-foundation'
SENTRY_PROJECT = 'faalkaart'
SENTRY_PROJECT_URL = 'https://sentry.io/%s/%s' % (SENTRY_ORGANIZATION, SENTRY_PROJECT)

# Some workers or (development) environments don't support both IP networks
# Note that not supporting either protocols can result in all endpoints being killed as they are unreachable by scanners
# We don't check these settings anywhere for sanity as some workers might not need a network at all.
# The defaults stem from our live environment, where we've set IPv4 being present on all containers and workers.
NETWORK_SUPPORTS_IPV4 = os.environ.get('NETWORK_SUPPORTS_IPV4', True)
NETWORK_SUPPORTS_IPV6 = os.environ.get('NETWORK_SUPPORTS_IPV6', False)

# atomic imports: fail completely, not half
IMPORT_EXPORT_USE_TRANSACTIONS = True

#########
# Begin constance settigns
# runtime configuration from database
# https://django-constance.readthedocs.io/en/latest/
CONSTANCE_BACKEND = 'constance.backends.database.DatabaseBackend'


CONSTANCE_ADDITIONAL_FIELDS = {
    'yes_no_null_select': ['django.forms.fields.ChoiceField', {
        'widget': 'django.forms.Select',
        'choices': ((None, "-----"), ("1", "Yes"), ("0", "No"))
    }],
}


CONSTANCE_CONFIG = {
    'COMMENTS': ('', 'Some comments by you that say a little bit about why below settings are the way they are.', str),

    'SHOW_ANNOUNCEMENT': (False, 'Shows the announcement bar. Announcements do not show when empty anyway.', bool),
    'ANNOUNCEMENT': ('', 'Text / HTML message that should appear on the top of the site / app. For example with '
                         'important news / features or current issues. You can enter any HTML, JS, CSS.', str),

    'PROJECT_NAME': ('', 'The name of this mapping project, used for branding and promotion.', str),
    'PROJECT_COUNTRY': ('NL', 'Two letter ISO code of the country that should be shown.', str),
    'PROJECT_TAGLINE': ('', 'Tagline for this project.', str),
    'PROJECT_WEBSITE': ('', 'The url where this site is located.', str),
    'PROJECT_MAIL': ('', 'The address where people can contact for more info about this project.', str),
    'PROJECT_ISSUE_MAIL': ('', 'The address where people can mail when they encounter issues, for example when they '
                               'are using the incorrect findings button.', str),
    'PROJECT_TWITTER': ('', 'The twitter address where people can follow this project. Include the @!', str),
    'PROJECT_FACEBOOK': ('', 'The facebook address where people can follow this project. Has to be a complete url.',
                         str),


    'GOOGLE_MAPS_API_KEY': ('AIzaSyBXJbEUxGW1dAB4hJOlmKdYelfoRY6_fjo',
                            'API Key of google maps that can be used in the game / adding section.', str),

    'MAPBOX_ACCESS_TOKEN': ('pk.eyJ1IjoibXJmYWlsIiwiYSI6ImNqMHRlNXloczAwMWQyd3FxY3JkMnUxb3EifQ.9nJBaedxrry91O1d90wfuw',
                            'Access token for Mapbox', str),

    'WAMBACHERS_OSM_CLIKEY': ('', 'CLI key for Wambachers OSM export feature', str),

    'RESPONSIBLE_ORGANIZATION_NAME': ('', 'The name of the organization running this project.', str),
    'RESPONSIBLE_ORGANIZATION_PROMO_TEXT': ('', 'Some text promoting this organization and it\s mission. This text will'
                                                ' not be translated.', str),
    'RESPONSIBLE_ORGANIZATION_WEBSITE': ('', 'The name of the organization running this project.', str),
    'RESPONSIBLE_ORGANIZATION_MAIL': ('', 'The name of the organization running this project.', str),
    'RESPONSIBLE_ORGANIZATION_TWITTER': ('', 'The twitter address where people can follow this project. Include '
                                             'the @!', str),
    'RESPONSIBLE_ORGANIZATION_FACEBOOK': ('', 'The facebook address where people can follow this project. Make sure'
                                              ' this is a complete url.', str),
    'RESPONSIBLE_ORGANIZATION_LINKEDIN': ('', 'Linkedin page url.', str),
    'RESPONSIBLE_ORGANIZATION_WHATSAPP': ('', 'Whatsapp number.', str),
    'RESPONSIBLE_ORGANIZATION_PHONE': ('', 'Phone number, displayed as a sip:// addres.', str),

    'SHOW_INTRO': (True, 'Shows the standard introduction.', bool),
    'SHOW_GOOD_BAD': (True, 'Shows the good / bad lists.', bool),
    'SHOW_EXTENSIVE_STATISTICS': (True, 'Shows extended statistics.', bool),
    'SHOW_STATS_GRAPHS': (True, 'Shows graphs in extended statistics. '
                                'Extended statistics needs to be enabled for this to have effect.', bool),
    'SHOW_STATS_IMPROVEMENTS': (True, 'Shows improvements in extended statistics. '
                                      'Extended statistics needs to be enabled for this to have effect.', bool),
    'SHOW_STATS_NUMBERS': (True, 'Shows numbers in extended statistics. '
                                 'Extended statistics needs to be enabled for this to have effect.', bool),
    'SHOW_STATS_CHANGES': (True, 'Shows changes in extended statistics. '
                                 'Extended statistics needs to be enabled for this to have effect.', bool),
    'SHOW_DATASETS': (True, 'Shows dataset downloads. Note: dataset downloads are always available, even if they '
                            'are not shown on the website.', bool),
    'SHOW_TICKER': (False, 'Shows stock-ticker with updates in the past month.', bool),

    'SHOW_SERVICES': (True, 'Show table with how many services are scanned. Requires SHOW_STATS_NUMBERS.', bool),
    'SHOW_DNS_DNSSEC': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_TLS_QUALYS': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_MISSING_TLS': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_HEADERS_HSTS': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_HEADERS_XFO': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_HEADERS_X_XSS': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_HTTP_HEADERS_X_CONTENT': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),
    'SHOW_FTP': (True, 'Show graphs/stats of this? May cause empty spots on the site.', bool),

    # todo: schedule this once per week by default.
    'DISCOVER_URLS_USING_NSEC': (True, 'Discover new domains using DNSSEC NSEC1 hashes? (See docs)', bool),
    'DISCOVER_URLS_USING_KNOWN_SUBDOMAINS': (True, 'Discover new domains using known subdomains? (See docs)', bool),
    'DISCOVER_URLS_USING_CERTIFICATE_TRANSPARENCY': (True, 'Discover new domains using crt.sh '
                                                           'certificate transperancy database? (See docs)', bool),
    'DISCOVER_HTTP_ENDPOINTS': (True, 'Do you want to discover HTTP endpoints?', bool),

    'SCAN_AT_ALL': (True, 'Do you want to scan at all?', bool),
    'SCAN_DNS_DNSSEC': (True, 'Do you want to scan for DNSSEC issues?', bool),
    'SCAN_HTTP_TLS_QUALYS': (True, 'Do you want to scan for TLS issues through Qualys? This is about 1 scan per '
                                   'two minutes. Cloud scanning can improve this a bit.', bool),
    'SCAN_HTTP_TLS_OSAFT': (True, 'Experimental: Do you want to scan for TLS issues through OSaft? This is about '
                                  '3 scans per minute. Cloud scanning can improve this a bit.', bool),
    'SCAN_HTTP_MISSING_TLS': (True, 'Do you want to scan for endpoints that don\'t have a secure counterpart?', bool),
    'SCAN_HTTP_HEADERS_HSTS': (True, 'Do you want to scan for missing '
                                     'Hypertext Strict Transport Security headers?', bool),
    'SCAN_HTTP_HEADERS_XFO': (True, 'Do you want to scan for missing X-Frame-Options headers?', bool),
    'SCAN_HTTP_HEADERS_X_XSS': (True, 'Do you want to scan for missing X-XSS headers?', bool),
    'SCAN_HTTP_HEADERS_X_CONTENT': (True, 'Do you want to scan for missing X-Content-Type issues?', bool),
    'SCAN_FTP': (True, 'Do you want to scan for FTP servers that are missing encryption?', bool),
    'CREATE_HTTP_SCREENSHOT': (True, 'Todo: Does not work yet! Do you want to create screenshots for HTTP endpoints?',
                               bool),

    # future: FTP, TLS_QUICK (way less robust and complete, much faster)
    'REPORT_INCLUDE_FTP': (True, 'Do you want to add FTP encryption issues to the report?', bool),
    'REPORT_INCLUDE_DNS_DNSSEC': (True, 'Do you want to add DNSSEC issues to the report?', bool),
    'REPORT_INCLUDE_HTTP_TLS_QUALYS': (True, 'Do you want to show TLS results in the report?', bool),
    'REPORT_INCLUDE_HTTP_MISSING_TLS': (True, 'Do you want to show missing TLS in the report?', bool),
    'REPORT_INCLUDE_HTTP_HEADERS_HSTS': (True, 'Do you want to HSTS in the report?', bool),
    'REPORT_INCLUDE_HTTP_HEADERS_XFO': (True, 'Do you want to show XFO in the report?', bool),
    'REPORT_INCLUDE_HTTP_HEADERS_X_XSS': (True, 'Do you want to show X-XSS protection headers in the report?', bool),
    'REPORT_INCLUDE_HTTP_HEADERS_X_CONTENT': (True, 'Do you want to show X-Content-Type headers in the report?', bool),

    # scanning pre-requisites
    'CONNECTIVITY_TEST_DOMAIN': ('faalkaart.nl', 'A server that is reachable over IPv4. This is used by a worker '
                                                 'to determine what kind of scans it can do. Enter an '
                                                 'address that you own or manage.', str),
    'IPV6_TEST_DOMAIN': ('faalkaart.nl', 'A server that is reachable over IPv6. This is used by a worker to determine '
                                         'what kind of scans it can do. Enter an address that you own or manage.', str),

    'GITTER_CHAT_ENABLE': (False, 'Show the Gitter Chat option on the website (using gitter sidecar).', bool),
    'GITTER_CHAT_CHANNEL': ('internet-cleanup-foundation/support', 'Name of the channel chat takes place.', str),

    #
    # 'USE_CUSTOM_INTRO': (False, 'If you want to use an (untranslated) custom intro, enable this. Enabling this'
    #                             'will remove the standard intro and has several fields that can be filled with '
    #                             'custom HTML.', bool),
}

CONSTANCE_CONFIG_FIELDSETS = OrderedDict([
    ('General', ('COMMENTS', 'SHOW_ANNOUNCEMENT', 'ANNOUNCEMENT', 'MAPBOX_ACCESS_TOKEN', 'WAMBACHERS_OSM_CLIKEY')),

    ('Project', ('PROJECT_NAME', 'PROJECT_COUNTRY', 'PROJECT_TAGLINE', 'PROJECT_WEBSITE', 'PROJECT_MAIL',
                 'PROJECT_ISSUE_MAIL', 'PROJECT_TWITTER', 'PROJECT_FACEBOOK')),

    ('Responsible', ('RESPONSIBLE_ORGANIZATION_NAME', 'RESPONSIBLE_ORGANIZATION_PROMO_TEXT',
                     'RESPONSIBLE_ORGANIZATION_WEBSITE', 'RESPONSIBLE_ORGANIZATION_MAIL',
                     'RESPONSIBLE_ORGANIZATION_TWITTER', 'RESPONSIBLE_ORGANIZATION_FACEBOOK',
                     'RESPONSIBLE_ORGANIZATION_LINKEDIN', 'RESPONSIBLE_ORGANIZATION_WHATSAPP',
                     'RESPONSIBLE_ORGANIZATION_PHONE')),

    ('Website', ('SHOW_INTRO', 'SHOW_GOOD_BAD', 'SHOW_EXTENSIVE_STATISTICS', 'SHOW_DATASETS', 'SHOW_STATS_GRAPHS',
                 'SHOW_STATS_IMPROVEMENTS', 'SHOW_STATS_NUMBERS', 'SHOW_SERVICES', 'SHOW_STATS_CHANGES', 'SHOW_TICKER',
                 'SHOW_DNS_DNSSEC', 'SHOW_HTTP_TLS_QUALYS', 'SHOW_HTTP_MISSING_TLS',
                 'SHOW_HTTP_HEADERS_HSTS', 'SHOW_HTTP_HEADERS_XFO', 'SHOW_HTTP_HEADERS_X_XSS',
                 'SHOW_HTTP_HEADERS_X_CONTENT', 'SHOW_FTP'
                 )),

    ('Discovery', ('DISCOVER_URLS_USING_NSEC', 'DISCOVER_URLS_USING_KNOWN_SUBDOMAINS',
                   'DISCOVER_URLS_USING_CERTIFICATE_TRANSPARENCY', 'DISCOVER_HTTP_ENDPOINTS')),

    ('Scanner Capabilities', ('CONNECTIVITY_TEST_DOMAIN', 'IPV6_TEST_DOMAIN')),

    ('Scanning', ('SCAN_AT_ALL', 'SCAN_DNS_DNSSEC', 'SCAN_HTTP_TLS_QUALYS', 'SCAN_HTTP_TLS_OSAFT',
                  'SCAN_HTTP_MISSING_TLS', 'SCAN_HTTP_HEADERS_HSTS',
                  'SCAN_HTTP_HEADERS_XFO', 'SCAN_HTTP_HEADERS_X_XSS', 'SCAN_HTTP_HEADERS_X_CONTENT', 'SCAN_FTP',
                  'CREATE_HTTP_SCREENSHOT')),

    ('Reporting', ('REPORT_INCLUDE_DNS_DNSSEC', 'REPORT_INCLUDE_HTTP_TLS_QUALYS', 'REPORT_INCLUDE_HTTP_MISSING_TLS',
                   'REPORT_INCLUDE_HTTP_HEADERS_HSTS',
                   'REPORT_INCLUDE_HTTP_HEADERS_XFO', 'REPORT_INCLUDE_HTTP_HEADERS_X_XSS',
                   'REPORT_INCLUDE_HTTP_HEADERS_X_CONTENT', 'REPORT_INCLUDE_FTP')),

    ('Game', ('GOOGLE_MAPS_API_KEY',)),

    ('Chat (using gitter)', ('GITTER_CHAT_ENABLE', 'GITTER_CHAT_CHANNEL'))
])

# Check for constance configuration issues:
# See also: https://github.com/jazzband/django-constance/issues/293
variables_in_fieldsets = [i for sub in [CONSTANCE_CONFIG_FIELDSETS[x] for x in CONSTANCE_CONFIG_FIELDSETS] for i in sub]
variables_in_config = [x for x in CONSTANCE_CONFIG]
missing = set(variables_in_config) - set(variables_in_fieldsets)
if missing:
    raise EnvironmentError("Constance config variables %s are missing in constance config fieldsets." % missing)

# End constance settings
########

# https://docs.djangoproject.com/en/1.11/ref/settings/#data-upload-max-number-fields
# The default is far too low with various inlines (even on the test dataset).
# Yes, we happily exceed 1000 fields anyday. No problem :)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 4242

########
# Begin game settings:
# login on the frontpage should redirect to the game landingpage
LOGIN_REDIRECT_URL = '/game/'
LOGIN_URL = '/authentication/login/'
LOGOUT_REDIRECT_URL = '/'

CRISPY_TEMPLATE_PACK = 'bootstrap3'

# End game settigns
#######

#######
# Begin helpdesk settings:
# Unfortunately we cannot manage these settings with constance. And therefore you should be still editing
# this file. We're sorry.
SITE_ID = 1  # For django-helpdesk. We only run one site...

# helps against spam, will leak all your data, so be careful. Spam could be protected against on your mailserver...
AKISMET_API_KEY = os.environ.get('AKISMET_API_KEY', '')
TYPEPAD_ANTISPAM_API_KEY = os.environ.get('TYPEPAD_ANTISPAM_API_KEY', '')

# If you use another server for sending mail, see config example here:
# http://django-helpdesk.readthedocs.io/en/0.2.x/configuration.html
# EMAIL_HOST = 'XXXXX'
# EMAIL_HOST_USER = 'YYYYYY@ZZZZ.PPP'
# EMAIL_HOST_PASSWORD = '123456'
# Make sure the MEDIA_ROOT is NOT readable from the webserver directly. So no https://bla/media.
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', os.path.abspath(os.path.dirname(__file__)) + '/../')

# End of helpdesk settings
#######


#######
# begin django jet menu configuration
# This helps making various resources and fewer used features less visible.


# todo: add permissions: 'permissions': ['core.user']

# The following items are hidden on purpose:
# core.site (we only have one site)
# scanners.state, will be deprecated and removed (if not already)
# See: http://jet.readthedocs.io/en/latest/config_file.html#custom-menu
# Permissions are AND-ed together.
# admin (a nonsense permission) has been added everywhere to avoid "empty arrows" when signing in with a role with
# limited permissions.
# For the default labels, see: https://docs.djangoproject.com/en/2.1/topics/auth/default/#topic-authorization
JET_SIDE_MENU_ITEMS = [  # A list of application or custom item dicts

    {'label': _('🔧 configuration'), 'items': [
        {'name': 'auth.user'},
        {'name': 'auth.group'},
        {'name': 'constance.config', 'label': _('configuration')},
        {'name': 'map.configuration', 'label': _('map configuration')},
        {'name': 'map.administrativeregion', 'label': _('import regions')},
    ], 'permissions': ['admin']},

    {'app_label': 'organizations', 'label': _('🏢 organizations'), 'items': [
        {'name': 'organization'},
        {'name': 'url'},
        {'name': 'promise'},
        {'name': 'coordinate'},
        {'name': 'organizationtype'},
    ], 'permissions': ['admin']},

    # todo: sort scan moment to show latest first.
    {'app_label': 'scanners', 'label': _('🔬 scanners'), 'items': [
        {'name': 'endpoint', 'permissions': ['admin']},
        {'name': 'endpointgenericscan', 'permissions': ['scanners.change_endpointgenericscan']},
        {'name': 'tlsscan', 'permissions': ['scanners.change_tlsscan']},
        {'name': 'tlsqualysscan', 'permissions': ['scanners.change_tlsqualysscan']},
        {'name': 'urlgenericscan', 'permissions': ['scanners.change_urlgenericscan']},
        {'name': 'screenshot', 'permissions': ['admin']},
        {'name': 'urlip', 'permissions': ['admin']},
        {'name': 'tlsqualysscratchpad', 'permissions': ['admin']},
        {'name': 'endpointgenericscanscratchpad', 'permissions': ['admin']},
    ]},

    {'label': _('🗺️ map (autogenerated)'), 'items': [
        {'name': 'map.organizationrating'},
        {'name': 'map.urlrating'},
    ], 'permissions': ['admin']},

    {'label': _('🕒 periodic tasks'), 'items': [
        {'name': 'app.job'},
        {'name': 'django_celery_beat.periodictask'},
        {'name': 'django_celery_beat.crontabschedule'},
        {'name': 'django_celery_beat.intervalschedule'},
        {'name': 'django_celery_beat.solarschedule'},
    ], 'permissions': ['admin']},

    {'app_label': 'helpdesk', 'label': _('ℹ️ helpdesk'), 'items': [
        {'name': 'queue'},
        {'name': 'ticket'},
        {'name': 'followup'},
        {'name': 'customfield'},
        {'name': 'presetreply'},
        {'name': 'emailtemplate'},
        {'name': 'escalationexclusion'},
        {'name': 'ignoreemail'},
        {'name': 'kbcategory'},
        {'name': 'kbitem'},
    ], 'permissions': ['admin']},

    {'app_label': 'hypersh', 'label': _('☁️ hypersh cloud scans'), 'items': [
        {'name': 'containerenvironment'},
        {'name': 'containerconfiguration'},
        {'name': 'containergroup'},
        {'name': 'credential'},
    ], 'permissions': ['admin']},

    {'app_label': 'game', 'label': _('👾️ the game'), 'items': [
        {'name': 'contest'},
        {'name': 'team'},
        {'name': 'organizationsubmission'},
        {'label': _('New organizations'),
         'url': '/admin/game/organizationsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-5',
         'url_blank': False},
        {'name': 'urlsubmission'},
        {'label': _('New urls'),
         'url': '/admin/game/urlsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-6.2.3',
         'url_blank': False},
    ], 'permissions': ['admin']},
]
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
