from django.db import models

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
    rating = models.IntegerField()
    when = models.DateTimeField()
    calculation = models.TextField()  # calculations of the independent urls... and perhaps others?

    class Meta:
        managed = True
        get_latest_by = "when"

    def __str__(self):
        return '%s  - %s' % (self.rating, self.when,)


class UrlRating(models.Model):
    """
        Aggregrates the results of many scanners to determine a rating for a URL.

        For example: organization.nl has a the following results:
        - TLS: A = 0 points
        - Banners: C = 100 points
        - Headers: F = 1000 points
    """
    url = models.ForeignKey(Url, on_delete=models.PROTECT,)
    rating = models.IntegerField()
    when = models.DateTimeField()
    calculation = models.TextField()  # calculation of different scanners. There will be a loop
    # somewhere that just figures out the rating on different time periods per scanner.
    # This does not need to contain ALL aggegrated data, but it can as it's calculated.

    class Meta:
        managed = True

    def __str__(self):
        return '%s  - %s' % (self.rating, self.when,)
