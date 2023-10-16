# Generated by Django 3.1.6 on 2021-06-26 13:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scanners", "0003_auto_20210524_1233"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plannedscan",
            name="scanner",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "unknown"),
                    (1, "tls_qualys"),
                    (2, "dnssec"),
                    (3, "security_headers"),
                    (4, "plain_http"),
                    (5, "internet_nl_mail"),
                    (6, "ftp"),
                    (7, "dns_endpoints"),
                    (8, "internet_nl_web"),
                    (9, "subdomains"),
                    (10, "dns_known_subdomains"),
                    (11, "dns_clean_wildcards"),
                    (12, "http"),
                    (13, "verify_unresolvable"),
                    (14, "onboard"),
                    (15, "ipv6"),
                    (16, "dns_wildcards"),
                    (17, "dummy"),
                    (18, "screenshot"),
                    (100, "autoexplain_dutch_untrusted_cert"),
                    (101, "autoexplain_trust_microsoft"),
                    (102, "autoexplain_no_https_microsoft"),
                    (103, "autoexplain_microsoft_neighboring_services"),
                ],
                db_index=True,
                default=0,
            ),
        ),
    ]