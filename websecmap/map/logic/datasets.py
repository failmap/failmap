import pyexcel as p
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url


def create_filename(set_name, country: str = "NL", organization_type="municipality"):
    country = get_country(country)
    organization_type_name = OrganizationType.objects.filter(name=organization_type).values("name").first()

    if not organization_type_name:
        organization_type_name = "municipality"
    else:
        organization_type_name = organization_type_name.get("name")

    filename = "%s_%s_%s_%s" % (country, organization_type_name, set_name, timezone.datetime.now().date())
    return filename


def generic_export(queryset, column_names):
    """
    This dataset can be imported in another instance blindly using the admin interface.

    The re-import feature has been dropped, as using django_import_export required extra models that where very
    specific. Using a factory for a model, and then set options to meta didn't work. Also the number of formats
    was too limited. Therefore we've switched to pyexcel as it supports tons of formats.

    Many pexcel formats are supported. There are a LOT.

    :return:
    """

    # None values will cause an invalid two dimensional array. So change all the None values to "":
    # Yes, it's possible to write this as a one liner, which makes the logic unclear and harder to maintain.
    dataset = []
    for row in queryset:
        dataset.append([value if value is not None else "" for value in row])

    data = [column_names] + list(dataset)

    book = p.get_book(bookdict={"data": data})
    return book


def export_urls_only(country: str = "NL", organization_type="municipality"):
    # how to reuse the column definition as both headers
    columns = ["id", "url", "not_resolvable", "is_dead", "computed_subdomain", "computed_domain", "computed_suffix"]
    queryset = (
        Url.objects.all()
        .filter(
            is_dead=False,
            not_resolvable=False,
            organization__is_dead=False,
            organization__country=get_country(country),
            organization__type=get_organization_type(organization_type),
        )
        .values_list(
            "id", "url", "not_resolvable", "is_dead", "computed_subdomain", "computed_domain", "computed_suffix"
        )
    )
    return generic_export(queryset, columns)


def export_organizations(country: str = "NL", organization_type="municipality"):
    columns = ["id", "name", "type", "wikidata", "wikipedia", "twitter_handle"]
    query = (
        Organization.objects.all()
        .filter(country=get_country(country), type=get_organization_type(organization_type), is_dead=False)
        .values_list("id", "name", "type", "wikidata", "wikipedia", "twitter_handle")
    )
    # values doesn't work anymore to determine what columns are relevant for the export.
    # we need to set it on the factory.

    # This does not restrain the amount of fields, all fields are included.
    # the export documentation is pretty terrible (there is none) and the code is obscure. So we're not using this
    # Left here for references, if anyone decides that
    # from import_export.resources import modelresource_factory
    # is a wise choice to use. It's not / it hardly is.
    # exporter = modelresource_factory(query.model)
    # exporter.Meta.fields = ['id', 'name', 'type', 'wikidata', 'wikipedia', 'twitter_handle']
    # dataset = exporter().export(query)

    return generic_export(query, columns)


def export_organization_types():
    columns = ["id", "name"]
    query = OrganizationType.objects.all().values_list("id", "name")
    return generic_export(query, columns)


def export_coordinates(country: str = "NL", organization_type="municipality"):
    organizations = Organization.objects.all().filter(
        country=get_country(country), type=get_organization_type(organization_type)
    )

    columns = ["id", "organization", "geojsontype", "area"]
    query = (
        Coordinate.objects.all()
        .filter(organization__in=list(organizations), is_dead=False)
        .values_list("id", "organization", "geojsontype", "area")
    )

    return generic_export(query, columns)


def export_urls(country: str = "NL", organization_type="municipality"):
    organizations = Organization.objects.all().filter(
        country=get_country(country), type=get_organization_type(organization_type)
    )

    columns = ["id", "url", "organization"]

    query = (
        Url.objects.all()
        .filter(organization__in=list(organizations), is_dead=False, not_resolvable=False)
        .values_list("id", "url", "organization")
    )

    return generic_export(query, columns)
