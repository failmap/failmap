from tldextract import tldextract

from websecmap.organizations.models import Organization, Url


def test_add_subdomain(db, patch_resolve):
    u = Url()
    u.url = "example.nl"
    u.save()

    u.add_subdomain("my", origin="Just a friendly test")
    u.save()

    assert Url.objects.all().count() == 2

    new_url = Url.objects.all().get(url="my.example.nl")
    assert new_url.origin == "Just a friendly test"


def test_add_sub_sub_domain(db, patch_resolve):
    """
    Handle two new situations. These should also be handled with adding regular urls, as subdomain checks have
    to be performed there as well.

    1:
    Subdomains have different owners than their parent domains. New domains of sub-sub domains must be placed
    at the correct organization.

    2:
    Some subdomains are configured not to allow new subdomains. This is set with the flag "do not add subdomains".
    In that case log a warning or give an negative feedback to the user. You CAN add it as a dead subdomain
    with the notice that the subdomain was not allowed to be added, but that would make for a more complex situation.

    Consider the following scenario:
    a_domain.nl -> owned by A
    b_domain.a_domain.nl -> owned by B
    c_domain.a_domain.nl -> owned by A, has the "do not add subdomains" flag set to True.
    d_domain.b_domain.a_domain.nl -> owned by A, new domains should not be added to B in this case.

    Example 1:
    adding a new sub-sub domain to a domain "some.b_domain.domain.nl" must be owned by B and not A.

    Example 2:
    adding a new sub-sub domain to a domain "some.c_domain.domain.nl" is not possible and will be rejected.

    # Realistic examples:
    business.gov.nl is owned by KVK
    finance.gov.nl is owned by the Ministry of Finance
    fiod.belastingdienst.gov.nl is owned by the Fiscale Inlichten en Opsporingsdienst of the tax authority

    # Realistic of not adding sub-subdomains:
    student.university.nl is seen as a hosting provider, and domains below that are not owned nor managed by
    the organization.
    """

    # setup the example scenario:
    org_a = Organization.objects.create(name="A")
    org_b = Organization.objects.create(name="B")

    a_domain = org_a.add_url("a_domain.nl", "test")
    org_a.add_url("a_domain.nl")
    b_domain = Url.objects.create(url="b_domain.a_domain.nl")
    b_domain.organization.add(org_b)
    c_domain = Url.objects.create(url="c_domain.a_domain.nl", do_not_find_subdomains=True)
    c_domain.organization.add(org_a)
    d_domain = Url.objects.create(url="d_domain.b_domain.a_domain.nl")
    d_domain.organization.add(org_a)

    # regular case, a subdomain will be owned by A:
    # should_be_owned_by_a.a_domain.nl
    should_be_owned_by_a = a_domain.add_subdomain(subdomain="should_be_owned_by_a")
    assert should_be_owned_by_a.organization.all().first() == org_a

    # now it's fun, let's add a subdomain under b_domain while we are at a_domain :)
    should_be_owned_by_b = a_domain.add_subdomain(subdomain="should_be_owned_by_b.b_domain")
    assert should_be_owned_by_b.organization.all().first() == org_b

    # c_domain has the do not find subdomains flag, so this will not be added.
    should_not_be_added = a_domain.add_subdomain(subdomain="should_not_be_added.c_domain")
    assert should_not_be_added is None

    # let's add something under d-domain which is owned by organization a again. The above domain is owned by b, and
    # the 2nd level is owned by a.
    should_be_owned_by_a = a_domain.add_subdomain(subdomain="should_be_owned_by_a.d_domain.b_domain")
    assert should_be_owned_by_a.organization.all().first() == org_a

    # assert that regex filters work that will prevent adding of certain subdomains that we don't need:
    a_domain.subdomain_iregexes_to_ignore = ["vps[0-9]{1,6}", "vm[0-9]{1,6}", "host[0-9]{1,6}"]
    a_domain.save()
    assert a_domain.add_subdomain(subdomain="vps123") is None
    assert a_domain.add_subdomain(subdomain="vm1") is None
    assert a_domain.add_subdomain(subdomain="host101010") is None
    # intentionally a too long thing that would fall outside of the patterns.
    assert a_domain.add_subdomain(subdomain="host10101010").computed_subdomain == "host10101010"

    assert a_domain.subdomain_should_be_ignored("host101010") is True
    assert a_domain.subdomain_should_be_ignored("host10101010") is False
    assert a_domain.subdomain_should_be_ignored("host") is False
    assert a_domain.subdomain_should_be_ignored("10host") is False


