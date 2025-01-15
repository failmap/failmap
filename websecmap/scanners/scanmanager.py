from django.urls import reverse
from websecmap.app.constance import constance_cached_value

import logging
from datetime import datetime, timezone
from typing import Any, TypeAlias, Union

from django.core.exceptions import ObjectDoesNotExist

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Url, UrlGenericScan
from django.db import transaction
from statshog.defaults.django import statsd

log = logging.getLogger(__package__)

# TODO: this is ugly, but for to not go to deep
Meaning: TypeAlias = Any


def store_endpoint_scan_result(
    scan_type: str, endpoint_id: int, rating: str, message: str, evidence: str = "", meaning: Meaning | None = None
) -> EndpointGenericScan:
    log.debug(
        "Storage requested for scan type %s, endpoint_id %s, rating: %s, message: %s, meaning: %s",
        scan_type,
        endpoint_id,
        rating,
        message,
        str(meaning),
    )

    # perform some normalization to prevent " present" and "present" causing separate metrics
    # the cast is needed. The database columns are strings, but the data =given to the method are sometimes integers
    # or lists...
    rating = str(rating).strip()
    message = str(message).strip()
    evidence = str(evidence).strip()

    # set meaning to a sane default, it is NOT a string, but a json storage object.
    # set the mutable object (thus change it) to a default value to prevent "" and "{'':''}" etc from being needed.
    if not meaning:
        meaning = {}

    # Check if the latest scan has the same rating or not:
    try:
        epgs = EndpointGenericScan.objects.all().filter(type=scan_type, endpoint=endpoint_id).latest("last_scan_moment")
        exists = True
    except ObjectDoesNotExist:
        exists = False
        epgs = EndpointGenericScan()

    # To deduplicate data, only store changes to scans. We'll update just the scan moment, and the rest stays the same.
    # The amount of data saved runs in the gigabytes. So it's worth the while doing it like this :)
    # in privacy metrics the rating may stay the same but the evidence can change. Make sure that this change
    # in evidence is reflected.
    if epgs.explanation == message and epgs.rating == rating and epgs.evidence == evidence and epgs.meaning == meaning:
        log.debug("Scan had the same rating, message and evidence, updating last_scan_moment only.")
        epgs.last_scan_moment = datetime.now(timezone.utc)
        epgs.save(update_fields=["last_scan_moment"])
        statsd.incr("scanmanager_endpoint_metric_update_amount", 1, tags={"type": scan_type})

        log.debug(
            "URL result saved as: %s, %s%s",
            epgs.id,
            constance_cached_value("PROJECT_WEBSITE").rstrip("/"),
            reverse(f"admin:{epgs._meta.app_label}_{epgs._meta.model_name}_change", args=[epgs.id]),
        )

        return epgs

    # message and rating changed for this scan_type, so it's worth while to save the scan.
    if not exists:
        log.debug("No prior scan result found, creating a new one.")
    else:
        log.debug("Message or rating changed compared to previous scan. Saving the new scan result.")

    # make sure only ONE is the latest
    with transaction.atomic():
        new_epgs = EndpointGenericScan()
        # very long csp headers for example
        new_epgs.explanation = message[:255]
        new_epgs.rating = rating
        new_epgs.endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
        new_epgs.type = scan_type
        # Very long CSP headers for example take a lot of space.
        new_epgs.evidence = evidence
        new_epgs.meaning = meaning
        new_epgs.last_scan_moment = datetime.now(timezone.utc)
        new_epgs.rating_determined_on = datetime.now(timezone.utc)
        new_epgs.is_the_latest_scan = True

        # the internet.nl evidence field does not yet contain all needed information to handle the following
        # automatic explanation. We can't add that because it might have side effects. So a short fix instead of
        # a longer fix is to copy an existing explanation for a metric if it's already there.
        # this only is true for the internet.nl category metrics, as those contain the url for internet.nl reports.
        # and people want to have the link to the latest report
        # this explanation is valid in 99.9% of the cases. a better way to deal with this stuff is needed
        if scan_type == "internet_nl_mail_tls":
            if epgs.comply_or_explain_explanation == "microsoft_applies_dane_from_july_2024":
                if datetime.now(timezone.utc) < datetime(2025, 1, 1, tzinfo=timezone.utc):
                    # copy explanation
                    new_epgs.comply_or_explain_is_explained = epgs.comply_or_explain_is_explained
                    new_epgs.comply_or_explain_explanation_valid_until = epgs.comply_or_explain_explanation_valid_until
                    new_epgs.comply_or_explain_explanation = epgs.comply_or_explain_explanation
                    new_epgs.comply_or_explain_explained_by = epgs.comply_or_explain_explained_by
                    new_epgs.comply_or_explain_explained_on = epgs.comply_or_explain_explained_on
                    new_epgs.comply_or_explain_case_handled_by = epgs.comply_or_explain_case_handled_by
                    new_epgs.comply_or_explain_case_additional_notes = epgs.comply_or_explain_case_additional_notes

        new_epgs.save()
        statsd.incr("scanmanager_endpoint_metric_create_amount", 1, tags={"type": scan_type})

        # Set all the previous endpoint scans of this endpoint + type to NOT be the latest scan.
        EndpointGenericScan.objects.all().filter(
            endpoint=new_epgs.endpoint,
            type=new_epgs.type,
            # speed up by only finding the ones that are true, not all results ofc!
            is_the_latest_scan=True,
        ).exclude(pk=new_epgs.pk).update(is_the_latest_scan=False)

        log.debug(
            "URL result saved as: %s, %s/%s",
            new_epgs.id,
            constance_cached_value("PROJECT_WEBSITE").rstrip("/"),
            reverse(f"admin:{new_epgs._meta.app_label}_{new_epgs._meta.model_name}_change", args=[new_epgs.id]),
        )

    return new_epgs


