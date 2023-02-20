from websecmap.scanners.support import kwargs_to_params


def test_kwargs_to_params():
    # Simulate arguments for Nuclei
    kwargs = {
        "args": [
            {"name": "silent", "type": "no-value"},
            {"name": "disable-update-check", "type": "no-value"},
            {"name": "rate-limit", "type": "single-argument", "value": 25},
            {"name": "config-directory", "type": "single-argument", "value": "/tmp"},
            {"name": "type", "type": "list-to-duplicate-arguments", "value": ["http"]},
            {
                "name": "exclude-severity",
                "type": "list-to-duplicate-arguments",
                "value": ["high", "critical", "medium"],
            },
            {"name": "exclude-id", "type": "list-to-single-csv-argument", "value": ["robots-txt", "security-txt"]},
        ]
    }

    kwargs = kwargs_to_params(kwargs, prefix="--")
    # Order is relevant!
    assert kwargs == [
        "--silent",
        "--disable-update-check",
        "--rate-limit",
        25,
        "--config-directory",
        "/tmp",
        "--type",
        "http",
        "--exclude-severity",
        "high",
        "--exclude-severity",
        "critical",
        "--exclude-severity",
        "medium",
        "--exclude-id",
        "robots-txt,security-txt",
    ]

    # different prefix
    kwargs = {"args": [{"name": "json", "type": "no-value"}]}
    kwargs = kwargs_to_params(kwargs, prefix="-")
    assert kwargs == ["-json"]

    # No crashes when there are no arguments
    assert kwargs_to_params({}, prefix="--") == []

    # Do not use standard kwargs such as amount for plannedscan.
    assert (
        kwargs_to_params({"NEVER_USE": {"type": "arguments-to-ignore", "value": ["amount"]}, "amount": 25}, prefix="--")
        == []
    )

    # simulate arguements for nmap:
    # -sV --host-timeout=5m -T3 --script=banner
    kwargs = kwargs_to_params(
        {
            "SPECIAL_DIRECT": "-sV --host-timeout=5m -T3 --script=banner",
        },
        prefix="--",
    )
    assert kwargs == ["-sV --host-timeout=5m -T3 --script=banner"]

    # mix them:
    kwargs = kwargs_to_params(
        {
            "args": [
                {"name": "json", "type": "no-value"},
            ],
            "SPECIAL_DIRECT": "-sV --host-timeout=5m -T3 --script=banner",
        },
        prefix="--",
    )
    assert kwargs == ["-sV --host-timeout=5m -T3 --script=banner", "--json"]
