import logging
from datetime import datetime, timedelta
from http.client import BadStatusLine
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import Any, Dict

import pytz
import requests
from constance import config
from django.db import transaction
from requests.exceptions import ConnectTimeout, ProxyError, SSLError
from tenacity import RetryError, before_log, retry, stop_after_attempt, wait_fixed
from urllib3.exceptions import ProtocolError

from websecmap.celery import app
from websecmap.scanners.models import ScanProxy

PROXY_NETWORK_TIMEOUT = 30
PROXY_SERVER_TIMEOUT = 30

log = logging.getLogger(__name__)


@app.task(queue="claim_proxy")
def claim_proxy(tracing_label="") -> Dict[str, Any]:
    """A proxy should first be claimed and then checked. If not, several scans might use the same proxy and thus
    crash.

    This is run on a dedicated worker as this is a blocking task.

    There used to be rate limiting to 30/hour. But that is not needed anymore since all scan tasks are now planned.
    These planned tasks claim whatever free proxy is available, if there are none, no proxies are even attempted to
    be claimed.
    """

    # try to get the first available, fastest, proxy
    while True:

        log.debug(f"Attempting to claim a proxy to scan {tracing_label} et al...")

        try:

            with transaction.atomic():

                # proxies can die if they are limited too often.
                proxy = (
                    ScanProxy.objects.all()
                    .filter(
                        is_dead=False,
                        currently_used_in_tls_qualys_scan=False,
                        manually_disabled=False,
                        request_speed_in_ms__gte=1,
                        # proxies that are too slow tend to have timeout errors
                        # self hosted proxies are between 150 and 300 ms.
                        # more proxy checks at the same time make slower results... disabled for now
                        # request_speed_in_ms__lte=2000
                    )
                    .order_by("request_speed_in_ms")
                    .first()
                )

                if proxy:

                    # first claim to prevent duplicate claims
                    log.debug(f"Proxy {proxy.id} claimed for {tracing_label} et al...")
                    proxy.currently_used_in_tls_qualys_scan = True
                    proxy.last_claim_at = datetime.now(pytz.utc)
                    proxy.save(update_fields=["currently_used_in_tls_qualys_scan", "last_claim_at"])

                    # we can't check for proxy quality here, as that will fill up the strorage with long tasks.
                    # instead run the proxy checking worker every hour or so to make sure the list stays fresh.
                    # if check_proxy(proxy):
                    #    log.debug('Using proxy %s for scan.' % proxy)
                    return {"id": proxy.pk, "address": proxy.address, "protocol": proxy.protocol}
                    # else:
                    #     log.debug('Proxy %s was not suitable for scanning. Trying another one in 60 seconds.' % proxy)

                else:
                    # do not log an error here, when forgetting to add proxies or if there are no clean proxies anymore,
                    # the queue might fill up with too many claim_proxy tasks. Each of them continuing in their own
                    # thread
                    # to get a proxy every 2 minutes (30/h). This can lead up to 30.000 issues per day.
                    # When you have over 500 proxy requests, things are off. It's better to start with a clean
                    # slate then.
                    log.debug(
                        f"No proxies available for {tracing_label} et al. "
                        f"You can add more proxies to solve this. Will try again in 60 seconds."
                    )

        except BaseException as e:
            # In some rare cases this method crashes, while it should be as reliable as can be.
            log.error(f"Exception occurred when requesting a proxy for {tracing_label} et al")
            log.exception(e)
            raise e

        sleep(60)


@app.task(queue="storage")
def release_proxy(proxy: Dict[str, Any], tracing_label=""):
    """As the claim proxy queue is ALWAYS filled, you cannot insert release proxy commands there..."""
    log.debug(f"Releasing proxy {proxy['id']} claimed for {tracing_label} et al...")

    db_proxy = ScanProxy.objects.all().filter(pk=proxy["id"]).first()
    if not db_proxy:
        return

    db_proxy.currently_used_in_tls_qualys_scan = False
    db_proxy.save(update_fields=["currently_used_in_tls_qualys_scan"])


@app.task(queue="storage")
def check_all_proxies():
    # celery doesn't work with asyncio. But it does work with threadpools.

    pool = ThreadPool(100)

    timeout_claims()

    proxies = ScanProxy.objects.all()
    for proxy in proxies:
        pool.apply_async(check_proxy, [proxy.as_dict()])

    pool.close()
    pool.join()


def timeout_claims():
    for proxy in ScanProxy.objects.all():
        release_claim_after_timeout(proxy.as_dict())


