from websecmap.scanners.scanner.internet_nl_websecmap import calculate_ipv6_views_mail, calculate_ipv6_views_web


def test_v6_web_v6_ready():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["web_ipv6_ns_address"] = {"status": "passed"}
    ref["web_ipv6_ns_reach"] = {"status": "passed"}
    ref["web_ipv6_ws_address"] = {"status": "passed"}
    ref["web_ipv6_ws_reach"] = {"status": "passed"}
    ref["web_ipv6_ws_similar"] = {"status": "passed"}

    calculate_ipv6_views_web(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_web_ipv6"]["status"] == "ready"
    assert added["v6_web_ipv6_ready"]["status"] is True
    assert added["v6_web_ipv6_proof"]["status"] is False
    assert added["v6_web_ipv6_incompatible"]["status"] is False


def test_v6_web_v6_proof():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["web_ipv6_ns_address"] = {"status": "failed"}
    ref["web_ipv6_ns_reach"] = {"status": "failed"}
    ref["web_ipv6_ws_address"] = {"status": "passed"}
    ref["web_ipv6_ws_reach"] = {"status": "passed"}
    ref["web_ipv6_ws_similar"] = {"status": "passed"}

    calculate_ipv6_views_web(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_web_ipv6"]["status"] == "proof"
    assert added["v6_web_ipv6_ready"]["status"] is False
    assert added["v6_web_ipv6_proof"]["status"] is True
    assert added["v6_web_ipv6_incompatible"]["status"] is False


def test_v6_web_v6_incompatible():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["web_ipv6_ns_address"] = {"status": "failed"}
    ref["web_ipv6_ns_reach"] = {"status": "passed"}
    ref["web_ipv6_ws_address"] = {"status": "failed"}
    ref["web_ipv6_ws_reach"] = {"status": "passed"}
    ref["web_ipv6_ws_similar"] = {"status": "passed"}

    calculate_ipv6_views_web(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_web_ipv6"]["status"] == "incompatible"
    assert added["v6_web_ipv6_ready"]["status"] is False
    assert added["v6_web_ipv6_proof"]["status"] is False
    assert added["v6_web_ipv6_incompatible"]["status"] is True


def test_v6_mail_v6_ready():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["mail_ipv6_ns_address"] = {"status": "passed"}
    ref["mail_ipv6_ns_reach"] = {"status": "passed"}
    ref["mail_ipv6_mx_address"] = {"status": "passed"}
    ref["mail_ipv6_mx_reach"] = {"status": "passed"}

    calculate_ipv6_views_mail(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_mail_ipv6"]["status"] == "ready"
    assert added["v6_mail_ipv6_ready"]["status"] is True
    assert added["v6_mail_ipv6_proof"]["status"] is False
    assert added["v6_mail_ipv6_incompatible"]["status"] is False


def test_v6_mail_v6_proof():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["mail_ipv6_ns_address"] = {"status": "failed"}
    ref["mail_ipv6_ns_reach"] = {"status": "failed"}
    ref["mail_ipv6_mx_address"] = {"status": "passed"}
    ref["mail_ipv6_mx_reach"] = {"status": "passed"}

    calculate_ipv6_views_mail(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_mail_ipv6"]["status"] == "proof"
    assert added["v6_mail_ipv6_ready"]["status"] is False
    assert added["v6_mail_ipv6_proof"]["status"] is True
    assert added["v6_mail_ipv6_incompatible"]["status"] is False


def test_v6_mail_v6_incompatible():
    scan_data = {"results": {"tests": {}}}
    ref = scan_data["results"]["tests"]
    ref["mail_ipv6_ns_address"] = {"status": "failed"}
    ref["mail_ipv6_ns_reach"] = {"status": "passed"}
    ref["mail_ipv6_mx_address"] = {"status": "failed"}
    ref["mail_ipv6_mx_reach"] = {"status": "passed"}

    calculate_ipv6_views_mail(scan_data)

    added = scan_data["results"]["calculated_results"]
    assert added["v6_mail_ipv6"]["status"] == "incompatible"
    assert added["v6_mail_ipv6_ready"]["status"] is False
    assert added["v6_mail_ipv6_proof"]["status"] is False
    assert added["v6_mail_ipv6_incompatible"]["status"] is True
