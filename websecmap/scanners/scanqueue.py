from typing import List, Union

from django.utils import timezone

from websecmap.scanners.models import Endpoint, EndpointScanQueue, UrlScanQueue

QUEUED_AS_URL_SCANS = ["tlsq", "plain_http"]
QUEUED_AS_ENDPOINT_SCANS = ["plain_http"]

"""
Todo: how to store discovery tasks? And verification tasks? And scans? Can this be in the same model?
"""


def update_state(sq: Union[EndpointScanQueue, UrlScanQueue], state: str, message: str, finished: bool
                 ) -> Union[EndpointScanQueue, UrlScanQueue]:

    sq.state = state
    sq.state_message = message
    sq.last_state_change = timezone.now()

    if finished:
        sq.finished_at_when = timezone.now()

    sq.save()
    return sq


def pickup(scanner, amount=25) -> List[Endpoint]:
    """
    Retrieves a list of items that need to be scanned using a specific scanner. The list might be empty if
    nothing needs to be scanned. Everything that is picked up is changed by state. Should it return endpoints?

    Todo: put into transaction.
    """

    queueds = EndpointScanQueue.objects.all().filter(scanner=scanner, state="queued")[0:amount]

    # cannot update one a slice has been taken, so we're updating them one by one:
    for queued in queueds:
        update_state(queued, state="picked_up", message="", finished=False)

    return [q.endpoint for q in queueds]


def queue_batch(endpoints: List[Endpoint], scanner: str):
    for endpoint in endpoints:
        queue(endpoint, scanner)


def queue(endpoint: Endpoint, scanner: str) -> EndpointScanQueue:
    esq = EndpointScanQueue()
    esq.created_at_when = timezone.now()
    esq.scanner = scanner
    esq.state = "queued"
    esq.endpoint = endpoint
    esq.last_state_change = timezone.now()
    esq.save()
    return esq


def update_state_on_endpoint_scan(endpoint: Endpoint, scanner: str, new_state: str, message: str = None,
                                  finished: bool = False) -> EndpointScanQueue:
    # should be registered:
    esq = EndpointScanQueue.objects.all().filter(endpoint=endpoint, scanner=scanner).last()

    # With a long running system, there is always bound to be a scan on this endpoint. Could even be queued.
    if not esq:
        raise EndpointScanQueue.DoesNotExist

    return update_state(esq, state=new_state, message=message, finished=finished)


def finish(endpoint, scanner):
    update_state_on_endpoint_scan(endpoint, scanner, "finished")


def cancel(endpoint, scanner):
    update_state_on_endpoint_scan(endpoint, scanner, "cancelled")


def timeout(endpoint, scanner, expiry_time=None):
    update_state_on_endpoint_scan(endpoint, scanner, "timed_out", "", True)


def error(endpoint: Endpoint, scanner: str, debug_message: str):
    update_state_on_endpoint_scan(endpoint, scanner, "error", debug_message, True)
