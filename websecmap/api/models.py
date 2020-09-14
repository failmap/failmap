from django.contrib.auth.models import User
from django.db import models
from jsonfield import JSONField


class SIDNUpload(models.Model):
    """
    Transactionlog of all credits spent and received. It's total should be the current number of credits in the account.
    """

    by_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
    )

    at_when = models.DateTimeField(blank=True, null=True, help_text="When the transaction was made.")

    state = models.CharField(
        max_length=120,
        default="new",
    )

    posted_data = models.TextField(
        default="",
        help_text="This is the raw CSV data that is uploaded. This is well in the megabytes "
        "(3 reasonably large municipal domains = ±1 MB)",
    )

    newly_added_domains = JSONField(
        help_text="A list of strings containing what domains have been added with this upload."
    )

    amount_of_newly_added_domains = models.PositiveIntegerField(default=0)

    class Meta:
        get_latest_by = "at_when"
        ordering = ("-at_when",)
