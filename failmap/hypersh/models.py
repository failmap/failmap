import logging
import random
import re
import subprocess
import tempfile
import time
import traceback
from base64 import b64decode

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django_fsm import FSMField, transition
from django_fsm_log.models import StateLog
from hyper_sh import Client
from raven.contrib.django.raven_compat.models import client

from ..celery import app

DEFAULT_IMAGE = 'failmap/failmap:latest'
DEFAULT_COMMAND = 'celery worker --loglevel=info --concurrency=1'

MAX_ERROR_COUNT = 5
STATE_FIELDS = ['last_error', 'error_count', 'state']

log = logging.getLogger(__name__)


class ScaleException(Exception):
    pass


class Credential(models.Model):
    """API authentication for Hyper.sh."""

    name = models.CharField(max_length=30)

    region = models.CharField(
        max_length=64,
        help_text="Currently choose between: eu-central-1 and us-west-1. "
                  "See https://docs.hyper.sh/hyper/Introduction/region.html"
    )

    access_key = models.CharField(max_length=64)
    secret_key = models.CharField(max_length=64)

    communication_certificate = models.TextField(
        max_length=8000,
        null=True,
        blank=True,
        help_text="A Base64 representation of a valid failmap .p12 certificate. You can create these yourself and "
                  "use these certificates to enter the admin interface. This certificate encrypts traffic between "
                  "failmap and it's workers. Do not share this certificate with anyone else, as they might get "
                  "access to the admin interface. (this feature will be better / more easily implemented someday "
                  "hopefully). You can create this value by running base64 filename. Do not use an online base64"
                  " service as that will leak your certificate :)."
    )

    enabled = models.BooleanField(default=True, help_text="Allow these credentials to be used.")

    valid = models.BooleanField(help_text="")
    last_validated = models.DateTimeField(null=True)
    last_result = models.TextField(default="{}")

    def __str__(self):
        return self.name

    @property
    def last_validate(self):
        """Return datetime when last validated."""

        return self.actions.latest('time').time

    @property
    def endpoint(self):
        """Return API endpoint for region."""

        return "https://%s.hyper.sh:443/v1.23" % self.region

    @property
    def client_config(self):
        """Return config object for hyper_sh."""

        return {
            'clouds': {
                self.endpoint: {
                    'accesskey': self.access_key,
                    'secretkey': self.secret_key,
                    'region': self.region,
                }
            }
        }

    @property
    def client(self):
        """Return client object for these credentials."""
        return Client(self.client_config)

    def validate(self):
        """Validate credentials against Hyper.sh."""

        if not self.enabled:
            return False

        try:
            self.valid = True
            self.last_result = self.client.info()
        except BaseException as e:
            self.valid = False
            sentry_id = client.captureException()
            if sentry_id:
                self.last_result = 'Error: {e}\nSentry: {project_url}/?query={sentry_id}'.format(
                    e=e,
                    project_url=settings.SENTRY_PROJECT_URL,
                    sentry_id=sentry_id,
                )
            else:
                self.last_result = 'Error: {e}'.format(e=e)
            raise

        self.last_validated = timezone.now()
        self.save(update_fields=['last_validated', 'valid', 'last_result'])

        return self.valid

    def nuke(self):
        self.task_nuke.apply_async(args=(self,))

    @app.task
    def task_nuke(self):
        """Removes all containers, volumes and images. You'll start with a clean slate."""

        # This part of the API also doesn't work anymore and has been replaced with command line functions. Too bad!
        # TypeError: 'ContainerCollection' object is not callable. You might be trying to use the old (pre-2.0) API -
        # use docker.APIClient if so.

        containers = self.hyper_cmd_run("List all containers", ["ps", "-a", "-q"])
        if containers:
            self.hyper_cmd_run("Kill all containers", ["rm", "-v", "-f"] + list(filter(None, containers.split('\n'))))

        volumes = self.hyper_cmd_run("List all volumes", ["volume", "ls", "-q"])
        if volumes:
            self.hyper_cmd_run("Removing any remaining volumes", ["volume", "rm"] +
                               list(filter(None, volumes.split('\n'))))

        images = self.hyper_cmd_run("List all containers", ["images", "-q"])
        if images:
            self.hyper_cmd_run("Removing any images", ["rmi", ] + list(filter(None, images.split('\n'))))

        log.info("All Clear!")

    def hyper_status(self):
        """Returns extensive status information"""
        status = ""
        status += "\n\nVersion:\n"
        status += self.hyper_cmd_run("Hyper Version", ["version"])
        status += "\n\nQuota (upper limits not available here):\n"
        status += str(self.quota_check("images", 0)) + '\n'
        status += str(self.quota_check("volumes", 0)) + '\n'
        status += str(self.quota_check("fips", 0)) + '\n'
        status += str(self.quota_check("containers", 0)) + '\n'
        status += "\n\nImages:\n"
        status += self.hyper_cmd_run("Current Images", ["images"])
        status += "\n\nContainers:\n"
        status += self.hyper_cmd_run("Current containers", ["ps", "-a"])
        status += "\n\nVolumes:\n"
        status += self.hyper_cmd_run("Current Volumes", ["volume", "ls"])
        status += "\n\nFIPS:\n"
        status += self.hyper_cmd_run("Current Floating IP's", ["fip", "ls"])
        return status

    def quota_check(self, what, max):
        c = {'images': ["images"], 'volumes': ["volume", "ls", "-q"], 'fips': ['fip', 'ls'], 'containers': ['ps', '-a']}
        running = self.hyper_cmd_run('Quota check for %s' % what, c[what])

        # something is off with the volumes output (at least at 0 volumes)
        if what in ['volumes']:
            running = running.count('\n')
        else:
            running = running.count('\n') - 1

        available = max - running
        log.debug("Fips: Running: %s, Max: %s, Free: %s" % (running, max, available))
        return {'what': what, 'running': running, 'max': max, 'available': available}

    def hyper_cmd_run(self, label, cmd):
        hyper_config_dir = self.create_tmp_hyper_config()
        log.info(label)

        # add the standard hyper command:
        stdcmd = ["hyper", "--config="+hyper_config_dir]

        cmd = stdcmd + cmd

        log.debug(cmd)
        out = subprocess.check_output(cmd)
        pretty = out.decode('utf-8').replace('\\n', '\n')
        log.info(pretty)
        return pretty

    def create_tmp_hyper_config(self):

        # you need a serparate dir per config file...
        # you need to manually delete this... which we currently wont.
        tmp_dir = tempfile.mkdtemp()

        """Writes credentials file for this Credential"""

        full_config = """
        {
            "auths": {},
            "clouds": {
                "tcp://*.hyper.sh:443": {
                    "accesskey": "%(accesskey)s",
                    "secretkey": "%(secretkey)s",
                    "region": "%(region)s"
                }
            }
        }
        """ % {'accesskey': self.access_key, 'secretkey': self.secret_key, 'region': self.region}

        with open(tmp_dir + '/config.json', 'w') as file:
            file.write(full_config)

        return tmp_dir

    @app.task
    def task_validate(self):
        return self.validate()

    def save(self, *args, **kwargs):
        """Verify credentials after they have been changed."""
        super().save(*args, **kwargs)
        is_validation_save = 'last_validated' in kwargs.get('update_fields', [])
        if not is_validation_save:
            self.task_validate.apply_async(args=(self,))


