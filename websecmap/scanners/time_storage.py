from datetime import timezone, datetime
from typing import Any, Dict, List

from websecmap.app import log


def abstract_time_storage(
    model: Any,
    fields_to_retrieve_latest: Dict[str, Any],
    fields_that_signify_change: List[str],
    data_for_new_record: Dict[str, Any],
):
    # abstracts the time storage / stacking pattern for many models. Originally used in EndpointGenericScan,
    # UrlGenericScan and reports. When they are refactored, they might use this method as well for simplification.

    now = datetime.now(timezone.utc)
    if existing := model.objects.all().filter(is_the_latest=True, **fields_to_retrieve_latest).first():
        existing.last_scan_moment = now
        changes = sum(
            getattr(existing, field_name) != data_for_new_record[field_name]
            for field_name in fields_that_signify_change
        )
        if changes == 0:
            log.debug("Found no changes in %s: for fields: %s", model.__name__, fields_to_retrieve_latest.keys())
            existing.save()
            return
        log.debug("Found a change in %s: %s", model.__name__, changes)

    # create it first, this might fail due to too long domain names and other things.
    created = model.objects.create(is_the_latest=True, at_when=now, last_scan_moment=now, **data_for_new_record)
    log.debug("Created new %s with id %s", model.__name__, created.pk)

    # If you are here saving went well, also save the previous record, it being not the latest anymore.
    if existing:
        log.debug("Existing %s with id %s is no longer the latest.", model.__name__, existing.pk)
        existing.is_the_latest = False
        existing.save()
