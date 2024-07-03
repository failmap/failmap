from django.db import models
from django.utils.translation import gettext_lazy as _
from jsonfield import JSONField

from websecmap.app.fields import CompressedJSONField
from websecmap.organizations.models import Url


class AllIssuesCombined(models.Model):
    """
    This counts ALL issues of all endpoint genericscan and urlgenericscan for a series of URL or a URL report.
    """

    total_issues = models.IntegerField(default=0)
    high = models.IntegerField(default=0)
    medium = models.IntegerField(default=0)
    low = models.IntegerField(default=0)
    ok = models.IntegerField(default=0)
    not_applicable = models.IntegerField(default=0)
    not_testable = models.IntegerField(default=0)
    error_in_test = models.IntegerField(default=0)

    class Meta:
        abstract = True


class EndpointIssues(models.Model):
    """
    A sum of issues per endpoint. An endpoint can have many scans with various severities.
    It sums up EndpointGenericScans.
    """

    total_endpoint_issues = models.IntegerField(
        help_text="A sum of all endpoint issues for this endpoint, it includes all high, medium and lows.", default=0
    )

    endpoint_issues_high = models.IntegerField(
        help_text="Total amount of high risk issues on this endpoint.", default=0
    )

    endpoint_issues_medium = models.IntegerField(
        help_text="Total amount of medium risk issues on this endpoint.", default=0
    )

    endpoint_issues_low = models.IntegerField(help_text="Total amount of low risk issues on this endpoint", default=0)

    endpoint_ok = models.IntegerField(
        help_text="Amount of measurements that resulted in an OK score on this endpoint.", default=0
    )

    endpoint_not_testable = models.IntegerField(
        help_text="Amount of things that could not be tested on this endpoint.", default=0
    )

    endpoint_not_applicable = models.IntegerField(
        help_text="Amount of things that are not applicable on this endpoint.", default=0
    )

    endpoint_error_in_test = models.IntegerField(
        help_text="Amount of errors in tests performed on this endpoint.", default=0
    )

    class Meta:
        abstract = True


class UrlIssues(models.Model):
    """
    The same as EndpointGenericScan, but then on URL level.
    """

    total_url_issues = models.IntegerField(help_text="Total amount of issues on url level.", default=0)

    url_issues_high = models.IntegerField(help_text="Number of high issues on url level.", default=0)

    url_issues_medium = models.IntegerField(help_text="Number of medium issues on url level.", default=0)

    url_issues_low = models.IntegerField(help_text="Number of low issues on url level.", default=0)

    url_ok = models.IntegerField(help_text="Zero issues on these urls.", default=0)

    url_not_testable = models.IntegerField(
        help_text="Amount of things that could not be tested on this url.", default=0
    )

    url_not_applicable = models.IntegerField(
        help_text="Amount of things that are not applicable on this url.", default=0
    )

    url_error_in_test = models.IntegerField(help_text="Amount of errors in tests on this url.", default=0)

    class Meta:
        abstract = True


class JudgedUrls(models.Model):
    """
    This contains stats over judged urls in a series of URL Reports. A judged url gives insight in the state of
    a url. For example: If you have a url with 10 high issues and 5 medium issues, the url is judged to be high.
    For each Url a maximum of 1 value is used: judging basically reduces the amount of issues to a single value
    representing the url.

    Judging is done for endpoints and urls.

    Example: 5 total_urls, 3 high_urls, 2 medium_urls
    """

    total_urls = models.IntegerField(help_text="Amount of urls for this organization.", default=0)
    high_urls = models.IntegerField(help_text="Amount of urls with (1 or more) high risk issues.", default=0)
    medium_urls = models.IntegerField(help_text="Amount of urls with (1 or more) medium risk issues.", default=0)
    low_urls = models.IntegerField(help_text="Amount of urls with (1 or more) low risk issues.", default=0)
    ok_urls = models.IntegerField(help_text="Amount of urls with zero issues.", default=0)

    class Meta:
        abstract = True


