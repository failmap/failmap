import logging
import os
import re
import subprocess
import urllib

import pytest
from retry import retry

log = logging.getLogger(__name__)

TIMEOUT = 30


@pytest.fixture(scope='session')
def failmap(docker_ip, docker_services):

    url = 'http://%s:%d' % (
        docker_ip,
        int(docker_services('port admin 8000').split(':')[-1]),
    )

    log.info('Waiting for url %s to be responsive.', url)

    @retry(tries=TIMEOUT, delay=1, logger=log)
    def check():
        with urllib.request.urlopen(url) as f:
            if f.status == 200:
                return
    check()

    class Failmap:
        admin_url = url
        frontend_url = 'http://%s:%d' % (
            docker_ip,
            int(docker_services('port frontend 8000').split(':')[-1]),
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
def docker_services(pytestconfig):
    """Ensure all Docker-based services are up and running."""

    docker_compose_file = os.path.join(
        str(pytestconfig.rootdir),
        'tests',
        'docker-compose.yml'
    )
    docker_compose_project_name = "pytest{}".format(os.getpid())

    def docker_compose(args):
        command = 'docker-compose --no-ansi -f "{}" -p "{}" {}'.format(
            docker_compose_file, docker_compose_project_name, args
        )
        log.info('Running command: %s', command)
        return subprocess.check_output(command, shell=True, universal_newlines=True)

    docker_compose('up -d')

    yield docker_compose

    for service in docker_compose('config --services').splitlines():
        for line in docker_compose('logs %s' % service).splitlines():
            log.info(line)

    docker_compose('down -v')
