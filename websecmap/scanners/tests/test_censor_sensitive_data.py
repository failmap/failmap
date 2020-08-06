"""Integration tests of scanner commands."""

from websecmap.app.models import censor_sensitive_data


def test_censor_sensitive_data():

    # single qouted secret, will be single qouted
    sensitive_data = "test, password='secret', other text"
    censored = censor_sensitive_data(sensitive_data)
    assert "secret" not in censored
    assert "'" in censored

    # double qouted secret, will be double qouted
    sensitive_data = 'test, password="secret", other text'
    censored = censor_sensitive_data(sensitive_data)
    assert '"' in censored

    # secret can be part of a variable name:
    sensitive_data = "test, some_password_string='secret', other text"
    censored = censor_sensitive_data(sensitive_data)
    assert "secret" not in censored

    # secrets are also filtered out over multiple lines:
    sensitive_data = """test

password='secret'
test
"""
    censored = censor_sensitive_data(sensitive_data)
    assert "secret" not in censored

    # nested content is also removed
    sensitive_data = "test, password='token=\"sessionid\"', other text"
    censored = censor_sensitive_data(sensitive_data)
    assert "token" not in censored
