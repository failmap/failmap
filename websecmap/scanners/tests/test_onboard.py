from websecmap.scanners.scanner.onboard import backward, forward

TEST_STAGES = [
    {"name": "", "active": False},
    {"name": "endpoint_discovery", "active": True},
    {"name": "endpoint_finished", "active": False},
    {"name": "scans_running", "active": True},
    {"name": "scans_finished", "active": False},
    {"name": "crawling", "active": True},
    {"name": "onboarded", "active": False},
]


def test_backward():
    assert backward("endpoint_discovery", TEST_STAGES) == {"name": "", "active": False}

    # can't go backward
    assert backward("", TEST_STAGES) == {"name": "", "active": False}

    # can go backward
    assert backward("onboarded", TEST_STAGES) == {"name": "crawling", "active": True}

    # resets onboarding? or valuerror?
    assert backward("non-existing", TEST_STAGES) == {"name": "", "active": False}


def test_forward():
    # going forward as usual
    assert forward("endpoint_discovery", TEST_STAGES) == {"name": "endpoint_finished", "active": False}

    # going forward as usual
    assert forward("", TEST_STAGES) == {"name": "endpoint_discovery", "active": True}

    # cannot go forward
    assert forward("onboarded", TEST_STAGES) == {"name": "onboarded", "active": False}

    # will finish onboarding
    assert forward("non-existing", TEST_STAGES) == {"name": "onboarded", "active": False}
