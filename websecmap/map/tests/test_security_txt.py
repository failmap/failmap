from django.test import Client
from constance.test import override_config
import pytest
from django.urls import reverse


@pytest.mark.parametrize("url", ["security_txt", "well_known_security_txt"])
@override_config(SECURITY_TXT_CONTENT="swag")
@override_config(SECURITY_TXT_IS_REDIRECTED=False)
@override_config(SECURITY_TXT_REDIRECT_URL="https://example.com/security.txt")
def test_security_txt(db, url):
    client = Client()
    response = client.get(reverse(url))
    assert response.status_code == 200
    assert "swag" in response.content.decode("utf-8")


@pytest.mark.parametrize("url", ["security_txt", "well_known_security_txt"])
@override_config(SECURITY_TXT_CONTENT="swag")
@override_config(SECURITY_TXT_IS_REDIRECTED=True)
@override_config(SECURITY_TXT_REDIRECT_URL="https://example.com/security.txt")
def test_security_txt_redirect(db, url):
    client = Client()
    response = client.get(reverse(url))
    assert response.status_code == 302
    assert response.url == "https://example.com/security.txt"
