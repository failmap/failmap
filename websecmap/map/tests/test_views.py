from websecmap.map.views import config_content


def test_config(db):
    conf = config_content()
    assert conf["project"]["country"] == "NL"
    assert conf["debug"] is False
    assert conf["show"]["issues"]["http_security_header_x_xss_protection"] is True
