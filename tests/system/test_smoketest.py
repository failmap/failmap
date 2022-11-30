"""Test that indicate something is seriously wrong with the application."""


def test_admin_frontpage(websecmap):
    """Admin frontpage should be available."""
    response, data = websecmap.get_admin("/")
    assert response.status == 200
    assert "MSPAIN" in data.decode("utf-8"), "Page did not render complete!"


def test_admin_login_page(websecmap):
    """Admin login should be available."""
    response, data = websecmap.get_admin("/admin/login/?next=/admin/")
    assert response.status == 200


def test_frontend(websecmap):
    """Frontend frontpage should be available."""
    response, data = websecmap.get_frontend("/")
    assert response.status == 200
    assert "MSPAIN" in data.decode("utf-8"), "Page did not render complete!"


def test_static_content(websecmap):
    """Static files should be returned."""
    response, data = websecmap.get_admin("/static/images/fail_logo.png")
    assert response.status == 200

    response, data = websecmap.get_frontend("/static/images/fail_logo.png")
    assert response.status == 200


def test_frontend_no_admin_url(websecmap):
    """Frontend frontpage should not serve admin urls."""
    response, data = websecmap.get_frontend("/admin/login/?next=/admin/")
    assert response.code == 404
