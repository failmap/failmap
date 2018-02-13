"""Test that indicate something is seriously wrong with the application."""


def test_admin_frontpage(failmap):
    """Admin frontpage should be available."""
    response, data = failmap.get_admin('/')
    assert response.status == 200
    assert 'MSPAIN' in data, 'Page did not render complete!'


def test_admin_login_page(failmap):
    """Admin login should be available."""
    assert failmap.get_admin('/admin/login/?next=/admin/')[0].status == 200


def test_frontend(failmap):
    """Frontend frontpage should be available."""
    response, data = failmap.get_frontend('/')
    assert response.status == 200
    assert 'MSPAIN' in data, 'Page did not render complete!'
