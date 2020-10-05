import csv
from datetime import datetime
from io import StringIO

import pytz
from django.db.models import Q

import logging

from websecmap.api.models import SIDNUpload
from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration
from websecmap.organizations.models import Url


log = logging.getLogger(__package__)


def get_uploads(user):
    # last 500 should be enough...
    uploads = SIDNUpload.objects.all().filter(by_user=user).defer("posted_data")[0:500]

    serialable_uploads = []
    for upload in uploads:
        serialable_uploads.append(
            {
                "when": upload.at_when.isoformat(),
                "state": upload.state,
                "amount_of_newly_added_domains": upload.amount_of_newly_added_domains,
                "newly_added_domains": upload.newly_added_domains,
            }
        )

    return list(serialable_uploads)


def get_uploads_with_results(user):
    uploads = (
        SIDNUpload.objects.all()
        .filter(by_user=user, amount_of_newly_added_domains__gt=0)
        .defer("posted_data")
        .order_by("-at_when")
    )

    serialable_uploads = []
    for upload in uploads:
        serialable_uploads.append(
            {
                "when": upload.at_when.isoformat(),
                "state": upload.state,
                "amount_of_newly_added_domains": upload.amount_of_newly_added_domains,
                "newly_added_domains": upload.newly_added_domains,
            }
        )

    return list(serialable_uploads)


def remove_last_dot(my_text):
    return my_text[0 : len(my_text) - 1] if my_text[len(my_text) - 1 : len(my_text)] == "." else my_text


@app.task(queue="storage")
def sidn_domain_upload(user, csv_data):
    """
    If the domain exists in the db, any subdomain will be added.
    As per usual, adding a subdomain will check if the domain is valid and resolvable.

    Format:
    ,2ndlevel,qname,distinct_asns
    *censored number*,arnhem.nl.,*.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,01.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfg.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,03.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,04www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfgs.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,10.255.254.35www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,12.arnhem.nl.,*censored number*
    :return:
    """

    if not csv_data:
        return

    # all mashed up in a single routine, should be separate tasks...
    upload = SIDNUpload()
    upload.at_when = datetime.now(pytz.utc)
    upload.state = "new"
    upload.by_user = user
    upload.posted_data = csv_data
    upload.save()


@app.task(queue="storage")
def sidn_process_upload(amount: int = 25):
    uploads = SIDNUpload.objects.all().filter(state__in=["processing", "new"])[0:amount]
    for upload in uploads:
        # make sure it's not happening twice:
        # Unfortunately no 'timeout and reset feature if failed', not enough time to build that.
        # just set that manually.
        upload.state = "being_processed"
        upload.save()
        sidn_handle_domain_upload.apply_async([upload.id])


@app.task(queue="storage")
def sidn_handle_domain_upload(upload_id: int):
    log.debug(f"Processing sidn data from {upload_id}")

    upload = SIDNUpload.objects.all().filter(id=upload_id).first()

    if not upload:
        log.debug(f"Could not find upload {upload_id}.")
        return

    csv_data = upload.posted_data

    f = StringIO(csv_data)
    reader = csv.reader(f, delimiter=",")
    added = []

    for row in reader:

        if len(row) < 4:
            continue

        # skip header row
        if row[1] == "2ndlevel":
            continue

        log.debug(f"Processing {row[2]}.")

        existing_second_level_url = (
            Url.objects.all()
            .filter(
                Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
                url=remove_last_dot(row[1]),
                is_dead=False,
            )
            .first()
        )

        if not existing_second_level_url:
            log.debug(f"Url '{remove_last_dot(row[1])}' is not in the database yet, so cannot add a subdomain.")
            continue

        if existing_second_level_url.uses_dns_wildcard:
            log.debug(f"Url '{existing_second_level_url}' uses a wildcard, so cannot verify if this is a real domain.")
            continue

        if existing_second_level_url.do_not_find_subdomains:
            log.debug(f"Url '{existing_second_level_url}' is not configures to allow new subdomains, skipping.")
            continue

        if row[2] == row[1]:
            log.debug("New subdomain is the same as domain, skipping.")
            continue

        if remove_last_dot(row[2]) == remove_last_dot(row[1]):
            log.debug("New subdomain is the same as domain, skipping.")
            continue

        # the entire domain is included, len of new subdomain + dot (1).
        new_subdomain = extract_subdomain(row[2], row[1])

        # domains like *.arnhem.nl are useless:
        if "*" in new_subdomain:
            log.debug("Wildcard found in subdomain, skipping.")
            continue

        log.debug(f"Going to try to add add {new_subdomain} as a subdomain to {row[1]}. Pending to correctness.")

        has_been_added = existing_second_level_url.add_subdomain(new_subdomain, "added via SIDN")
        if has_been_added:
            added.append(has_been_added)

    upload.state = "done"
    upload.amount_of_newly_added_domains = len(added)
    upload.newly_added_domains = [url.url for url in added]
    upload.save()


def extract_subdomain(new_subdomain, domain):
    """
    IN: 01daf671c183434584727ff1c0c29af1.arnhem.nl, arnhem.nl.
    OUT: 01daf671c183434584727ff1c0c29af1
    """
    log.debug(f"Extracting subdomain, new_subdomain: {new_subdomain}, domain: {domain}")
    extracted = new_subdomain[0 : (len(new_subdomain) - 1) - len(domain)]
    log.debug(f"Extracted: {extracted}")
    return extracted


def get_map_configuration():
    # Using this, it's possible to get the right params for 2ndlevel domains

    configs = (
        Configuration.objects.all().filter(is_displayed=True, is_the_default_option=True).order_by("display_order")
    )

    data = []
    for map_config in configs:
        data.append({"country": map_config.country.code, "layer": map_config.organization_type.name})

    return data


def get_2ndlevel_domains(country, layer):
    """
    This is a starting point for SIDN to upload information for domains. This is basically a list of all
    2nd level domains for a layer. Data for this is uploaded.
    """
    urls = (
        Url.objects.all()
        .filter(
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            organization__country=get_country(country),
            organization__type=get_organization_type(layer),
        )
        .values_list("url", flat=True)
    )

    urls = list(set(urls))

    return urls