class JudgedEndpoints(models.Model):
    total_endpoints = models.IntegerField(help_text="Amount of endpoints for this url.", default=0)
    high_endpoints = models.IntegerField(help_text="Amount of endpoints with (1 or more) high risk issues.", default=0)
    medium_endpoints = models.IntegerField(
        help_text="Amount of endpoints with (1 or more) medium risk issues.", default=0
    )
    low_endpoints = models.IntegerField(help_text="Amount of endpoints with (1 or more) low risk issues.", default=0)
    ok_endpoints = models.IntegerField(help_text="Amount of endpoints with zero issues.", default=0)

    class Meta:
        abstract = True


class AllExplainedIssuesCombined(models.Model):
    """
    The same as all above statistics classes, but with the major difference that this does not contain
    not_testable, not_applicable and error in test. Each EndpointGenericScan and UrlGEnericScan can be explained.
    Instead of counting towards the normal set of issues, separate statistics are created over this.

    Everything that is explained therefore does not count as a 'good' value, only as an explained 'bad' value.
    """

    explained_total_issues = models.IntegerField(
        help_text="The summed number of all vulnerabilities and failures.", default=0
    )

    explained_high = models.IntegerField(help_text="The number of high risk vulnerabilities and failures.", default=0)

    explained_medium = models.IntegerField(
        help_text="The number of medium risk vulnerabilities and failures.", default=0
    )

    explained_low = models.IntegerField(help_text="The number of low risk vulnerabilities and failures.", default=0)

    class Meta:
        abstract = True


class ExplainedEndpointIssues(models.Model):
    """
    Some issues can be explained. This counts the amount of explained issues on a single endpoint for all
    explained scans below it.
    """

    explained_total_endpoint_issues = models.IntegerField(
        help_text="Total amount of issues on endpoint level.", default=0
    )

    explained_endpoint_issues_high = models.IntegerField(
        help_text="Total amount of issues on endpoint level.", default=0
    )

    explained_endpoint_issues_medium = models.IntegerField(
        help_text="Total amount of issues on endpoint level.", default=0
    )

    explained_endpoint_issues_low = models.IntegerField(
        help_text="Total amount of issues on endpoint level.", default=0
    )

    class Meta:
        abstract = True


class ExplainedUrlIssues(models.Model):
    explained_total_url_issues = models.IntegerField(help_text="Total amount of issues on endpoint level.", default=0)

    explained_url_issues_high = models.IntegerField(help_text="Total amount of issues on endpoint level.", default=0)

    explained_url_issues_medium = models.IntegerField(help_text="Total amount of issues on endpoint level.", default=0)

    explained_url_issues_low = models.IntegerField(help_text="Total amount of issues on endpoint level.", default=0)

    class Meta:
        abstract = True


class ExplainedJudgedUrls(models.Model):
    """
    I can't imagine this being used. It's the amount of urls that are judged to have one or more explanation.
    It's already hard to understand. It's of course easy to make in statistics, but why?
    """

    explained_total_urls = models.IntegerField(help_text="Amount of urls for this organization.", default=0)
    explained_high_urls = models.IntegerField(help_text="Amount of urls with (1 or more) high risk issues.", default=0)
    explained_medium_urls = models.IntegerField(
        help_text="Amount of urls with (1 or more) medium risk issues.", default=0
    )
    explained_low_urls = models.IntegerField(help_text="Amount of urls with (1 or more) low risk issues.", default=0)

    class Meta:
        abstract = True


class ExplainedJudgedEndpoints(models.Model):
    """
    See ExplainedJudgedUrls
    """

    explained_total_endpoints = models.IntegerField(help_text="Amount of endpoints for this url.", default=0)
    explained_high_endpoints = models.IntegerField(
        help_text="Amount of endpoints with (1 or more) high risk issues.", default=0
    )
    explained_medium_endpoints = models.IntegerField(
        help_text="Amount of endpoints with (1 or more) medium risk issues.", default=0
    )
    explained_low_endpoints = models.IntegerField(
        help_text="Amount of endpoints with (1 or more) low risk issues.", default=0
    )

    class Meta:
        abstract = True