def release_claim_after_timeout(proxy: Dict[str, Any]):
    # Release all proxies that have been claimed a few hours before. As a scan of 25 addresss takes about 45 minutes.
    # And in bad cases only double that. So let's quadruple that time and then just release the proxy automatically
    # because of a timeout. Last claim at can be empty.

    db_proxy = ScanProxy.objects.all().filter(pk=proxy["id"]).first()
    if not db_proxy:
        return

    if db_proxy.last_claim_at:
        if all(
            [
                db_proxy.last_claim_at < datetime.now(pytz.utc) - timedelta(hours=3),
                db_proxy.currently_used_in_tls_qualys_scan,
            ]
        ):
            log.warning(f"Force released proxy {db_proxy.pk} because of a claim timeout period of 3 hours.")
            db_proxy.currently_used_in_tls_qualys_scan = False
            db_proxy.save(update_fields=["currently_used_in_tls_qualys_scan"])


@app.task(queue="internet")
def check_proxy(proxy: Dict[str, Any]):
    # todo: service_provider_status should stop after a certain amount of requests.
    # Note that you MUST USE HTTPS proxies for HTTPS traffic! Otherwise your normal IP is used.

    log.debug(f"Testing proxy {proxy['id']}")

    if not config.SCAN_PROXY_TESTING_URL:
        proxy_testing_url = "https://google.com/"
        log.debug("No SCAN_PROXY_TESTING_URL configured, falling back to google.com.")
    else:
        proxy_testing_url = config.SCAN_PROXY_TESTING_URL

    log.debug(f"Attempting to connect to testing url: {proxy_testing_url}")
    # send requests to a known domain to inspect the headers the proxies attach. There has to be something
    # that links various scans to each other.
    try:
        requests.get(
            proxy_testing_url,
            proxies={proxy["protocol"]: proxy["address"]},
            timeout=(PROXY_NETWORK_TIMEOUT, PROXY_SERVER_TIMEOUT),
            headers={
                "User-Agent": f"Request through proxy {proxy['id']}",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "DNT": "1",
            },
        )

    # Storage is handled async, because you might not be on the machine that is able to save data.
    except ProxyError:
        log.debug("ProxyError, Perhaps because: proxy does not support https.")
        store_check_result.apply_async(
            [proxy, "ProxyError, Perhaps because: proxy does not support https.", True, datetime.now(pytz.utc)]
        )
        return False
    except SSLError:
        log.debug("SSL error received.")
        store_check_result.apply_async([proxy, "SSL error received.", True, datetime.now(pytz.utc)])
        return False
    except ConnectTimeout:
        log.debug("Connection timeout.")
        store_check_result.apply_async([proxy, "Connection timeout.", True, datetime.now(pytz.utc)])
        return False
    except ConnectionError:
        log.debug("Connection error.")
        store_check_result.apply_async([proxy, "Connection error.", True, datetime.now(pytz.utc)])
        return False
    except ProtocolError:
        log.debug("Protocol error.")
        store_check_result.apply_async([proxy, "Protocol error.", True, datetime.now(pytz.utc)])
        return False
    except BadStatusLine:
        log.debug("Bad status line.")
        store_check_result.apply_async([proxy, "Bad status line.", True, datetime.now(pytz.utc)])
        return False

    log.debug(f"Could connect to test site {proxy_testing_url}. Proxy is functional.")

    log.debug("Attempting to connect to the Qualys API.")
    try:
        api_results = service_provider_status(proxy)
    except RetryError:
        log.debug("Retry error. Could not connect.")
        store_check_result.apply_async([proxy, "Retry error. Could not connect.", True, datetime.now(pytz.utc)])
        return False

    # tried a few times, no result. Proxy is dead.
    if not api_results:
        log.debug("No result, proxy not reachable?")
        store_check_result.apply_async([proxy, "No result, proxy not reachable?", True, datetime.now(pytz.utc)])
        return False

    if api_results["max"] < 20 or api_results["this-client-max"] < 20 or api_results["current"] > 19:
        log.debug("Out of capacity %s." % proxy)
        store_check_result.apply_async(
            [
                proxy,
                "Out of capacity.",
                True,
                datetime.now(pytz.utc),
                api_results["current"],
                api_results["max"],
                api_results["this-client-max"],
            ]
        )
        return False
    else:
        # todo: Request time via the proxy. Just getting google.com might take a lot of time...
        try:
            speed = requests.get(
                "https://apple.com",
                proxies={proxy["protocol"]: proxy["address"]},
                timeout=(PROXY_NETWORK_TIMEOUT, PROXY_SERVER_TIMEOUT),
            ).elapsed.total_seconds()
            log.debug("Website retrieved.")
        except ProxyError:
            log.debug("Could not retrieve website.")
            store_check_result.apply_async(
                [
                    proxy,
                    "Could not retrieve website.",
                    True,
                    datetime.now(pytz.utc),
                    api_results["current"],
                    api_results["max"],
                    api_results["this-client-max"],
                ]
            )
            return False
        except ConnectTimeout:
            log.debug("Proxy too slow for standard site.")
            store_check_result.apply_async(
                [
                    proxy,
                    "Proxy too slow for standard site.",
                    True,
                    datetime.now(pytz.utc),
                    api_results["current"],
                    api_results["max"],
                    api_results["this-client-max"],
                ]
            )
            return False

        # todo: how to check the headers the proxy sends to the client? That requires a server to receive
        # requests. Proxies wont work if they are not "elite", aka: not revealing the internet user behind them.
        # otherwise the data will be coupled to a single client.

        log.debug(f"Proxy accessible. Capacity available. {proxy['id']}.")
        store_check_result.apply_async(
            [
                proxy,
                "Proxy accessible. Capacity available.",
                False,
                datetime.now(pytz.utc),
                api_results["current"],
                api_results["max"],
                api_results["this-client-max"],
                int(speed * 1000),
            ]
        )
        return True


