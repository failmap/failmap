"""Generic Types for type hinting."""

from .celery import Task


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose a task to perform work on specified organizations/urls/endpoints.

    :param organizations_filter: dict: limit organizations to these filters, see below
    :param urls_filter: dict: limit urls to these filters, see below
    :param endpoints_filter: dict: limit endpoints to these filters, see below

    Composition of a task is building a task from primitives (task, group, chain) and other composed tasks in order
    to create a 'collection' of work that as a whole can be scheduled for execution in the task processing system.

    **Task processing system**

    At the core of Failmap is the Task processing system which ensures 'work' can be done as efficient as possible.

    For example:

    Onboarding an organization requires work that needs to be executed:

        - A default 'base' rating needs to be created.
        - URLs and endpoints belonging to the organization need to be discovered from various sources.
        - Scans need to be performed on newly found URLs and endpoints.
        - Results of scans need to be rated on their conformity.
        - All ratings need to be aggregated so a final rating for the organization can be extracted.

    Some of this work needs to be executed in-order (without urls/endpoints, no scanners can run), other work can (and
    should be) done in parallel for performance. There is work (scanners) that need a specific environment to be
    executed in (eg: IPv6 connectivity). In order to occomodate for this the work is devided into 'tasks'.

    A task is basically a function that executes code. It takes inputs, does work and generates an output, like a
    'normal' function. The difference with a 'normal' function is that a task is put into the task processing system in
    order to be executed at a later time and potentially different location depending on the rules set for the task.

    Task can be executed directly and synchronously, but must always be able to execute asynchronously. Whenever a task
    is created (eg: a user click a button on the admin page to onboard a selected organization), the task is not
    expected to give a result then and there, and the result should not be waited for. Rather a reference to the task
    is returned to the user which can be used to verify the completion of the work at a later time.

    For work that needs to be done sequentually the tasks are 'chained' where the input of one tasks can be passed on
    to the next. Work that should happen in parallel have their tasks put into `groups`. Both chains and groups are
    tasks of their own and can be chained and grouped allong with other tasks, groups and chains. Tasks can be as
    simple as a single function or as complex as described in the onboarding example. The composer always returns a
    task (task, group or chain) and this task can be used by other composers as any other task primitive.

    **Logic**

    The task composer should be implemented smart enough to convert any combination of filters into a valid task.

    The most simple example is scanning an organization. The composer should create a group of tasks for scanning all
    urls and/or endpoints of this organization.

    If a composer is not able to apply a certain type of filter it should fail to compose the task, for example: The
    rebuilding of ratings works on a URL or organization level only, as endpoints have no rating. If `endpoint_filters`
    is passed to the composer for this scanner it should fail.

    Some types of work need to operate on a different level to acquire the desired result, for example: to rebuild
    ratings two steps are required, rebuiling url ratings and rebuilding organization ratings with those new url
    ratings. If only a few urls in an organization are selected for rerating the composer should be smart enough to
    only select these url for rebuilding, but also do a organization rebuild in order to incorporate these new ratings
    in the total.

    **Further reading**

        - http://docs.celeryproject.org/en/latest/userguide/canvas.html

    **Filters**

    *For legibility reasons the text below is writen from the viewport of a scanner, but the same
    principle applies to other work as well (eg: rebuild-ratings, onboarding, etc).*

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a task will be composed to allow scanning of these items.

    By default all elegible items will be scanned. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> task = compose_task(organizations={'name__iexact': 'example'})
    >>> result = task.apply_async()
    >>> print(result.get())

    *`name__iexact` matches the name case-insensitive.*

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> task = compose_task(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

    """
    raise NotImplementedError()
