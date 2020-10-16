import csv
from datetime import datetime
from io import StringIO

import pytz
import tldextract
from django.db.models import Q

import logging

from websecmap.api.models import SIDNUpload
from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration
from websecmap.organizations.models import Url

log = logging.getLogger(__package__)

FIELD_ID = 0
FIELD_SECOND_LEVEL = 1
FIELD_QNAME = 2
FIELD_ASNS = 3


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
    Moved to reporting due to more room for delays on that queue.

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


@app.task(queue="reporting")
def sidn_process_upload(amount: int = 25):
    # Moved to reporting due to more room for delays on that queue.
    uploads = SIDNUpload.objects.all().filter(state__in=["processing", "new"])[0:amount]
    for upload in uploads:
        # make sure it's not happening twice:
        # Unfortunately no 'timeout and reset feature if failed', not enough time to build that.
        # just set that manually.
        upload.state = "being_processed"
        upload.save()
        sidn_handle_domain_upload.apply_async([upload.id])


@app.task(queue="reporting")
def sidn_handle_domain_upload(upload_id: int):
    log.debug(f"Processing sidn data from {upload_id}")

    upload = SIDNUpload.objects.all().filter(id=upload_id).first()

    if not upload:
        log.debug(f"Could not find upload {upload_id}.")
        return

    added = set(process_SIDN_row(row) for row in csv.reader(StringIO(upload.posted_data), delimiter=","))
    # remove all error situations, which return None
    added.remove(None)

    upload.state = "done"
    upload.amount_of_newly_added_domains = len(added)
    upload.newly_added_domains = [url.url for url in added]
    upload.save()


def process_SIDN_row(row):
    if len(row) < 4:
        log.debug("Row does not have the correct length.")
        return

    # skip header row
    if row[FIELD_SECOND_LEVEL] == "2ndlevel":
        log.debug("Ignoring header field.")
        return

    log.debug(f"Processing {row[FIELD_QNAME]}.")

    # We only care about the qname, field, which can be a very long domain
    # it might also not match the 2nd level in case of old domains.
    # for example: 333,arnhem.nl,www.myris.zeewolde.nl.,1 -> the 2nd level should be ignored there.
    # Do not roll your own domain extraction.
    extracted = tldextract.extract(remove_last_dot(row[FIELD_QNAME]))

    if not extracted.subdomain:
        log.debug("No subdomain found in query. Skipping.")
        return

    if "*" in extracted.subdomain:
        log.debug("Found wildcard in subdomain. Not adding this.")
        return

    second_level_domain = f"{extracted.domain}.{extracted.suffix}"
    existing_second_level_url = (
        Url.objects.all()
        .filter(
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            url=second_level_domain,
            is_dead=False,
            # We cannot verify if this is a real subdomain, as wildcards always resolve. There are ways with overhead.
            uses_dns_wildcard=False,
            # Some domains should not add new subdomains, for example large organizations with 5000 real subdomains.
            do_not_find_subdomains=False,
        )
        .first()
    )

    if not existing_second_level_url:
        log.debug(f"Url '{second_level_domain}' is not in the database yet, so cannot add a subdomain.")
        return

    log.debug(f"Attempting to add {extracted.subdomain} as a subdomain of {second_level_domain}.")
    return existing_second_level_url.add_subdomain(extracted.subdomain, "added via SIDN")


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
