from django.contrib.admin import AdminSite
from django.contrib.auth.models import User


from websecmap.organizations.admin import UrlAdmin, MyUrlAdminForm
from websecmap.organizations.models import Url


class MockRequest(object):
    def __init__(self, user=None):
        self.user = user


def test_url_admin(db):
    # todo: does this test anything at all?
    super_user = User.objects.create_superuser(username="super", email="super@email.org", password="pass")
    my_model_admin = UrlAdmin(model=Url, admin_site=AdminSite())
    my_model_admin.save_model(
        obj=Url(**{"url": "test.example.com"}), request=MockRequest(user=super_user), form=MyUrlAdminForm(), change=None
    )

    assert Url.objects.all().count() == 1
    added = Url.objects.first()
    assert added.computed_subdomain == "test"
    assert added.computed_domain == "example"
    assert added.computed_suffix == "com"
    assert added.url == "test.example.com"


def test_adminform(db):

    form = MyUrlAdminForm()
    form.data = {"url": "https://www.example.com:1337/asd#12"}
    cleaned = form.clean_url()
    assert cleaned == "www.example.com"
