from datetime import datetime

from websecmap.celery import app
from websecmap.map.models import OrganizationOnLayerOverTime, MapFlow
from websecmap.organizations.models import Organization
from websecmap.scanners.time_storage import abstract_time_storage


@app.task(queue="storage", ignore_result=True)
def update_organizations_on_map_over_time():
    # make a snapshot of all current organizations on all layers right now. This can be performed every day. You can
    # run it every second, but that is just waste. Once a day is more than enough.

    for organization in Organization.objects.all():
        data = {
            "organization": organization,
            # you can't set multiple layers at once, so make this a shallow representation of list id's.
            # so you can still change the layer names etc. But this isn't autoremoved.
            # Not going to support time storage with many to many for this outlier.
            "layers": [layer.id for layer in organization.layers.all().order_by("id")],
        }
        abstract_time_storage(
            OrganizationOnLayerOverTime,
            fields_to_retrieve_latest={"organization": organization},
            fields_that_signify_change=["layers"],
            data_for_new_record=data,
        )


@app.task(queue="storage", ignore_result=True)
def tick_map_flow():
    # a tick happens every day?
    for flow in MapFlow.objects.all().filter(is_enabled=True):
        if flow.enable_on_specific_date:
            if flow.on_specific_date <= datetime.now().date():
                # move all from from_layer to to_layer
                organization_on_layer = Organization.objects.all().filter(layers__in=[flow.from_layer])
                for organization in organization_on_layer:
                    organization.layers.add(flow.to_layer)

                    if flow.also_remove_from_original_layer:
                        organization.layers.remove(flow.from_layer)

        if flow.enable_after_n_days:
            # it's impossible to filter on layers, the jsonfield allows stuff but not this exact
            organization_on_layer = OrganizationOnLayerOverTime.objects.all().filter(
                is_the_latest=True,
            )
            for org_on_layer in organization_on_layer:
                # TODO: this is a stupid and ugly fix but it is because layers is a jsonfield and
                # the storage/stacking pattern is used here which would ideally be replaced with
                # something else which allows for proper ORM queries without bugs
                # Maybe using postgresql can provide a solution here as it supports 'DISTICT ON'
                # which can be a replacement for the 'is_the_latest'
                if flow.from_layer.id not in org_on_layer.layers:
                    # skip organizations which have nothing to do with the mapflow
                    continue

                # already on layer, don't act. If it should have been removed, it would have.
                if flow.to_layer.id in org_on_layer.layers:
                    continue

                # it's not time yet
                if org_on_layer.days_on_map < flow.after_n_days:
                    continue

                # not a relevant layer
                # if flow.from_layer in org_on_layer.layers:
                #     continue

                # add the new layer to the organization.
                org_on_layer.organization.layers.add(flow.to_layer)

                if flow.also_remove_from_original_layer:
                    org_on_layer.organization.layers.remove(flow.from_layer)
