import os

from kombu import Queue

# define queues


# define roles for workers
WORKER_QUEUE_CONFIGURATION = {
    # universal worker that has access to database and internet
    'default': {
        # for tasks that require network connectivity to perform a scanning task
        Queue('scanners'),
        # allow to differentiate on scan tasks that have specific ip network family requirements
        Queue('scanners.ipv4'),
        Queue('scanners.ipv6'),
        # for tasks that require a database connection
        Queue('storage'),
        # default queue for task with no explicit queue assigned
        # these tasks should not expect network connectivity or database access!
        Queue('default'),

        # legacy default queue, can be removed after transition period to multiworkers
        Queue('celery'),
    },
    # universal scanner worker that has internet access for both IPv4 and IPv6
    'scanner': {
        Queue('scanners'),
        Queue('scanners.ipv4'),
        Queue('scanners.ipv6'),
    },
    # scanner with no IPv6 connectivity
    # this is an initial concept and can later be replaced with universal
    # scanner that automatically detects connectivity
    'scanner_ipv4_only': {
        Queue('scanners'),
        Queue('scanners.ipv4'),
    },
}


def worker_configuration(conf):
    """Apply specific configuration for worker depending on environment."""

    role = os.environ.get('WORKER_ROLE', 'default')

    # configure which queues should be consumed depending on assigned role for this worker
    conf.task_queues = WORKER_QUEUE_CONFIGURATION[role]
