import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner.http import check_network

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Try to establish ipv4 and ipv6 connections to test the network, on both a worker and locally."

    def handle(self, *args, **options):

        log.info("Checking the network locally, this might take a while.")

        # locally
        check_network(code_location="local")

        log.info("Checking the network on a random worker, this might take a while and even hang without a worker.")

        # on a worker
        task = check_network.s(code_location="worker")
        task.apply_async()
