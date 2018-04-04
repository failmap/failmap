import logging
import os
import re
import subprocess
import time
import urllib.request
from datetime import timedelta

import pytest

log = logging.getLogger(__name__)

TIMEOUT = timedelta(seconds=int(os.environ.get('SYSTEM_TEST_TIMEOUT', 30)))
INTERVAL = timedelta(seconds=5)


@pytest.fixture(scope='session')
def failmap(docker_ip, docker_services):
    class Failmap:
        admin_url = 'http://%s:%d' % (
            docker_ip, int(docker_services('port admin 8000').split(':')[-1]),
        )
        frontend_url = 'http://%s:%d' % (
            docker_ip, int(docker_services('port frontend 8000').split(':')[-1]),
        )

        def get_admin(self, path):
            with urllib.request.urlopen(self.admin_url + path) as f:
                return (f, f.read().decode('utf-8'))

        def get_frontend(self, path):
            with urllib.request.urlopen(self.frontend_url + path) as f:
                return (f, f.read().decode('utf-8'))

    return Failmap()


@pytest.fixture(scope='session')
def docker_ip():
    """Determine IP address for TCP connections to Docker containers."""

    # When talking to the Docker daemon via a UNIX socket, route all TCP
    # traffic to docker containers via the TCP loopback interface.
    docker_host = os.environ.get('DOCKER_HOST', '').strip()
    if not docker_host:
        return '127.0.0.1'

    match = re.match('^tcp://(.+?):\d+$', docker_host)
    if not match:
        raise ValueError(
            'Invalid value for DOCKER_HOST: "%s".' % (docker_host,)
        )
    return match.group(1)


@pytest.fixture(scope='session')
def docker_services(pytestconfig, docker_ip):
    """Ensure all Docker-based services are up and running."""
    docker_compose_file = os.path.join(
        str(pytestconfig.rootdir),
        'tests',
        'docker-compose.yml'
    )
    docker_compose_project_name = "pytest{}".format(os.getpid())

    def docker_compose(args, background=False):
        command = 'docker-compose --no-ansi -f "{}" -p "{}" {}'.format(
            docker_compose_file, docker_compose_project_name, args
        )
        log.info('Running command: %s', command)
        env = dict(os.environ, ALLOWED_HOSTS=docker_ip)
        if background:
            return subprocess.Popen(command, env=env, shell=True)
        else:
            return subprocess.check_output(command, env=env, shell=True, universal_newlines=True)

    docker_compose('up -d')

    # docker-compose binds port 8000 to an unique port number, extract that number here to form url
    url = 'http://%s:%d' % (docker_ip, int(docker_compose('port admin 8000').split(':')[-1]))

    print('waiting for url %s to be responsive.' % url)
    for _ in range(int(TIMEOUT.seconds / INTERVAL.seconds)):
        try:
            # verify admin is http responsive and stop waiting
            urllib.request.urlopen('url')
            print("admin instance is ready for testing")
            break
        except BaseException as e:
            print("admin instance not accessible, exception: %r, retrying in %i" % (e, INTERVAL.seconds))
            time.sleep(INTERVAL.seconds)
    else:
        # provide context as to why the containered service failed to be responsive
        for service in docker_compose('config --services').splitlines():
            docker_compose('logs -f %s' % service, background=True)
        docker_compose('down -v')
        pytest.fail(
            "admin instance at %s not accessible after %s seconds" %
            (url, TIMEOUT), pytrace=False)

    yield docker_compose

    # output logs in case the test failed, and cleanup the containers
    for service in docker_compose('config --services').splitlines():
        docker_compose('logs -f %s' % service, background=True)
    docker_compose('down -v')