def store_url_scan_result(  # pylint: disable=inconsistent-return-statements
    scan_type: str, url_id: int, rating: str, message: str, evidence: str = ""
):
    # Check if the latest scan has the same rating or not:
    try:
        ugs = (
            UrlGenericScan.objects.all()
            .filter(
                type=scan_type,
                url=url_id,
            )
            .latest("last_scan_moment")
        )
    except ObjectDoesNotExist:
        ugs = UrlGenericScan()

    # here we figured out that you can still pass a bool while type hinting.
    # log.debug("Explanation new: '%s', old: '%s' eq: %s, Rating new: '%s', old: '%s', eq: %s" %
    #           (message, gs.explanation, message == gs.explanation, rating, gs.rating, str(rating) == gs.rating))

    # last scan had exactly the same result, so don't create a new scan and just update the last scan date.
    # while we have type hinting, it's still possible to pass in a boolean and then you compare a str to a bool...
    if ugs.explanation == message and ugs.rating == rating and ugs.evidence == evidence:
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        ugs.last_scan_moment = datetime.now(timezone.utc)
        ugs.save(update_fields=["last_scan_moment"])
        statsd.incr("scanmanager_url_metric_update_amount", 1, tags={"type": scan_type})
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        log.debug("Message or rating changed: making a new generic scan.")
        # make sure only ONE is the latest
        with transaction.atomic():
            ugs = UrlGenericScan()
            ugs.explanation = message
            ugs.rating = rating
            ugs.url = Url.objects.all().filter(id=url_id).first()
            ugs.evidence = evidence
            ugs.type = scan_type
            ugs.last_scan_moment = datetime.now(timezone.utc)
            ugs.rating_determined_on = datetime.now(timezone.utc)
            ugs.is_the_latest_scan = True
            ugs.save()
            statsd.incr("scanmanager_url_metric_create_amount", 1, tags={"type": scan_type})

            UrlGenericScan.objects.all().filter(
                url=ugs.url,
                type=ugs.type,
                # speed up by only finding the ones that are true, not all results ofc!
                is_the_latest_scan=True,
            ).exclude(pk=ugs.pk).update(is_the_latest_scan=False)

        log.debug(
            "URL result saved as: %s, %s/%s",
            ugs.id,
            constance_cached_value("PROJECT_WEBSITE").rstrip("/"),
            reverse(f"admin:{ugs._meta.app_label}_{ugs._meta.model_name}_change", args=[ugs.id]),
        )

        return ugs


def endpoint_has_scans(scan_type: str, endpoint_id: int):  # pylint: disable=inconsistent-return-statements
    """
    Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
    to zero (or another rating)
    :param scan_type:
    :param endpoint_id:
    :return:
    """

    try:
        genericscan = (
            EndpointGenericScan.objects.all()
            .filter(
                type=scan_type,
                endpoint=endpoint_id,
            )
            .latest("last_scan_moment")
        )
        if genericscan.rating:
            return True
    except ObjectDoesNotExist:
        return False


def delete_metric_and_set_previous_to_latest(item: Union[EndpointGenericScan, UrlGenericScan]):
    # This helps setting the latest scan of the same scan type to "is the latest" when the latest scan is deleted.

    # no need to transfer the latest scan to another scan.
    if not item.is_the_latest_scan:
        item.delete()

    if item.__class__.__name__ == "EndpointGenericScan":
        manager = EndpointGenericScan
    else:
        manager = UrlGenericScan

    if (
        previous_item := manager.objects.filter(
            endpoint=item.endpoint,
            type=item.type,
        )
        .exclude(id=item.id)
        .order_by("-id")
        .first()
    ):
        previous_item.is_the_latest_scan = True
        previous_item.save()

    item.delete()
