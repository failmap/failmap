from websecmap.scanners.scanner import allowed_to_scan


def test_allowed_to_scan(db, default_scan_metadata):
    assert allowed_to_scan("not existing scanner") is False
    assert allowed_to_scan("dnssec") is True

    assert allowed_to_scan("dnssec", "not existing activity") is False
    assert allowed_to_scan("dnssec", "scan") is True
