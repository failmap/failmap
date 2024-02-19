from datetime import datetime

from websecmap.celery import app
from websecmap.map.models import OrganizationOnLayerOverTime, MapFlow
from websecmap.organizations.models import Organization
from websecmap.scanners.time_storage import abstract_time_storage


@app.task(queue="storage", ignore_result=True)
def update_organizations_over_time():
    # make a snapshot of all current organizations on all layers right now.

    data = {
        "organization": "",
        "layers": "",
    }
    abstract_time_storage(
        OrganizationOnLayerOverTime,
        fields_to_retrieve_latest={"organization": ""},
        fields_that_signify_change=["layers"],
        data_for_new_record=data,
    )


@app.task(queue="storage", ignore_result=True)
def tick_map_flow():
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
            organization_on_layer = OrganizationOnLayerOverTime.objects.all().filter(
                layers__in=[flow.from_layer],
                is_the_latest=True,
            )
            ...
    ...
