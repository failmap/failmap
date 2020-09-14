"""Basic tests to check nothing major is broken."""


def test_admin_view(admin_client):
    """Admin login page should at least return 200."""

    response = admin_client.get("/admin/")
    assert response.status_code == 200
