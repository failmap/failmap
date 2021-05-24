# Copyright 2021 Internet Cleanup Foundation
# SPDX-License-Identifier: AGPL-3.0-only

"""
These automated explanations match standardardized IT infrastructure. For all other comply or explain actions, use
the management interface to quickly add explanations.

The approach here is as-strict-as-possible whitelisting. This means for example that while a certain error is accepted,
other errors such as certificate expiration, mis configurations and such will still be seen as insufficient.

Local, non-vendor policies are not taken into account: they should standardize and try to comply first.
"""

import logging
from datetime import datetime, timedelta
import pytz

from websecmap.scanners.models import EndpointGenericScan

log = logging.getLogger(__package__)


def add_bot_explanation(scan: EndpointGenericScan, explanation: str, duration: timedelta):
    scan.comply_or_explain_is_explained = True
    scan.comply_or_explain_case_handled_by = "WebSecMap Explanation Bot"
    scan.comply_or_explain_explained_by = "Websecmap Explanation Bot"
    scan.comply_or_explain_explanation = explanation
    scan.comply_or_explain_explained_on = datetime.now(pytz.utc)
    scan.comply_or_explain_explanation_valid_until = datetime.now(pytz.utc) + duration
    scan.save()


def autoexplain_pki_subdomain():
    """
    todo:
    Subdomains: pki / crl

    Subdomains with certificate revocation lists do not have to have an https endpoint. It could harm the
    crl process.

    Deviation: no https endpoint is needed. If none is found, and a warning is issued, this will counteract the standard
    finding.

    :return:
    """

    # applicable_subdomains = 'pki'
    # scan_type = 'plain_https'
    raise NotImplementedError
