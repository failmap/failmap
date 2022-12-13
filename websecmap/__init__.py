from pkg_resources import get_distribution, DistributionNotFound

try:
    # try to get version number from installation metadata
    VERSION = get_distribution(__name__.split(".", 1)[0]).version
except DistributionNotFound:
    # if not available, that means the application is running in development
    VERSION = "0.0.0.dev0"

__version__ = VERSION
