from datetime import date

from freezegun import freeze_time

from websecmap.map.logic.MapFlow import update_organizations_on_map_over_time, tick_map_flow
from websecmap.map.models import OrganizationOnLayerOverTime, MapFlow
from websecmap.organizations.models import OrganizationType, Organization


def test_update_organizations_over_time(db):
    # this should add all organizations in the database. From this we can see how many days they are on the map and
    # that can be used to move organizations to another map via MapFlow.

    # no crashes, nothing is in the database
    update_organizations_on_map_over_time()

    # add an organization on a layer, this should be visible
    with freeze_time("2024-01-01"):
        organization = Organization.objects.create(name="test", country="NL")
        layer1 = OrganizationType.objects.create(name="layer1")
        organization.layers.add(layer1)

        # this should only create one record and it will be updated. This timestorage is tested elsewhere.
        update_organizations_on_map_over_time()
        update_organizations_on_map_over_time()
        update_organizations_on_map_over_time()
        update_organizations_on_map_over_time()
        update_organizations_on_map_over_time()

        assert OrganizationOnLayerOverTime.objects.all().count() == 1

    # let's add another layer to the organization and see that another record is created.
    with freeze_time("2024-02-01"):
        layer2 = OrganizationType.objects.create(name="layer2")
        organization.layers.add(layer2)

        update_organizations_on_map_over_time()
        update_organizations_on_map_over_time()

        assert OrganizationOnLayerOverTime.objects.all().count() == 2
        assert OrganizationOnLayerOverTime.objects.all().filter(is_the_latest=True).count() == 1
        assert OrganizationOnLayerOverTime.objects.all().filter(is_the_latest=False).count() == 1

    # now remove the first layer and see that a third record is created signifiying a change
    with freeze_time("2024-03-01"):
        organization.layers.remove(layer1)

        update_organizations_on_map_over_time()

        assert OrganizationOnLayerOverTime.objects.all().count() == 3
        assert OrganizationOnLayerOverTime.objects.all().filter(is_the_latest=True).count() == 1
        assert OrganizationOnLayerOverTime.objects.all().filter(is_the_latest=False).count() == 2


def test_tick_map_flow_on_specific_date(db):
    layer1 = OrganizationType.objects.create(name="layer1")
    layer2 = OrganizationType.objects.create(name="layer2")

    mf = MapFlow.objects.create(
        from_layer=layer1,
        to_layer=layer2,
        is_enabled=True,
        enable_on_specific_date=True,
        on_specific_date=date(2024, 2, 1),
    )

    organization = Organization.objects.create(name="test", country="NL")
    organization.layers.add(layer1)

    # Create a map flow that moves an organization on a specific date. See that the organization is moved.
    # in the first scenario keep the organization on the same layer.
    with freeze_time("2024-01-01"):
        # too early, so the organization is not moved.
        # calling it multiple times will do no harm...
        tick_map_flow()
        tick_map_flow()
        tick_map_flow()

        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer1]

    with freeze_time("2024-02-01"):
        # the organization will be moved. The original layer stays
        tick_map_flow()
        tick_map_flow()
        tick_map_flow()

        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer1, layer2]

    # prepare for the second scenario.
    Organization.objects.get(id=organization.id).layers.remove(layer2)
    mf.also_remove_from_original_layer = True
    mf.save()

    # now the organization is moved to the second layer and removed from the original one.
    with freeze_time("2024-02-01"):
        # the organization will be moved. The original layer stays
        tick_map_flow()
        tick_map_flow()
        tick_map_flow()
        tick_map_flow()

        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer2]


def test_tick_map_flow_enable_after_n_days(db):
    # this tests if an organization is moved to a new map after a set amount of days. This makes it easier to comply
    # with the two month preview period for new organizations before their data goes public. With the specific scenario
    # that organizations are added in batches over time. This also publishes those batches without requiring any further
    # manual work / reminders etc. So the organization can be mailed and then put on a preview map. From there it will
    # become public automatically after a number of days of being on the preview map. The standard duration would be 61
    # days.

    layer1 = OrganizationType.objects.create(name="layer1")
    layer2 = OrganizationType.objects.create(name="layer2")

    # in this case a move happens after 14 days.
    mf = MapFlow.objects.create(
        from_layer=layer1,
        to_layer=layer2,
        is_enabled=True,
        enable_after_n_days=True,
        after_n_days=14,
    )

    organization = Organization.objects.create(name="test", country="NL")
    organization.layers.add(layer1)

    with freeze_time("2024-02-01"):
        # organization is now 0 days on layer 1
        update_organizations_on_map_over_time()
        assert OrganizationOnLayerOverTime.objects.all().first().days_on_map == 0

        # it will not be moved to layer 2
        tick_map_flow()
        tick_map_flow()
        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer1]

    with freeze_time("2024-02-11"):
        # organization is now 10 days on layer 1
        update_organizations_on_map_over_time()
        assert OrganizationOnLayerOverTime.objects.all().first().days_on_map == 10

        # it will not be moved to layer 2
        tick_map_flow()
        tick_map_flow()
        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer1]

    # now it will be added to the other layer as it's on layer 1
    with freeze_time("2024-02-15"):
        update_organizations_on_map_over_time()
        assert OrganizationOnLayerOverTime.objects.all().first().days_on_map == 14

        tick_map_flow()
        tick_map_flow()
        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer1, layer2]

    # prepare for the second scenario.
    Organization.objects.get(id=organization.id).layers.remove(layer2)
    mf.also_remove_from_original_layer = True
    mf.save()

    with freeze_time("2024-02-16"):
        update_organizations_on_map_over_time()
        assert OrganizationOnLayerOverTime.objects.all().first().days_on_map == 15

        tick_map_flow()
        tick_map_flow()
        assert list(Organization.objects.get(id=organization.id).layers.all()) == [layer2]
