import logging
import time

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django_fsm import FSMField, transition
from django_fsm_log.models import StateLog
from hyper_sh import Client

from ..celery import app

DEFAULT_IMAGE = 'registry.gitlab.com/failmap/failmap:latest'
DEFAULT_COMMAND = 'celery worker --log info --concurrency 1'

log = logging.getLogger(__name__)


class ScaleException(Exception):
    pass


class Credential(models.Model):
    """API authentication for Hyper.sh."""

    name = models.CharField(max_length=30)

    region = models.CharField(max_length=64)

    access_key = models.CharField(max_length=64)
    secret_key = models.CharField(max_length=64)

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
            self.last_result = str(e)

        self.last_validated = timezone.now()
        self.save(update_fields=['last_validated', 'valid', 'last_result'])

        return self.valid

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
    value = models.CharField(max_length=64)

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

    def __str__(self):
        return self.name

    @property
    def as_dict(self):
        """Return configuration as directory of arguments that can be passed to hypersh API."""

        return {
            'image': self.image,
            'command': self.command,
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

    # use django-fsm to
    state = FSMField(default='new')
    current = models.IntegerField(default=0)

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

        state_field_change = 'state' in kwargs.get('update_fields', [])
        is_scaling = self.state not in ['idle', 'new']
        if is_scaling or state_field_change:
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
        if self.state != 'idle':
            raise Exception('concurrent scaling actions')
        self.state = 'scaling'
        self.save(update_fields=['state'])

        # get latest state changes from user and real world
        self.update()

        while self.current is not self.desired:
            # get latest state changes from user and real world
            # self.refresh_from_db()
            self.update()

            if self.current < self.desired:
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

        log.info('Idle')
        self.state = 'idle'
        self.save(update_fields=['state'])

    def update(self):
        """Update current object state based on real-world state."""
        self.current = len([c for c in self.client.containers()
                            if c['Names'][0].startswith("/%s-" % slugify(self.name))])
        self.save(update_fields=['current'])

    def create_container(self):
        container_id = slugify("%s-%d" % (self.name, self.current + 1))
        # destroy lingering container
        try:
            log.debug("removing possible previous container with same name")
            self.client.remove_container(container_id, force=True)
        except BaseException:
            pass

        try:
            environment = [str(x) for x in self.environment.all()]
            log.debug("creating container")
            self.client.create_container(
                name=container_id,
                labels={
                    'sh_hyper_instancetype': 'S1'
                },
                environment=environment,
                tty=True,
                **self.configuration.as_dict)
            log.debug("starting container")
            self.client.start(container_id)
        except BaseException:
            log.exception('failed to start container')

    def destroy_container(self):
        container_id = slugify("%s-%d" % (self.name, self.current))
        log.debug("removing container")
        self.client.remove_container(container_id, force=True)
