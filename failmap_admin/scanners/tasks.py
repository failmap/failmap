"""Binds the function logic into queue logic."""

import logging

from celery.task import task
from django.apps import apps

from failmap_admin.scanners.scanner_security_headers import analyze_headers, get_headers

logger = logging.getLogger(__package__)

RETRY_INTERVAL = 60
