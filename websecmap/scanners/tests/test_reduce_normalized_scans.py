from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import UrlGenericScan
from websecmap.scanners.reduce_identical_scans import reduce_normalized_identical_scans


def test_reduce_normalized_identical_scans(db, default_policy, default_scan_metadata):
    # and a bunch of similar scans, some are explained, others are of a different type. They have a nice gradient
    # over time so we can see that some scans should be merged while others stay untouched.
    # The reduction algorithm is slow.
    # in short:

    # 01: jan 2021: test scan, out of scope, should not be touched
    # 02: feb 2021: dnssec scan (range 1), oldest one
    # 03: mar 2021: test scan, out of scope
    # 04: apr 2021: dnssec scan, a normalized duplicate of feb. The feb one should be merged into this one. This one
    # is explained, so the merged one should also be explained. (range 1)
    # 05: may 2021: dnssec scan, copy of the april one, so should have the feb 2021 scan date. End of range 1.
    # 06: jun 2021: test scan, out of scope, should not be touched
    # 07: jul 2021: other dnssec scan, range 2
    # 08: aug 2021: yet another dnssec scan (range 3), this one will be merged in the sept one
    # 09: sep 2021: latest dnssec scan from range 3.

    # in the end there should be 3 dnssec scans, where there where 6.

    # Let's setup the scenario above:
    u1 = Url.objects.create(url="range1.nl")
    u2 = Url.objects.create(url="range2.foundation")
    u3 = Url.objects.create(url="range3.com")

    # Some things that does not match the policy
    # 01
    UrlGenericScan.objects.create(
        url=u1,
        rating="G",
        type="test",
        evidence="test",
        last_scan_moment=datetime(2021, 1, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )

    # 02
    UrlGenericScan.objects.create(
        url=u1,
        rating="range 1",
        type="dnssec",
        evidence="range 1",
        last_scan_moment=datetime(2021, 2, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 2, 1, tzinfo=timezone.utc),
    )

    # 03
    UrlGenericScan.objects.create(
        url=u1,
        rating="G",
        type="test",
        evidence="test with another value",
        last_scan_moment=datetime(2021, 3, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 3, 1, tzinfo=timezone.utc),
    )

    # 04, duplicate of 02 but explained.
    UrlGenericScan.objects.create(
        url=u1,
        rating="range 1",
        type="dnssec",
        evidence="range 1",
        last_scan_moment=datetime(2021, 4, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 4, 1, tzinfo=timezone.utc),
        comply_or_explain_is_explained=True,
        comply_or_explain_explanation="explanation",
        comply_or_explain_explained_on=datetime(2021, 4, 1, tzinfo=timezone.utc),
    )

    # 05: and the copy of 4, this is the latest scan in range 1 and should be the one left. Not explained!
    # but the previous one was, so this one should be after merging.
    UrlGenericScan.objects.create(
        url=u1,
        rating="range 1",
        type="dnssec",
        evidence="range 1",
        last_scan_moment=datetime(2021, 5, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 5, 1, tzinfo=timezone.utc),
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
    )

    # 06: out of scope
    UrlGenericScan.objects.create(
        url=u1,
        rating="G",
        type="test",
        evidence="test",
        last_scan_moment=datetime(2021, 6, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 6, 1, tzinfo=timezone.utc),
    )

    # 07 the one at range 2 is just 1 scan and no duplication
    UrlGenericScan.objects.create(
        url=u2,
        rating="range 2",
        type="dnssec",
        evidence="range 2",
        last_scan_moment=datetime(2021, 7, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 7, 1, tzinfo=timezone.utc),
        is_the_latest_scan=True,
    )

    # 08: duplicate of 09
    UrlGenericScan.objects.create(
        url=u3,
        rating="range 3",
        type="dnssec",
        evidence="range 3",
        last_scan_moment=datetime(2021, 8, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 8, 1, tzinfo=timezone.utc),
    )

    # 09: leading scan for range 3
    UrlGenericScan.objects.create(
        url=u3,
        rating="range 3",
        type="dnssec",
        evidence="range 3",
        is_the_latest_scan=True,
        last_scan_moment=datetime(2021, 9, 1, tzinfo=timezone.utc),
        rating_determined_on=datetime(2021, 9, 1, tzinfo=timezone.utc),
    )

    # now reduce this as planned
    tasks = reduce_normalized_identical_scans(scan_type="dnssec")
    tasks.apply()

    # Verify that there are indeed 3 dnssec scans, and those are now from feb (range 1), jul and aug.
    # all three should be the latest scans...
    assert UrlGenericScan.objects.filter(is_the_latest_scan=True, type="dnssec").count() == 3

    # no other dnssec scans:
    assert UrlGenericScan.objects.filter(type="dnssec").count() == 3

    # the other 3 test scans are not affected
    assert UrlGenericScan.objects.filter().count() == 6

    # range 3 started in aug and ended in september:
    r3_scan = UrlGenericScan.objects.filter(url=u3, type="dnssec").first()
    assert r3_scan.last_scan_moment == datetime(2021, 9, 1, tzinfo=timezone.utc)
    assert r3_scan.rating_determined_on == datetime(2021, 8, 1, tzinfo=timezone.utc)

    # range 1 started from feb and ended in may, is also explained
    r1_scan = UrlGenericScan.objects.filter(url=u1, type="dnssec").first()
    assert r1_scan.last_scan_moment == datetime(2021, 5, 1, tzinfo=timezone.utc)
    assert r1_scan.rating_determined_on == datetime(2021, 2, 1, tzinfo=timezone.utc)
    assert r1_scan.comply_or_explain_is_explained is True
