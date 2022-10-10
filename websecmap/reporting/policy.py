from websecmap.app import log
from websecmap.reporting import time_cache
from websecmap.reporting.models import ScanPolicy

CACHE_DURATION_SECONDS = 600
CACHE = {}


def conclusion_to_score(scan: str = "", conclusion: str = "") -> ScanPolicy:
    """
    Retrieve the severity from the database in a combination of test name and the conclusion that has been found.
    How to get to that conclusion can of course be a very complex set of conditions.
    It will also retrieve an explanation.

    All policy data is cached for 10 minutes

    So:
    - Something gets scanned, this results in a 'rating' / a metric
    - This rating is converted to a conclusion, such as 'missing_header' in severity.py
    - The conclusion is converted to actual rating such as high/medium/low/error etc...

    It's basically what 'severity' used to do, but hard coded. Now we can convert a conclusion from severity
    to any set of scores we need.
    """
    key = f"{scan}{conclusion}"
    if cached := time_cache.cache_get(key):
        return cached

    if policy := ScanPolicy.objects.all().filter(scan_type=scan, conclusion=conclusion).first():
        time_cache.cache_set(key, policy)
        return policy

    # You'll get an empty score, or should we now add an empty policy to be 'self repairing'. I think so, as there
    # are tons and tons of metrics available and it's easy to miss one in a migration. Then it at least gives a
    # sense of control. Some ratings might also change over time, for example, qualys might add a 'Q' score. That
    # should not stop the software, only skew the results a bit until that score is set up properly.
    log.warning(
        "Could not find a policy, cannot convert conclusion to a score. Creating ad hoc policy. "
        "Please configure this policy in the admin interface.",
        extra={"scan": scan, "conclusion": conclusion},
    )
    log.debug({"scan": scan, "conclusion": conclusion})

    ad_hoc_sp = ScanPolicy()
    ad_hoc_sp.scan_type = scan
    ad_hoc_sp.conclusion = conclusion
    ad_hoc_sp.annotation = "Missing policy added automatically. Please set up any explanation and scoring if needed."
    ad_hoc_sp.save()

    return ad_hoc_sp
