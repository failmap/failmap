from django.db import models
from django.utils.translation import gettext_lazy as _
from jsonfield import JSONField

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
):
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
            return "🔴%s 🔶%s 🍋%s | %s" % (
                self.high,
                self.medium,
                self.low,
                self.at_when.date(),
            )
        else:
            return "✅ perfect | %s" % self.at_when.date()

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
):
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
    calculation = JSONField(
        help_text="Contains JSON with a calculation of all scanners at this moment. The rating can "
        "be spread out over multiple endpoints, which might look a bit confusing. Yet it "
        "is perfectly possible as some urls change their IP every five minutes and "
        "scans are spread out over days."
    )

    class Meta:
        managed = True
        verbose_name = _("Url Report")
        verbose_name_plural = _("Url Reports")

    def __str__(self):
        return "%s,%s,%s  - %s" % (
            self.high,
            self.medium,
            self.low,
            self.at_when.date(),
        )


# todo: we can make a vulnerabilitystatistic per organization type or per tag. But not per country, list etc.
