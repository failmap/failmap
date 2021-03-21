import logging
import os
import subprocess
import sys
import time
import warnings
from datetime import timedelta
from os.path import abspath, dirname, join
from uuid import uuid1

from django.conf import settings
from django.core.management import call_command
from django.core.management.commands.runserver import Command as RunserverCommand
from retry import retry

from websecmap.celery import app

log = logging.getLogger(__name__)

SOURCE_DIRECTORY = abspath(join(dirname(abspath(__file__)), "../" * 3))

TIMEOUT = timedelta(seconds=30)
KILL_TIMEOUT = timedelta(seconds=3)

REDIS_INFO = """
In order to run a full Failmap development instance Docker is required. For Linux systems the user should be
in the 'docker' group to be able to run Docker commands.

Please follow these instructions to install Docker and try again: https://docs.docker.com/engine/installation/

Alternatively if you only need to develop on 'website' parts of Failmap and not on scanner tasks and backend
processing you can start the devserver with backend disabled:

websecmap devserver --no-backend

or when running from `make`:

make run_no_backend

"""

DEVELOPMENT_FIXTURES = "development_user,development_scandata,development_periodic_tasks,testdata"


def start_borker(uuid):

    name = "websecmap-broker-%s" % str(uuid.int)

    borker_command = "docker run --rm --name=%s -p 6379 redis" % name
    borker_process = subprocess.Popen(borker_command.split(), stdout=subprocess.DEVNULL, stderr=sys.stderr.buffer)

    @retry(tries=10, delay=1)
    def get_container_port():
        command = "docker port %s 6379/tcp" % name
        return subprocess.check_output(
            command,
            shell=True,  # nosec predefined input in name mitigates risk of exploitation (unless uuid.int overridden).
            universal_newlines=True,
        ).split(":")[-1]

    time.sleep(1)  # small delay to prevent first warning
    port = int(get_container_port())

    return borker_process, port


def start_worker(broker_port, silent=True):
    watchdog = (
        ("watchmedo auto-restart --directory={} --pattern=*.py" " --recursive --signal=SIGKILL -- ")
        .format(SOURCE_DIRECTORY)
        .split()
    )
    # watchdog = 'tools/autoreload.sh'
    worker_command = (
        ("websecmap celery worker --loglevel=info --pool=gevent" " --concurrency=1 --broker redis://localhost:{}/0")
        .format(broker_port)
        .split()
    )

    worker_process = subprocess.Popen(watchdog + worker_command, stdout=sys.stdout.buffer, stderr=sys.stderr.buffer)

    return worker_process


def stop_process(process):
    # soft shutdown
    process.terminate()
    try:
        process.wait(KILL_TIMEOUT.seconds)
    except subprocess.TimeoutExpired:
        # hard shutdown
        process.kill()


class Command(RunserverCommand):
    """Run full development server."""

    help = __doc__

    command = None

    processes = []

    def add_arguments(self, parser):
        parser.add_argument(
            "-l",
            "--loaddata",
            default=DEVELOPMENT_FIXTURES,
            type=str,
            help="Comma separated list of data fixtures to load.",
        )
        parser.add_argument(
            "--no-backend", action="store_true", help="Do not start backend services (redis broker & task worker)."
        )
        parser.add_argument(
            "--no-data", action="store_true", help="Do not update database or load data (quicker start)."
        )

        super().add_arguments(parser)

    def handle(self, *args, **options):
        """Wrap in exception handler to perform cleanup."""

        # detect if we run inside the autoreloader's second thread
        inner_run = os.environ.get("RUN_MAIN", False)
        if inner_run:
            # only run the runserver in inner loop
            super().handle(*args, **options)
        else:
            try:
                self._handle(*args, **options)
            finally:
                for process in reversed(self.processes):
                    stop_process(process)

    def _handle(self, *args, **options):
        """Ensure complete development environment is started."""

        # unique ID for container name
        uuid = uuid1()

        # suppress celery DEBUG warning
        if options["verbosity"] < 2:
            warnings.filterwarnings("ignore")

        if not options["no_backend"]:
            # Make sure all requirements for devserver are met.
            try:
                # docker should be installed, daemon should be configured and running
                subprocess.check_call("docker info", shell=True, stdout=subprocess.DEVNULL)
            except BaseException:
                print(REDIS_INFO)
                sys.exit(1)

            # start backend services
            broker_process, broker_port = start_borker(uuid)
            log.info("Starting broker")
            self.processes.append(broker_process)
            log.info("Starting worker")
            self.processes.append(start_worker(broker_port, options["verbosity"] < 2))

            # set celery broker url
            settings.CELERY_BROKER_URL = "redis://localhost:%d/0" % broker_port
            # set as environment variable for the inner_run
            os.environ["BROKER"] = settings.CELERY_BROKER_URL

            # wait for worker to be ready
            log.info("Waiting for worker to be ready")
            for _ in range(TIMEOUT.seconds * 2):
                if app.control.ping(timeout=0.5):
                    break
            log.info("Worker ready")

        log.info("Updating database tables")
        call_command("migrate")

        if not options["no_data"]:
            # initialize/update dataset
            log.info("Loading fixture data")
            call_command("load_dataset", *options["loaddata"].split(","))

        # start the runserver command
        log.info("Starting webserver")
        super().handle(*args, **options)