# todo: store amount of OK and the percentage.
class SeriesOfUrlsReportMixin(
    AllIssuesCombined,
    JudgedUrls,
    JudgedEndpoints,
    UrlIssues,
    EndpointIssues,
    AllExplainedIssuesCombined,
    ExplainedJudgedUrls,
    ExplainedJudgedEndpoints,
    ExplainedUrlIssues,
    ExplainedEndpointIssues,
):  # pylint: disable=too-many-ancestors
    """
    This contains a series of URL reports statistics, it has the same fields as url report statistics,
    but because this is about multiple urls, it also contains JudgedUrls and ExplainedJudgedUrls.
    """

    at_when = models.DateTimeField(db_index=True)
    calculation = JSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment, for all urls "
        "of this organization. This can be a lot."
    )  # calculations of the independent urls... and perhaps others?

    def __str__(self):
        if any([self.high, self.medium, self.low]):
            return f"🔴{self.high} 🔶{self.medium} 🍋{self.low} | {self.at_when.date()}"

        return f"✅ perfect | {self.at_when.date()}"

    class Meta:
        abstract = True


class UrlReport(
    AllIssuesCombined,
    JudgedEndpoints,
    UrlIssues,
    EndpointIssues,
    AllExplainedIssuesCombined,
    ExplainedJudgedEndpoints,
    ExplainedUrlIssues,
    ExplainedEndpointIssues,
):  # pylint: disable=too-many-ancestors
    """
    A UrlReport is an aggregation of all scans below it: on urls and endpoints. It's all for a single URL.

    This is what you'll find in the calculation field:
    UrlReport:
        Url:
            Issues:
                Issue 1,
                Issue 2
            Endpoints:
                Endpoint 1:
                    Issues:
                        Issue 3,
                        Issue 4
    """

    url = models.ForeignKey(Url, on_delete=models.CASCADE)

    at_when = models.DateTimeField(db_index=True)
    calculation = CompressedJSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment. The rating can "
        "be spread out over multiple endpoints, which might look a bit confusing. Yet it "
        "is perfectly possible as some urls change their IP every five minutes and "
        "scans are spread out over days."
    )

    is_the_newest = models.BooleanField(
        default=False,
        help_text="The newest url report allows for quick retrieval of the current state, it prevents complex queries.",
        blank=True,
    )

    class Meta:
        managed = True
        verbose_name = _("Url Report")
        verbose_name_plural = _("Url Reports")

    def __str__(self):
        return f"{self.high},{self.medium},{self.low}  - {self.at_when.date()}"


class LatestUrlReport(
    AllIssuesCombined,
    JudgedEndpoints,
    UrlIssues,
    EndpointIssues,
    AllExplainedIssuesCombined,
    ExplainedJudgedEndpoints,
    ExplainedUrlIssues,
    ExplainedEndpointIssues,
):
    # This is exactly the same as urlreport, but only the ones with 'is_the_newest' are stored in this table.
    # The reason is that the table of UrlReport is very large: one report per day per url on average which makes
    # any form of rapidly searching hard given the amount of disk/ram is needed to walk over the results.
    # once cached it IS fast of course, but this table is very much out of hand.
    # This table is created and filled when new UrlReports are made automatically and only contains the latest
    # urlreport per url. This should make searching in + very fast. The search before this fix takes over 500 seconds
    # for very large organizations with a lot of url reports.

    # and no you cannot subclass UrlReport!

    url = models.ForeignKey(Url, on_delete=models.CASCADE)

    at_when = models.DateTimeField(db_index=True)
    calculation = CompressedJSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment. The rating can "
        "be spread out over multiple endpoints, which might look a bit confusing. Yet it "
        "is perfectly possible as some urls change their IP every five minutes and "
        "scans are spread out over days."
    )

    is_the_newest = models.BooleanField(
        default=False,
        help_text="The newest url report allows for quick retrieval of the current state, it prevents complex queries.",
        blank=True,
    )

    class Meta:
        managed = True


