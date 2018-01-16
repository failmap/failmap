"""Generic Types for type hinting."""

from .celery import Task

# template for compose_task function


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    :param organizations_filter: dict: limit organizations to scan to these filters, see below
    :param urls_filter: dict: limit urls to scan to these filters, see below
    :param endpoints_filter: dict: limit endpoints to scan to these filters, see below

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a taskset will be composed to allow scanning of these items.

    By default all elegible items will be scanned. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> task = compose_task(organizations={'name__iexact': 'example'})
    >>> result = task.apply_async()
    >>> print(result.get())

    (`name__iexact` matches the name case-insensitive)

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> task = compose_task(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

    """
    raise NotImplementedError()
