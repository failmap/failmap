from datetime import datetime

import pytz
from django.contrib.auth.models import User
from django.db import models, transaction

from websecmap.organizations.models import Organization, Url
from websecmap.reporting.models import SeriesOfUrlsReportMixin
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan

"""
Ideas:

Map users to an account.
how can users add their own / new urls? Should they be able to? How does that propagate back into the system?
A user cannot see other accounts, only their own account.
new urls can be added to the organizations the account has access to. This has to be a subdomain in a series of
domains the account has access to.
Several users can be linked to one account for which they have a number of organizations with urls.
We want to support urls that are spread out over multiple organizations, such as a series of subdomains of the same
vendor.
The structure / hierarchy and other business structures must be able to change, without affecting the rest of the
production data. If we want a nested tree set tomorrow and some sort of other weird hierarchy next week, the rest
of the system remains unaffected. This is just a way to point to the existing data.
You are allowed to add subdomains to "topleveldomain.nl" etc. Those are checked for validity and added publicly.

In the future there might be subdomain datafeeds / ip datafeeds so service providers can manage everything they own.
"""


class Account(models.Model):
    # todo: created_on, is_dead etc.

    name = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text="Understandable name of the organization."
    )

    enable_logins = models.BooleanField(
        blank=True,
        null=True,
        default=False,
        help_text="Inactive accounts cannot be logged-in to."
    )

    credits = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=0,
        help_text='Credits limit the amount of scans an account can make. Otherwise they might scan-flood.'
    )

    # Since this is not in the same transaction as spend, it might be possible this is outdated. Yet, in most
    # cases it will be fine.
    def can_spend(self, amount):
        return (self.credits - amount) >= 0

    @transaction.atomic
    def spend_credits(self, amount, goal):
        try:
            # make sure you check that you can spend. If not you might get a nice error.
            if not self.can_spend(amount):
                raise ValueError('Not possible to spend credits, balance would go below zero.')

            mutation = CreditMutation(
                account=self,
                credits_spent=int(amount),
                credits_received=0,
                credit_mutation=-int(amount),
                at_when=datetime.now(pytz.utc),
                goal=goal,
            )
            mutation.save()
            self.credits -= int(amount)
            self.save(update_fields=['credits'])
        except BaseException as e:
            raise e

    @transaction.atomic
    def receive_credits(self, amount, goal):
        try:
            mutation = CreditMutation(
                account=self,
                credits_spent=0,
                credits_received=int(amount),
                credit_mutation=int(amount),
                at_when=datetime.now(pytz.utc),
                goal=goal,
            )
            mutation.save()
            self.credits += int(amount)
            self.save(update_fields=['credits'])
        except BaseException as e:
            raise e

    def __str__(self):
        return 'Account %s' % self.name


class CreditMutation(models.Model):
    """
    Transactionlog of all credits spent and received. It's total should be the current number of credits in the account.
    """

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
    )

    credits_received = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=0,
        help_text='A positive number of amount of credits received.'
    )

    credits_spent = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=0,
        help_text='A positive number of the amount of credits spent.'
    )

    credit_mutation = models.IntegerField(
        blank=True,
        null=True,
        default=0,
        help_text='The amount of credits received is positive, amount spent is negative.'
    )

    goal = models.TextField(
        max_length=1024,
        blank=True,
        help_text="Description on how the mutation came to be. For example: deposit, scan on XYZ, etc. Be as "
                  "complete as possible so it's obvious why credits where received and spent.",
        null=True,
    )

    at_when = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the transaction was made."
    )

    class Meta:
        get_latest_by = "at_when"
        ordering = ('-at_when', )


class ProUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
    )

    # some fields to get in touch with the user
    phone_number = models.CharField(
        max_length=120,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        max_length=800,
        blank=True,
        null=True,
    )


class UrlList(models.Model):
    # Todo: make reports for this. Make sure they can be stored here somewhere.
    name = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text="Name of the UrlList, for example name of the organization in it."
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        help_text="Who owns and manages this urllist."
    )

    urls = models.ManyToManyField(
        Url,
        blank=True
    )

    # Was a separate class, should the mail settings be a mixin?
    send_notifications = models.BooleanField(
        default=False,
    )

    send_notification_on_new_issue_with_high_risk = models.BooleanField(
        default=False,
    )

    send_notification_on_new_issue_with_medium_risk = models.BooleanField(
        default=False
    )

    send_notification_on_new_issue_with_low_risk = models.BooleanField(
        default=False
    )

    notification_receipients = models.CharField(
        max_length=800,
        default='',
        blank=True,
        null=True,
        # todo: validation of e-mail field. Relation?
    )

    send_reports = models.BooleanField(
        default=False
    )

    send_report_format = models.CharField(
        max_length=40,
        choices=[('html_inline', 'Inline HTML')],
        default='html_inline'
    )

    report_receipients = models.CharField(
        max_length=800,
        default='',
        blank=True,
        null=True,
    )

    def __str__(self):
        return 'Urllist %s (acc %s)' % (self.name, self.account_id)


class UrlListReport(SeriesOfUrlsReportMixin):
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
    urllist = models.ForeignKey(UrlList, on_delete=models.CASCADE)

    class Meta:
        get_latest_by = "at_when"
        index_together = [
            ["at_when", "id"],
        ]


class FailmapOrganizationDataFeed(models.Model):
    """
    A way to automatically add urls to the UrlList. If you associate this feed with an urllist, the urllist will be
    automatically expanded when new urls are discovered and added. They might behave as a ghost-organization.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text="Organization where urls come from."
    )

    urllist = models.ManyToManyField(
        UrlList,
    )


class UrlDataFeed(models.Model):

    # products are usually attached to a certain subdomain. This is for those cases.
    # basically all subdomains in the whole dataset...
    # maybe we should be able to filter on organization type or country, although it's unusual still. :)
    # when the need arises it's easy to build. So we do it then.
    subdomain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    topleveldomain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    urllist = models.ManyToManyField(
        UrlList,
    )


class RescanRequest(models.Model):

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        help_text="Who owns and manages this urllist."
    )

    cost = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=0,
        help_text='A positive number of the amount of credits spent for this re-scan.'
    )

    scan_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    scan_id = models.IntegerField(
        default=0,
        help_text='Makes it easy to find if a rescan is already requested.'
    )

    endpoint_scan = models.ForeignKey(
        EndpointGenericScan,
        on_delete=models.CASCADE,
        null=True
    )

    url_scan = models.ForeignKey(
        UrlGenericScan,
        on_delete=models.CASCADE,
        null=True
    )

    endpoint = models.ForeignKey(
        Endpoint,
        on_delete=models.CASCADE,
        null=True
    )

    url = models.ForeignKey(
        Url,
        on_delete=models.CASCADE,
        null=True
    )

    added_on = models.DateTimeField(
        blank=True,
        null=True,
    )

    started = models.BooleanField(
        default=False
    )

    started_on = models.DateTimeField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20
    )

    finished = models.BooleanField(
        default=False
    )

    finished_on = models.DateTimeField(
        blank=True,
        null=True,
    )
