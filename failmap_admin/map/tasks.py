import logging

from failmap_admin.celery import app
from failmap_admin.map.determineratings import (default_ratings, rate_organizations_efficient,
                                                rerate_existing_urls)
from failmap_admin.map.models import OrganizationRating

log = logging.getLogger(__name__)


@app.task
def rebuild_ratings():
    """Remove all organization and url ratings, then rebuild them from scratch."""

    log.info('Rebuilding ratings.')

    rerate_existing_urls()

    OrganizationRating.objects.all().delete()
    default_ratings()
    rate_organizations_efficient(create_history=True)

    log.info('Finished rebuilding ratings.')
