from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from jsonfield import JSONField

from websecmap.organizations.models import OrganizationType


class AdministrativeRegion(models.Model):
    """
    Helps with downloading / importing openstreetmap regions. Makes it possible for end users to add regions without
    altering code and then import / update those regions.

    Caveats:
    - The more detail you need, the more data is downloaded and processed. This can go into extremes when working with
    cities. Our advice is to only download larger regions or have a massive setup to convert the data. Your memory might
    not be adequate in those cases.
    - Importing regions can be excruciatingly slow, even up to hours and days, depending on the size.
    - Importing regions will possibly block the worker that is importing the region for said time.
    """

    country = CountryField(db_index=True)

    organization_type = models.ForeignKey(
        OrganizationType,
        on_delete=models.CASCADE,
        help_text="The organization type desired to import. Not all organization types might be present in this list"
                  " by default. Create new ones accordingly."
    )

    admin_level = models.IntegerField(
        help_text=mark_safe(
            "The administrative level as documented on the OSM Wiki. Note that each country uses a different way "
            "to organize the same thing. Some use municipalities on level 8, other on level 4 etc. Really do "
            "check the wiki before adding any missing organization. "
            "<a href='https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative' target='_blank'>"
            "Visit the OSM wiki</a>."),
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(11)]
    )

    resampling_resolution = models.FloatField(
        help_text='This is used in the algorithm that reduces datapoints in map shapes: this saves a lot of data. '
                  'value here should make the map look decent when the entire country is visible but may be somewhat '
                  'blocky when zooming in. The smaller the number, the more detail.',
        default='0.001'
    )

    imported = models.BooleanField(
        help_text="When imported, this is checked. Helps with importing a larger number of regions manually.",
        default=False
    )

    import_start_date = models.DateTimeField(
        blank=True,
        null=True
    )

    import_message = models.CharField(
        max_length=255,
        default="",
        blank=True,
        null=True,
        help_text="Information returned from the import features."
    )

    class Meta:
        verbose_name = _('administrative_region')
        verbose_name_plural = _('administrative_regions')

    def __str__(self):
        return '%s/%s' % (self.country, self.organization_type,)


class Configuration(models.Model):

    country = CountryField(db_index=True,
                           help_text="Part of the combination shown on the map.")

    organization_type = models.ForeignKey(
        OrganizationType,
        on_delete=models.CASCADE,
        verbose_name="Layer",
        help_text="Part of the combination shown on the map.")

    is_displayed = models.BooleanField(
        help_text="Whether this combination is shown on the map.",
        default=False
    )

    is_reported = models.BooleanField(
        help_text="Whether this combination is shown on the map.",
        default=False
    )

    is_the_default_option = models.BooleanField(
        help_text="Determines if this is the default view. Only one can be selected to be displayed first. If there "
                  "are multiple, the first one is used. This can lead to unexpected results.",
        default=False
    )

    display_order = models.PositiveIntegerField(
        _('order'),
        default=0,
        blank=False,
        null=False,
        help_text="Setting this to 0 will automatically set the country at a guessed position. For example: near the"
                  "same country or at the end of the list."
    )

    is_scanned = models.BooleanField(
        help_text="Whether this combination will be scanned by the scanners.",
        default=False
    )

    class Meta(object):
        verbose_name = _('configuration')
        verbose_name_plural = _('configurations')
        ordering = ('display_order', )


class MapDataCache(models.Model):

    country = CountryField(db_index=True,
                           help_text="Part of the combination shown on the map.")

    organization_type = models.ForeignKey(
        OrganizationType,
        on_delete=models.CASCADE,
        help_text="Part of the combination shown on the map.")

    when = models.DateField()

    filters = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        db_index=True,
        help_text="Any set of desired scan_types"
    )

    dataset = JSONField()

    cached_on = models.DateField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return 'Map Cache %s %s %s' % (self.country, self.organization_type, self.when)


# It took too long to calculate these stats, resulting in non showing graphs. Therefore we're now storing
# them in this model.
class VulnerabilityStatistic(models.Model):

    country = CountryField(db_index=True,
                           help_text="Part of the combination shown on the map.")

    organization_type = models.ForeignKey(
        OrganizationType,
        on_delete=models.CASCADE,
        help_text="Part of the combination shown on the map.")

    when = models.DateField()

    scan_type = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True
    )

    high = models.PositiveIntegerField(default=0, blank=False, null=False)
    medium = models.PositiveIntegerField(default=0, blank=False, null=False)
    low = models.PositiveIntegerField(default=0, blank=False, null=False)
    urls = models.PositiveIntegerField(default=0, blank=False, null=False,
                                       help_text="Makes only sense on the total number of vulnerabilities")
    endpoints = models.PositiveIntegerField(default=0, blank=False, null=False,
                                            help_text="Makes only sense on the total number of vulnerabilities")

    ok = models.PositiveIntegerField(default=0, blank=False, null=False,
                                     help_text="Determines on the scan type what is stored here.")
    ok_urls = models.PositiveIntegerField(default=0, blank=False, null=False)
    ok_endpoints = models.PositiveIntegerField(default=0, blank=False, null=False)

    class Meta:
        managed = True