@app.task(queue="storage")
def store_check_result(
    proxy: Dict[str, Any],
    check_result,
    is_dead: bool,
    check_result_date,
    qualys_capacity_current=-1,
    qualys_capacity_max=-1,
    qualys_capacity_this_client=-1,
    request_speed_in_ms=-1,
):
    """Separates this to storage, so that capacity scans can be performed on another worker."""

    db_proxy = ScanProxy.objects.all().filter(pk=proxy["id"]).first()
    if not proxy:
        return

    db_proxy.is_dead = is_dead
    db_proxy.check_result = check_result
    db_proxy.check_result_date = check_result_date
    db_proxy.qualys_capacity_max = qualys_capacity_max
    db_proxy.qualys_capacity_current = qualys_capacity_current
    db_proxy.qualys_capacity_this_client = qualys_capacity_this_client
    db_proxy.request_speed_in_ms = request_speed_in_ms
    db_proxy.save()


@retry(wait=wait_fixed(30), stop=stop_after_attempt(3), before=before_log(log, logging.DEBUG))
def service_provider_status(proxy: Dict[str, Any]):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

    response = requests.get(
        "https://api.ssllabs.com/api/v2/getStatusCodes",
        params={},
        timeout=(PROXY_NETWORK_TIMEOUT, PROXY_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_1) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/79.0.3945.130 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,"
            "*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
        },
        proxies={proxy["protocol"]: proxy["address"]},
        cookies={},
    )

    # inspect to see if there are cookies or other tracking variables.
    log.debug("Cookies: %s Proxy: %s" % (proxy, response.cookies))

    """
    Always the same response. This is just used to get a correct response and the available capacity.

     {'statusDetails': {'TESTING_PROTOCOL_INTOLERANCE_399': 'Testing Protocol Intolerance (TLS 1.152)',
     'PREPARING_REPORT': 'Preparing the report', 'TESTING_SESSION_RESUMPTION': 'Testing session resumption',
     'RETRIEVING_CERT_V3__NO_SNI': 'Retrieving certificate', 'TESTING_NPN': 'Testing NPN',
     'RETRIEVING_CERT_V3__SNI_APEX': 'Retrieving certificate', 'TESTING_CVE_2014_0224': 'Testing CVE-2014-0224',
     'TESTING_CAPABILITIES': 'Determining server capabilities', 'TESTING_CVE_2016_2107': 'Testing CVE-2016-2107',
     'TESTING_HEARTBLEED': 'Testing Heartbleed', 'TESTING_PROTO_3_3_V2H': 'Testing TLS 1.1 (v2 handshake)',
     'TESTING_SESSION_TICKETS': 'Testing Session Ticket support', 'VALIDATING_TRUST_PATHS': 'Validating trust paths',
     'TESTING_RENEGOTIATION': 'Testing renegotiation', 'TESTING_HTTPS': 'Sending one complete HTTPS request',
     'TESTING_ALPN': 'Determining supported ALPN protocols', 'TESTING_V2H_HANDSHAKE': 'Testing v2 handshake',
     'TESTING_STRICT_RI': 'Testing Strict Renegotiation', 'TESTING_HANDSHAKE_SIMULATION': 'Simulating handshakes',
     'TESTING_SUITES_DEPRECATED': 'Testing deprecated cipher suites', 'TESTING_STRICT_SNI': 'Testing Strict SNI',
     'TESTING_PROTOCOL_INTOLERANCE_499': 'Testing Protocol Intolerance (TLS 2.152)', 'TESTING_PROTO_3_1_V2H':
     'Testing TLS 1.0 (v2 handshake)', 'TESTING_TLS_VERSION_INTOLERANCE': 'Testing TLS version intolerance',
     'TESTING_BLEICHENBACHER': 'Testing Bleichenbacher', 'TESTING_PROTOCOL_INTOLERANCE_304':
     'Testing Protocol Intolerance (TLS 1.3)', 'TESTING_SUITES_BULK': 'Bulk-testing less common cipher suites',
     'TESTING_BEAST': 'Testing for BEAST', 'TESTING_PROTO_2_0': 'Testing SSL 2.0', 'TESTING_TICKETBLEED':
     'Testing Ticketbleed', 'BUILDING_TRUST_PATHS': 'Building trust paths', 'TESTING_PROTO_3_1': 'Testing TLS 1.0',
     'TESTING_PROTO_3_0_V2H': 'Testing SSL 3.0 (v2 handshake)', 'TESTING_PROTO_3_0': 'Testing SSL 3.0',
     'TESTING_PROTOCOL_INTOLERANCE_300': 'Testing Protocol Intolerance (SSL 3.0)', 'TESTING_PROTOCOL_INTOLERANCE_301':
     'Testing Protocol Intolerance (TLS 1.0)', 'TESTING_PROTOCOL_INTOLERANCE_302':
     'Testing Protocol Intolerance (TLS 1.1)', 'TESTING_SUITES_NO_SNI': 'Observed extra suites during simulation,
     Testing cipher suites without SNI support', 'TESTING_EC_NAMED_CURVES': 'Determining supported named groups',
     'TESTING_PROTOCOL_INTOLERANCE_303': 'Testing Protocol Intolerance (TLS 1.2)', 'TESTING_OCSP_STAPLING_PRIME':
     'Trying to prime OCSP stapling', 'TESTING_DROWN': 'Testing for DROWN', 'TESTING_EXTENSION_INTOLERANCE':
     'Testing Extension Intolerance (might take a while)', 'TESTING_OCSP_STAPLING': 'Testing OCSP stapling',
     'TESTING_SSL2_SUITES': 'Checking if SSL 2.0 has any ciphers enabled', 'TESTING_SUITES':
     'Determining available cipher suites', 'TESTING_ECDHE_PARAMETER_REUSE': 'Testing ECDHE parameter reuse',
     'TESTING_PROTO_3_2_V2H': 'Testing TLS 1.1 (v2 handshake)', 'TESTING_POODLE_TLS': 'Testing POODLE against TLS',
     'RETRIEVING_CERT_TLS13': 'Retrieving certificate', 'RETRIEVING_CERT_V3__SNI_WWW': 'Retrieving certificate',
     'TESTING_PROTO_3_4': 'Testing TLS 1.3', 'TESTING_COMPRESSION': 'Testing compression', 'CHECKING_REVOCATION':
     'Checking for revoked certificates', 'TESTING_SUITE_PREFERENCE': 'Determining cipher suite preference',
     'TESTING_PROTO_3_2': 'Testing TLS 1.1', 'TESTING_PROTO_3_3': 'Testing TLS 1.2', 'TESTING_LONG_HANDSHAKE':
     'Testing Long Handshake (might take a while)'}}
    """

    # log.debug(vars(response))  # extreme debugging
    # The x-max-assements etc have been removed from the response headers in december 2019.
    # always return the max available. And make sure the claiming works as intended.
    log.debug(
        "Status: max: %s, current: %s, this client: %s, proxy: %s",
        response.headers.get("X-Max-Assessments", 25),
        response.headers.get("X-Current-Assessments", 0),
        response.headers.get("X-ClientMaxAssessments", 25),
        proxy['id'],
    )

    return {
        "max": int(response.headers.get("X-Max-Assessments", 25)),
        "current": int(response.headers.get("X-Current-Assessments", 0)),
        "this-client-max": int(response.headers.get("X-ClientMaxAssessments", 25)),
        "data": response.json(),
    }
