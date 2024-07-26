import logging
from typing import List
import json

from celery import group

from websecmap.celery import app
from websecmap.organizations.models import Organization, UrlWhois, Url
from websecmap.scanners.scanmanager import store_url_scan_result


log = logging.getLogger(__name__)


SCANNER_NAME = "whois_domain_ownership"


@app.task(queue="database", ignore_result=True)
def scan():
    # whois_domain_ownership
    # On url:
    # - whois_internal_ownership
    # - whois_external_ownership
    # - whois_unknown_ownership
    #
    # this is not implemented as a scanner-per-url because it's an quick database-level formality which isn't worth the
    # administrative overhead of scan management.
    tasks = group([regenerate_registrant_statistics_for_all_organizations.si(), check_ownership.si()])
    tasks.apply_async()


@app.task(queue="storage", ignore_result=True)
def check_ownership():
    # acceptable_domain_registrants
    # A URL can be in multiple organizations, this means that the domain has to be owned by one of these organisations
    # if it's not, then there is an issue.
    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False, computed_subdomain="")
    for url in urls:
        # gather all allowed registrants.
        registrants = get_registrants_for_url(url)
        if not registrants:
            # if there is no registrant information, judging will be unfair
            continue

        whois = UrlWhois.objects.all().filter(url=url, is_the_latest=True).first()
        if not whois:
            # can't judge if there is no whois info, so don't...
            continue

        evidence = json.dumps(
            {
                "found_registrant": whois.registrant,
                "known_acceptable_registrants": registrants,
            }
        )
        # It's dubious when a registration from the government cannot be seen/verified
        if whois.registrant == "":
            store_url_scan_result(SCANNER_NAME, url.id, "whois_unknown_ownership", "whois_unknown_ownership", evidence)
            continue

        # comparison is done in lowercase to make obvious typos not a problem. Aka: "De Connectie" / "de CONNECTIe"
        lc_registrants = [registrant.lower() for registrant in registrants]

        owner = "whois_internal_ownership" if whois.registrant.lower() in lc_registrants else "whois_external_ownership"
        store_url_scan_result(SCANNER_NAME, url.id, owner, owner, evidence)


def get_registrants_for_url(url: Url) -> List[str]:
    registrants = []

    for organization in url.organization.all():
        registrants += organization.acceptable_domain_registrants

    return registrants


@app.task(queue="storage", ignore_result=True)
def regenerate_registrant_statistics_for_all_organizations():
    # get all registrant data from urls of this organization, then count the number of domains per registrant
    organizations = Organization.objects.all().filter(is_dead=False)
    for organization in organizations:
        log.debug("Regenerating registrant statistics for organization %s", organization)
        registrant_stats = {}
        urls = Url.objects.all().filter(
            organization=organization, is_dead=False, not_resolvable=False, computed_subdomain=""
        )
        for url in urls:
            log.debug("Regenerating registrant statistics for url %s", url)

            if whois := UrlWhois.objects.all().filter(url=url, is_the_latest=True).first():
                if whois.registrant not in registrant_stats:
                    registrant_stats[whois.registrant] = {"urls": [], "amount": 0}

                log.debug("Registrant statistics for url %s: %s", url, whois)
                registrant_stats[whois.registrant]["amount"] += 1
                registrant_stats[whois.registrant]["urls"].append(url.url)

        log.debug("Registrant statistics for organization %s: %s", organization, registrant_stats)
        organization.computed_domain_registrant_statistics = registrant_stats
        # it's easier to delete stuff than add stuff, so just add all new keys as being legit
        if not organization.acceptable_domain_registrants:
            all_registrants = list(registrant_stats.keys())
            # never allow the empty registrant
            if "" in all_registrants:
                all_registrants.remove("")

            # remove all not allowed registrants:
            leftover = list(set(all_registrants) - set(organization.not_allowed_registrant_names))

            organization.acceptable_domain_registrants = leftover
        organization.save()


def remove_not_allowed_registrants_from_acceptable_domain_registrants():
    organizations = Organization.objects.all().filter(is_dead=False)
    for org in organizations:
        leftover = list(set(org.acceptable_domain_registrants) - set(org.not_allowed_registrant_names))
        org.acceptable_domain_registrants = leftover
        org.save()


def move_non_structured_reasoning_to_structured_reasoning():
    for org in Organization.objects.all():
        if org.reasoning_for_registrant_decisions:
            lines = org.reasoning_for_registrant_decisions.split("\n")
            for line in lines:
                clean_line = line.strip()
                clean_line = clean_line.replace('"', "")
                clean_line = clean_line.replace(",", "")
                clean_line = clean_line.split(":", 1)[0]
                if clean_line and clean_line not in org.not_allowed_registrant_names:
                    org.structured_reasoning_for_registrant_decisions.append(
                        {"registrant": clean_line.strip(), "reason": "bulk removed"}
                    )
                    org.save()
