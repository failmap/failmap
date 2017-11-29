from django.db import models
from jsonfield import JSONField

from failmap_admin.organizations.models import Organization, Url

# Create your models here.


class OrganizationRating(models.Model):
    """
    This is basically an aggregation of UrlRating

    Contains aggregated ratings over time. Why?

    - Reduces complexity to get ratings
        You don't need to know about dead(urls, endpoints), scanner-results.
        For convenience purposes a calculation field also contains some hints why the rating is
        the way it is.

    -   It increases speed
        Instead of continuously calculating the score, it is done on a more regular interval: for
        example once every 10 minutes and only for the last 10 minutes.

    A time dimension is kept, since it's important to see what the rating was over time. This is
    now very simple to get (you don't need a complex join which is hard in django).

    The client software does a drill down on domains and shows why things are the way they are.
    Also this should not know too much about different scanners. In OO fashion, it should ask a
    scanner to explain why something is the way it is (over time).
    """
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT,)
    rating = models.IntegerField(
        help_text="Amount of points scored by the organization based on a sum of all URL ratings at"
                  " this moment. Rating -1 is used as a default first rating, which are displayed "
                  "in gray on the map. All next ratings are between 0 (perfect) and 2147483647."
    )
    high = models.IntegerField(help_text="The number of high risk vulnerabilities and failures.", default=0)
    medium = models.IntegerField(help_text="The number of medium risk vulnerabilities and failures.", default=0)
    low = models.IntegerField(help_text="The number of low risk vulnerabilities and failures.", default=0)

    when = models.DateTimeField(db_index=True)
    calculation = JSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment, for all urls "
                  "of this organization. This can be a lot."
    )  # calculations of the independent urls... and perhaps others?

    class Meta:
        managed = True
        get_latest_by = "when"

    def __str__(self):
        return '%s  - %s' % (self.rating, self.when,)


class UrlRating(models.Model):
    """
        Aggregrates the results of many scanners to determine a rating for a URL.
    """
    url = models.ForeignKey(Url)
    rating = models.IntegerField(
        help_text="Amount of points scored after rating the URL. Ratings are usually positive, yet "
                  "this is not a positive integerfield because we might use -1 as an 'unknown' "
                  "default value for when there are no ratings at all. Ratings can go from 0 "
                  "up to 2147483647."
    )

    high = models.IntegerField(help_text="The number of high risk vulnerabilities and failures.", default=0)
    medium = models.IntegerField(help_text="The number of medium risk vulnerabilities and failures.", default=0)
    low = models.IntegerField(help_text="The number of low risk vulnerabilities and failures.", default=0)

    when = models.DateTimeField(db_index=True)
    calculation = JSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment. The rating can "
                  "be spread out over multiple endpoints, which might look a bit confusing. Yet it "
                  "is perfectly possible as some urls change their IP every five minutes and "
                  "scans are spread out over days."
    )

    class Meta:
        managed = True

    def __str__(self):
        return '%s  - %s' % (self.rating, self.when,)
