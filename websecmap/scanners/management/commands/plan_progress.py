import argparse
import logging
from datetime import datetime
from pprint import pprint
from time import sleep

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner import (dnssec, ftp, security_headers, tls_qualys, plain_http, subdomains,
                                        dns_wildcards, dns_known_subdomains, dns_endpoints)

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Normally all scans are planned and executed using periodic tasks. This command however will plan
    all verify, discovery and scan tasks on the entire system.
    """

    def handle(self, *args, **options):
        pprint(plannedscan.progress())
