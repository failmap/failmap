"""
SMTP DANE with DNSSEC is bij Microsoft in ontwikkeling.
In maart dit jaar een Public Preview en vanaf Juli 2024 pas General Available.
https://techcommunity.microsoft.com/t5/exchange-team-blog/
    implementing-inbound-smtp-dane-with-dnssec-for-exchange-online/ba-p/3939694
"""
from datetime import datetime, timezone

from celery import group

from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan, GeoIp, DomainIp, DomainMX

explanation = "microsoft_applies_dane_from_july_2024"
accepted_as = ["MICROSOFT-CORP-MSN-AS-BLOCK"]


@app.task(queue="storage", ignore_result=True)
def correct():
    # if the mailserver is in the microsoft as AND all other internet.nl mail metrics are right and only DANE
    # is not.
    scans = EndpointGenericScan.objects.filter(
        type="internet_nl_mail_tls", rating="failed", is_the_latest_scan=True, comply_or_explain_is_explained=False
    )
    group([correct_scan.si(scan.id) for scan in scans]).apply_async()


@app.task(queue="storage", ignore_result=True)
def correct_scan(scan_id: int):
    scan = EndpointGenericScan.objects.filter(id=scan_id).first()
    if not scan:
        log.debug("No scan found with id %s", scan_id)
        return

    # todo: dit per scan doen, dan schaalt het beter. En mss inplannen.
    # is in MS netblock?
    url = scan.endpoint.url.url
    first_mx = DomainMX.objects.all().filter(domain=url, is_the_latest=True).first()
    if not first_mx:
        log.debug("No first_mx found for %s", url)
        return

    mail_server_records = first_mx.mail_server_records
    if not mail_server_records:
        log.debug("No mail_server_records found for %s", url)
        return
    first_server = mail_server_records[0].get("domain", None)
    if not first_server:
        log.debug("No first_server found for %s", url)
        return
    domainip = DomainIp.objects.all().filter(domain=first_server, is_the_latest=True).first()
    if not domainip:
        log.debug("No domainip found for %s", url)
        return
    geoip = GeoIp.objects.all().filter(ip_address=domainip.ip_address, is_the_latest=True).first()
    if not geoip:
        log.debug("No geoip found for %s", domainip.ip_address)
        return
    if geoip.as_organization not in accepted_as:
        log.debug("AS %s is not in %s", geoip.as_organization, accepted_as)
        return
    # are all other TLS metrics from internet.nl on this domain correct?
    # should use the legacy metric?
    ncsc_starttls_fields = [
        "internet_nl_mail_starttls_tls_available",
        "internet_nl_mail_starttls_tls_keyexchange",
        "internet_nl_mail_starttls_tls_compress",
        "internet_nl_mail_starttls_tls_secreneg",
        "internet_nl_mail_starttls_tls_ciphers",
        "internet_nl_mail_starttls_tls_clientreneg",
        "internet_nl_mail_starttls_tls_version",
        "internet_nl_mail_starttls_tls_cipherorder",
        "internet_nl_mail_starttls_tls_keyexchangehash",
        "internet_nl_mail_starttls_tls_0rtt",
        "internet_nl_mail_starttls_cert_sig",
        "internet_nl_mail_starttls_cert_pubkey",
        "internet_nl_mail_starttls_cert_chain",
        "internet_nl_mail_starttls_cert_domain",
    ]
    metrics = EndpointGenericScan.objects.filter(
        endpoint=scan.endpoint, type__in=ncsc_starttls_fields, is_the_latest_scan=True, rating="failed"
    )
    # some metrics are failed, so this is not good.
    if metrics.count():
        log.info("Found %s failed metrics for %s, so not only dane errors", metrics.count(), scan.endpoint)
        return
    # dane has failed, while the rest has not.
    if EndpointGenericScan.objects.filter(
        endpoint=scan.endpoint,
        type="internet_nl_mail_starttls_dane_exist",
        is_the_latest_scan=True,
        rating="failed",
    ).first():
        log.debug("OK: Will add a DANE exception to %s", url)
        print(f"OK: Will add a DANE exception to {url}")
        add_bot_explanation(scan, explanation, datetime(2024, 7, 1, tzinfo=timezone.utc) - datetime.now(timezone.utc))