class ContainerEnvironment(models.Model):
    """Single environment variable for docker container."""
    name = models.CharField(max_length=64)
    value = models.TextField()

    configuration = models.ManyToManyField('hypersh.ContainerConfiguration')
    group = models.ManyToManyField('hypersh.ContainerGroup')

    def __str__(self):
        return "{name}={value}".format(**self.__dict__)


class ContainerConfiguration(models.Model):
    """All parameters required for a running a (group of) containers."""

    name = models.CharField(max_length=30)
    image = models.CharField(max_length=200, default=DEFAULT_IMAGE)
    command = models.CharField(max_length=200, default=DEFAULT_COMMAND)
    environment = models.ManyToManyField(ContainerEnvironment)
    volumes = models.CharField(max_length=200, help_text="Comma separated list of volumes.")
    instance_type = models.CharField(
        max_length=2,
        default='S1',
        help_text="Container sizes are described here: https://hyper.sh/hyper/pricing.html - In most cases S3 will "
                  "suffice. The smaller, the cheaper."
    )
    requires_unique_ip = models.BooleanField(
        default=False,
        help_text="When set to true, a FIP is connected to this container. Make sure those are available."
    )

    def __str__(self):
        return self.name

    @property
    def as_dict(self):
        """Return configuration as directory of arguments that can be passed to hypersh API."""

        # update hyper certificate, rendered from settings to a certain path.

        return {
            'image': self.image,
            'command': self.command,
            'volumes': self.volumes.split(','),
        }