def test_find_domain_owner(db):
    # garbage yields to nothing
    owner = Url.find_domain_owner("aasdasadnl")
    assert owner == []

    # should test a.b.c.d.e.f.nl, b.c.d.e.f.nl, c.d.e.f.nl till it finds nothing
    owner = Url.find_domain_owner("a.b.c.d.e.f.nl")
    assert owner == []

    # let's create some domains and owners
    # setup the example scenario:
    org_a = Organization.objects.create(name="A")
    org_b = Organization.objects.create(name="B")

    org_a.add_url("a_domain.nl")
    b_domain = Url.objects.create(url="b_domain.a_domain.nl")
    b_domain.organization.add(org_b)
    c_domain = Url.objects.create(url="c_domain.a_domain.nl")
    c_domain.organization.add(org_a)
    d_domain = Url.objects.create(url="d_domain.b_domain.a_domain.nl")
    d_domain.organization.add(org_a)

    assert Url.find_domain_owner("a_domain.nl") == [org_a]
    assert Url.find_domain_owner("b_domain.a_domain.nl") == [org_b]
    assert Url.find_domain_owner("c_domain.a_domain.nl") == [org_a]
    assert Url.find_domain_owner("d_domain.b_domain.a_domain.nl") == [org_a]

    # try something with two organizations
    d_domain.organization.add(org_b)
    assert Url.find_domain_owner("d_domain.b_domain.a_domain.nl") == [org_a, org_b]

    # no owner:
    Url.objects.create(url="e_domain.a_domain.nl")
    assert Url.find_domain_owner("e_domain.a_domain.nl") == []


def test_subdomain_adding_is_allowed(db):
    # everything is allowed
    org_a = Organization.objects.create(name="A")
    a_domain = org_a.add_url("a_domain.nl")
    Url.objects.create(url="b_domain.a_domain.nl")
    Url.objects.create(url="d_domain.b_domain.a_domain.nl")

    assert Url.subdomain_adding_is_allowed("a_domain.nl") is True
    assert Url.subdomain_adding_is_allowed("b_domain.a_domain.nl") is True
    assert Url.subdomain_adding_is_allowed("d_domain.b_domain.a_domain.nl") is True

    # and now nothing is allowed.
    a_domain.do_not_find_subdomains = True
    a_domain.save()

    assert Url.subdomain_adding_is_allowed("a_domain.nl") is False
    assert Url.subdomain_adding_is_allowed("b_domain.a_domain.nl") is False
    assert Url.subdomain_adding_is_allowed("d_domain.b_domain.a_domain.nl") is False


def test_is_valid_url():
    # This is not going to work as there is a dot in front of the domain.
    # No crashes because of IDNA.
    assert Url.is_valid_url(".espacenet.com") is False
    assert Url.is_valid_url("") is False
    assert Url.is_valid_url("-works.nl") is False

    # Works for domains that are actual domains:
    assert Url.is_valid_url("google.com") is True
    assert Url.is_valid_url("аренда.орг") is True
    assert Url.is_valid_url("something.something.something.орг") is True

    # _jabber._tcp.gmail.com, subdomains can have an underscore, but not hostnames:
    assert Url.is_valid_url("_tcp._mumc.nl") is False
    assert Url.is_valid_url("_tcp.mumc.nl") is True
    assert Url.is_valid_url("_test._tcp.mumc.nl") is True


def test_tldextract():
    # just to know that tldextract is sane:
    extract = tldextract.extract("https://subdomein.basisbeveiliging.co.uk:443/some_page#anchor-13")
    assert extract.fqdn == f"{extract.subdomain}.{extract.domain}.{extract.suffix}"

    extract = tldextract.extract("https://basisbeveiliging.co.uk:443/some_page#anchor-13")
    assert extract.fqdn == f"{extract.domain}.{extract.suffix}"
