import logging
import re
import subprocess

from django.core.management.base import BaseCommand

log = logging.getLogger(__name__)

# sumulating quota's given their API doesn't support that query (i mean wtf!)
HYPER_MAX_CONTAINERS = 20
HYPER_MAX_IMAGES = 20
HYPER_MAX_VOLUMES = 40
HYPER_MAX_FIPS = 10

"""
Hyper.sh manual control command.

Requires hyper.sh to be installed, see hyper.sh for installation instructions (pip install hyper).
Requires a client.p12 file in the failmap directory. Will only install things in the frankfurt region for now.

Usage:

failmap hype -a status
failmap hype -a clear - Removes all containers, images and volumes

failmap hype -a up qualys (number)
failmap hype -a down qualys (number)

failmap hype -a status - amount of containers vs max, images and volumes.

"""


class Command(BaseCommand):
    """Run a Failmap production server."""

    def add_arguments(self, parser):
        parser.add_argument('-a', '--action',
                            help='The specific action you want to perform')

        super().add_arguments(parser)

    def handle(self, *args, **options):

        if options['action'] == "status":
            self.run("Hyper Version", ["hyper", "version"])
            self.run("Current Images", ["hyper", "images"])
            self.run("Current containers", ["hyper", "ps"])
            self.run("Current Volumes", ["hyper", "volume", "ls"])
            self.run("Current Floating IP's", ["hyper", "fip", "ls"])

        if options['action'] == "clear":
            # -v = also remove the associated volume
            # -f = sigkill the contents of the container
            #
            # hyper rm -f -v failmap-worker-scanner-$id

            # todo: what about dead containers? get those too!
            containers = self.run("List all containers", ["hyper", "ps", "-a", "-q"])
            if containers:
                self.run("Kill all containers", ["hyper", "rm", "-v", "-f"] +
                         list(filter(None, containers.split('\n'))))

            volumes = self.run("List all volumes", "hyper volume ls -q".split(" "))
            if volumes:
                self.run("Removing any remaining volumes", ["hyper", "volume", "rm"] +
                         list(filter(None, volumes.split('\n'))))

            images = self.run("List all containers", ["hyper", "images", "-q"])
            if images:
                self.run("Removing any images", ["hyper", "rmi", ] + list(filter(None, images.split('\n'))))

            log.info("All Clear!")

        if options['action'] == "scantls":
            # this will use a 1 volume, 1 fip and 1 container. Will re-use a single image, which might be available.
            # we're not going to check if there already is a scanner: we'll be using a single image now for all
            # commands. So there are more than enough images.

            # get number of containers with similar names, and +1 this one.
            container_running, container_max, container_available = self.check_container_quota()
            fips_running, fips_max, fips_available = self.check_fips_quota()
            image_running, image_max, images_available = self.check_image_quota()
            volume_running, volume_max, volume_available = self.check_volume_qouta()

            if not fips_available:
                raise ValueError("No FIPS available. Get more or try again later.")

            if not container_available:
                raise ValueError("No containers available. Get more or try again later.")

            if not images_available:
                raise ValueError("No images available. Get more or try again later.")

            if not volume_available:
                raise ValueError("No volumes available. Get more or try again later.")

            exit()

            # todo: this scanner requires a FIP, so map one and check beforehand if there is one available.
            # MAX is also an option.

            id = running + 1
            from django.conf import settings
            from constance import config

            cmd = """
                hyper run --size=s3 -d --name 'failmap-worker-scanner-qualys-%(id)s'
                    -e WORKER_ROLE="scanner_qualys"         -e BROKER=redis://%(url)s:1337/0
                    -e PASSPHRASE=geheim                    -e HOST_HOSTNAME='hyperdotsh_qualys_%(id)s'
                    -e SENTRY_DSN=''                        -e C_FORCE_ROOT='true'
                    -v '%(path)s/../client.p12:/client.p12'
                    registry.gitlab.com/failmap/failmap:latest
                    celery worker --loglevel info --without-gossip --without-mingle --pool eventlet --concurrency='1'
                """ % ({'id': id, 'path': settings.BASE_DIR, 'url': config.SITE_BASE_ADDRESS})

            cmd = self.text_to_command(cmd)
            self.run("Starting tls worker %s." % id, cmd)

            # attach a FIP to this scanner
            cmd = "hyper fip attach qualys-ip-%(id)s failmap-worker-scanner-qualys-%(id)s" % {'id': id}
            self.run("Assigning FIP to scanner.", cmd)

    def text_to_command(self, cmd: str):
        # remove whitespaces and invisible characters
        return list(filter(lambda x: not re.match(r'^\s*$', x), cmd.split(' ')))

    def check_image_quota(self):
        """Returns the number of createable images"""
        lines = self.run("Current images", ["hyper", "images"])
        running = lines.count('\n') - 1
        available = HYPER_MAX_IMAGES - running
        log.debug("Images: Running: %s, Max: %s, Free: %s" % (running, HYPER_MAX_IMAGES, available))
        return running, HYPER_MAX_IMAGES, available

    # there is no quota function, as they use on their site, which is annoying as shit.
    def check_container_quota(self):
        """Return the number of creatable containers"""
        lines = self.run("Current containers", ["hyper", "ps"])
        running = lines.count('\n') - 1
        available = HYPER_MAX_CONTAINERS - running
        log.debug("Containers: Running: %s, Max: %s, Free: %s" % (running, HYPER_MAX_CONTAINERS, available))
        return running, HYPER_MAX_CONTAINERS, available

    def check_fips_quota(self):
        lines = self.run("Current Floating IP's", ["hyper", "fip", "ls"])
        running = lines.count('\n') - 1
        available = HYPER_MAX_FIPS - running
        log.debug("Fips: Running: %s, Max: %s, Free: %s" % (running, HYPER_MAX_FIPS, available))
        return running, HYPER_MAX_FIPS, available

    def check_volume_qouta(self):
        lines = self.run("Current Images", ["hyper", "images"])
        running = lines.count('\n') - 1
        available = HYPER_MAX_VOLUMES - running
        log.debug("Columes: Running: %s, Max: %s, Free: %s" % (running, HYPER_MAX_VOLUMES, available))
        return running, HYPER_MAX_VOLUMES, available

    def debug_quota(self):
        self.check_container_quota()
        self.check_image_quota()

    def run(self, label, cmd):
        log.info(label)
        log.debug(cmd)
        out = subprocess.check_output(cmd)
        pretty = out.decode('utf-8').replace('\\n', '\n')
        log.info(pretty)
        return pretty

        # start gewone scanner, ipv4 only:
        """ 
        hyper run --size=s3 -d \
        --name "failmap-worker-scanner-v4-"$id \
        -e WORKER_ROLE="scanner_v4" \
        -e BROKER=redis://failmap.co.uk:1337/0 \
        -e PASSPHRASE=geheim \
        -e HOST_HOSTNAME="hyperdotsh_"$id \
        -e SENTRY_DSN="" \
        -e C_FORCE_ROOT="true" \
        -v "/Applications/XAMPP/xamppfiles/htdocs/failmap/hyper/co.uk/client.p12:/client.p12" \
        registry.gitlab.com/failmap/failmap:latest \
        celery worker --loglevel info --without-gossip --without-mingle --pool eventlet --concurrency="4"
        
        """
