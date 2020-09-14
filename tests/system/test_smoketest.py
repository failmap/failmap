"""Test that indicate something is seriously wrong with the application."""


def test_admin_frontpage(websecmap):
    """Admin frontpage should be available."""
    response, data = websecmap.get_admin("/")
    assert response.status == 200
    assert "MSPAIN" in data, "Page did not render complete!"


def test_admin_login_page(websecmap):
    """Admin login should be available."""
    assert websecmap.get_admin("/admin/login/?next=/admin/")[0].status == 200


def test_frontend(websecmap):
    """Frontend frontpage should be available."""
    response, data = websecmap.get_frontend("/")
    assert response.status == 200
    assert "MSPAIN" in data, "Page did not render complete!"


def test_frontend_no_admin_url(websecmap):
    """Frontend frontpage should not serve admin urls."""
    assert websecmap.get_frontend("/admin/login/?next=/admin/").code == 404
