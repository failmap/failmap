import json
import logging
from typing import List

from websecmap.organizations.models import Url

log = logging.getLogger(__name__)


def nuke_url(domain: str, suffix: str = "", excluded_subdomains: List[str] = None):
    # delete a url with all subdomains. Used when a domain is just nonsense or added by mistake. There is no way
    # to undo this.
    # url will look at computed_domain
    # tld will look at computed_suffix
    # excluded_subdomains will exclude domains

    log.info("Nuking url %s, with suffix %s, excluding subdomains %s", domain, suffix, excluded_subdomains)

    urls = Url.objects.all().filter(computed_domain=domain)

    if suffix:
        urls = urls.filter(computed_suffix=suffix)

    if excluded_subdomains:
        urls = urls.exclude(computed_subdomain__in=excluded_subdomains)

    amount = urls.count()
    log.info("Going to delete %s urls.", amount)

    total_deleted_items = 0

    # this is done PER url as it contains a lot of related data, this can be thousands of records,
    # and thus feel a bit slow. This makes it easier to see something is happening.
    for url in urls:
        log.debug("Deleting %s", url)
        deleted_items, data2 = url.delete()
        log.debug("Deleted %s associated records on %s, data: %s", deleted_items, url.url, json.dumps(data2))
        total_deleted_items += deleted_items

    log.info("Done, deleted %s records that where associated with %s urls.", total_deleted_items, amount)