# todo: we can make a vulnerabilitystatistic per organization type or per tag. But not per country, list etc.


class ScanPolicy(AllIssuesCombined):
    scan_type = models.CharField(
        max_length=60,
        db_index=True,
    )
    conclusion = models.CharField(
        # the result that something gets from the scanner.
        max_length=128,
        default="",
    )
    explanation = models.CharField(
        max_length=255, help_text="Short explanation from the scanner on how the rating came to be.", blank=True
    )
    annotation = models.TextField(
        max_length=8000,
        help_text="This allows policy makers to write down something about why a conclusion results in what score...",
        blank=True,
    )

    def summary_text(self):
        # for simple representations where emojis are not supported
        text = []

        if self.low:
            text += ["low"]

        if self.medium:
            text += ["medium"]

        if self.high:
            text += ["high"]

        if self.error_in_test:
            text += ["error"]

        if self.not_applicable:
            text += ["N/A"]

        if self.not_testable:
            text += ["Not Testable"]

        if self.ok:
            text += ["ok"]

        if not text:
            text = ["neutral"]

        return ", ".join(text)

    def summary_emoji(self):
        # for traffic light only representation
        text = []

        if self.low:
            text += ["🟡"]

        if self.medium:
            text += ["🟠"]

        if self.high:
            text += ["🔴"]

        if self.error_in_test:
            text += ["❌"]

        if self.not_applicable:
            text += ["❌"]

        if self.not_testable:
            text += ["❌"]

        if self.ok:
            text += ["🟢"]

        if not text:
            text = ["⚪"]

        return ", ".join(text)

    def summary_text_and_emoji(self):
        # for the nicest representation in the admin etc
        text = []

        if self.low:
            text += ["🟡 low"]

        if self.medium:
            text += ["🟠 medium"]

        if self.high:
            text += ["🔴 high"]

        if self.error_in_test:
            text += ["❌ error"]

        if self.not_applicable:
            text += ["❌ N/A"]

        if self.not_testable:
            text += ["❌ Not Testable"]

        if self.ok:
            text += ["🟢 ok"]

        if not text:
            text = ["⚪ neutral"]

        return ", ".join(text)

    def __str__(self):
        # Django admin cannot deal with emojis, such as 🏅 (django 3 at least)
        # b'INSERT INTO `django_admin_log` (`action_time`, `user_id`, `content_type_id`, `object_id`, `object_repr`,
        #   `action_flag`, `change_message`) VALUES (\'2022-09-09 07:52:07.296311\', 1, 62, \'942\',
        #   \'\xf0\x9f\x8f\x85 [internet_nl_mail_ipv6 passed]\', 1, \'[{\\"added\\": {}}]\')'
        # -> (1366, "Incorrect string value: '\\xF0\\x9F\\x8F\\x85 [...' for column 'object_repr' at row 1")
        return f"{self.scan_type}: {self.conclusion} ({self.summary_text()})"


class MajorChange(models.Model):
    # this is used in graph annotations to explain changes. Such as major increases in domains, major policy changes
    # such as higher or lower risks etc
    at_when = models.DateField()
    change_code = models.CharField(
        max_length=128,
        help_text="machine readable place holder, only lowercase letters, numbers, underscores. This is used "
        "to translate the change in the frontend graphs.",
    )
    change_title = models.CharField(max_length=128, blank=True, help_text="For internal use")
    change_message = models.TextField(
        help_text="This allows policy makers to write down something about "
        "why a conclusion results in what score... Please provide as much context and detail as possible. "
        "For internal use.",
        blank=True,
    )