class ContainerGroup(models.Model):
    """Scaling parameters for a group of containers"""

    name = models.CharField(max_length=30)

    enabled = models.BooleanField(default=True,
                                  help_text="When disabled are containers are removed and scaling is not possible.")

    credential = models.ForeignKey(Credential, on_delete=models.PROTECT)
    configuration = models.ForeignKey(ContainerConfiguration, on_delete=models.PROTECT)
    environment_overlay = models.ManyToManyField(ContainerEnvironment)

    # scaling configuration
    minimum = models.IntegerField(default=0)
    maximum = models.IntegerField(default=1)
    desired = models.IntegerField(default=1)

    # use django-fsm to manage state
    state = FSMField(default='new')
    last_error = models.TextField(default='')
    error_count = models.IntegerField(default=0)
    current = models.IntegerField(default=0)

    last_error.allow_tags = True

    def __str__(self):
        return self.name

    @property
    def environment(self):
        return self.configuration.environment.all() | self.environment_overlay.all()

    @property
    def client(self):
        """Return validated client."""
        if not self.credential.validate():
            raise Exception('Credentials disabled or invalid.')

        return self.credential.client

    @property
    def last_update(self):
        """Return date for most recent state change."""
        return StateLog.objects.for_(self).latest().timestamp

    def save(self, *args, **kwargs):
        """If after a save a scaling action is required enqueue a task for this."""
        super().save(*args, **kwargs)

        # prevent creating concurrent scaling tasks or exponential task spawning
        state_field_change = set(kwargs.get('update_fields', [])).intersection(set(STATE_FIELDS))
        is_scaling = self.state not in ['idle', 'new', 'error']
        disabled = not self.enabled
        if disabled or is_scaling or state_field_change:
            return

        self.scale_action.apply_async(args=(self,))

    @transition(field=state, target='idle')
    def reset_state(self):
        """Reset scaling state in case it does not reflect current state."""
        self.state = 'idle'
        self.save(update_fields=['state'])

    @app.task
    def scale_action(self):
        """Evaluate current state to desired and perform actions to reach desired state.

        This is the 'engine', it is run in a separate thread/task when the object changes or
        at regular intervals to ensure state.
        """

        # state is used as a crude lock to prevent multiple simultanious scaling actions
        if self.state not in ['idle', 'error']:
            raise Exception('concurrent scaling actions')
        self.state = 'scaling'
        self.last_error = ''
        self.error_count = 0
        self.save(update_fields=['state', 'last_error', 'error_count'])

        # get latest state changes from user and real world
        self.refresh_from_db()
        self.update()

        while self.current is not self.desired and self.error_count < MAX_ERROR_COUNT:
            # get latest state changes from user and real world
            self.refresh_from_db()
            self.update()

            if self.current < self.desired:
                log.info('Updating image')
                self.state = 'updating image'
                self.save(update_fields=['state'])
                self.pull_image()

                log.info('Scaling up')
                self.state = 'scaling up'
                self.save(update_fields=['state'])

                self.create_container()
            elif self.current > self.desired:
                log.info('Scaling down')
                self.state = 'scaling down'
                self.save(update_fields=['state'])

                self.destroy_container()
            time.sleep(1)

        if self.error_count >= MAX_ERROR_COUNT:
            self.state = 'error'
        else:
            log.info('Idle')
            self.state = 'idle'
            self.last_error = ''
            self.error_count = 0
        self.save(update_fields=['state', 'last_error', 'error_count'])

    def update(self):
        """Update current object state based on real-world state."""
        try:
            # all = Also get terminated containers.
            containers = self.client.containers.list(all=True, filters={'label': 'group=' + slugify(self.name)})
        except BaseException as e:
            log.exception('failed to start container')
            sentry_id = client.captureException()
            if sentry_id:
                self.last_error = '{e}\nSentry: {project_url}/?query={sentry_id}'.format(
                    e=e,
                    project_url=settings.SENTRY_PROJECT_URL,
                    sentry_id=sentry_id,
                )
            else:
                self.last_error = e
            self.error_count += 1
            self.save(update_fields=['last_error', 'error_count'])
        else:
            self.current = len(containers)
            self.save(update_fields=['current'])

    def pull_image(self):
        try:
            log.debug("pulling latest image")
            self.client.images.pull(self.configuration.as_dict['image'],
                                    auth_config="hack")  # prevent docker api from having auth issues
        except BaseException as e:
            log.exception('failed to pull image')
            sentry_id = client.captureException()
            if sentry_id:
                self.last_error = '{e}\nSentry: {project_url}/?query={sentry_id}'.format(
                    e=e,
                    project_url=settings.SENTRY_PROJECT_URL,
                    sentry_id=sentry_id,
                )
            else:
                self.last_error = e
            self.error_count += 1
            self.save(update_fields=['last_error', 'error_count'])
            raise

    def create_container(self):
        try:
            log.debug("running container")

            conf = self.configuration.as_dict

            # create a temporary file with certificate information. Will be deleted asap.
            # will leak the certificate if temporaryfile can be accessed by others etc.
            # you really need to save it... can't unlink it manually as exceptions below will make sure it remains.
            # starting containers can be really slow.
            with tempfile.NamedTemporaryFile(delete=False) as tmp_certfile:
                tmp_certfile.write(b64decode(self.credential.communication_certificate))
                tmp_certfile.flush()  # make sure it's actually written.

            # Give $certificate the correct name and id:
            conf['volumes'] = [volume.replace("$certificate", tmp_certfile.name) for volume in conf['volumes']]

            """
            You'll see that we use commands to perform certain hyper operations. This is due to the mismatch with the
            wrapped docker API and the hyper API. Hyper API looks more like the docker 1.0 API which has been
            deprecated a while. This means that you'll have to find another way to send commands to hyper.

            Simply sending POST commands doesn't work, given the amazon integrity code which is not really simple
            and easy to understand (perhaps there is someone who added that to the requests library, but didn't check).

            With code inspection you will see all kinds of nice functions that you can't use. The API of hyper is
            leading and you'll have to figure out what's available in their documentation.

            Things such as HostConfig are not available in the new API and will result in an error.
            """

            env = ["-e " + str(x) for x in self.environment.all()]
            env = " ".join(env)

            volumes = " ".join(conf['volumes'])
            if volumes:
                volumes = "-v " + volumes

            container_id = random.randint(0, 10000000)

            # get you command injection ready! Because here we go down a terrible road...
            container_name = "fail-%(name)s-%(id)s" % {'name': slugify(self.name), 'id': container_id}

            # Check if we need a FIP BEFORE we create the container, if there is no free FIP, then don't create
            # the container! - This is not a transaction, it will fail sometimes.
            if self.configuration.requires_unique_ip:
                fip_name = self.get_fip()
                if not fip_name:
                    raise BaseException("No FIP available, while container needs one. Get more FIPS!")

            cmd = \
                "run --size=%(size)s -d --label %(lbl)s --name %(name)s %(env)s %(vol)s %(image)s %(cmd)s" \
                % ({'id': container_id, 'env': env, 'vol': volumes, 'image': conf['image'],
                    'cmd': conf['command'], 'size': self.configuration.instance_type, 'name': container_name,
                    'lbl': 'group=%s' % slugify(self.name)})

            cmd = list(filter(lambda x: not re.match(r'^\s*$', x), cmd.split(' ')))
            log.info(cmd)
            output = self.credential.hyper_cmd_run("Creating container", cmd)

            # if pretty ends on something like: e7239e4f30ec38319095a47eed13c122e804ac316c7e7e553588f6a17246e86a
            # then the container was succesfully created.
            if re.findall(r'[a-f0-9]{64}', output):
                log.info("Container succesfully started.")
            else:
                raise BaseException("Could not create container. Output: " + output)

            # some containers need a FIP, this has to be configured, and that isn't happening yet.
            if self.configuration.requires_unique_ip:
                # assign a FIP.
                fip_name = self.get_fip()
                if not fip_name:
                    raise BaseException("No FIP available, while container needs one. Get more FIPS!")
                cmd = ["fip", "attach", fip_name, container_name]
                self.credential.hyper_cmd_run("Attaching FIP", cmd)

        except BaseException as e:
            log.exception('failed to start container')
            sentry_id = client.captureException()
            if sentry_id:
                self.last_error = '{e}\nSentry: {project_url}/?query={sentry_id}'.format(
                    e=e,
                    project_url=settings.SENTRY_PROJECT_URL,
                    sentry_id=sentry_id,
                )
            else:
                self.last_error = str(e) + str(traceback.print_exc())
            self.error_count += 1
            self.save(update_fields=['last_error', 'error_count'])
        else:
            self.last_error = ''
            self.error_count = 0
            self.save(update_fields=['last_error', 'error_count'])

    def get_fip(self):
        """Returns the name of the first available FIP."""
        name = ""
        output = self.credential.hyper_cmd_run("Listing FIPS", ['fip', 'ls'])
        for line in output.split('\n'):
            if line:
                elements = line.split()
                if len(elements) == 2:  # ip and name
                    return elements[1]
        return name

    def destroy_container(self):
        """Remove one container."""
        log.debug("removing container")
        # -v = also remove associated volume
        self.client.containers.list(all=True, filters={'label': 'group=' + slugify(self.name)})[0].remove(
            force=True, v=True)


@app.task
def check_scaling():
    """Create tasks for each container group to check if scaling actions are required."""
    for group in ContainerGroup.objects.filter(enabled=True, state__in=['idle', 'new', 'error']):
        group.scale_action.apply_async(args=(group,))
