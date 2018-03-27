import logging
from datetime import datetime
from typing import List

import pytz
from celery import chain, group, chord

from failmap.app.models import Job
from failmap.organizations.models import Url
from failmap.scanners import (scanner_dnssec, scanner_http, scanner_plain_http,
                              scanner_security_headers, scanner_tls_qualys)
from failmap.scanners.scanner_dns import brute_known_subdomains, certificate_transparency, nsec

from ..celery import app, PRIO_HIGH

log = logging.getLogger(__package__)


# TODO: make queue explicit, split functionality in storage and scanner
@app.task
def onboard_new_urls():
    never_onboarded = Url.objects.all().filter(onboarded=False)

    if never_onboarded.count() > 0:
        cyber = """

    ................................................................................
    .......-:////:.....:-.......::...-///////:-......://////////:..../////////:.....
    ...../mMMMMMMMN...NMM+.....hMMy..+MMMMMMMMMNy-...dMMMMMMMMMMMN..-MMMMMMMMMMNy...
    ....+MMMhsssss/...MMMd-.../NMMd..+MMMyssssmMMN-..dMMNssssssss/..-MMMdsssssNMMy..
    ...+MMMy........../mMMNo-yMMMh-..+MMM:....:MMM+..dMMm...........-MMMy+++++NMMh..
    ../MMMy.............sMMMMMMm/....+MMMo+++odMMM:..dMMm+++/.......-MMMMMMMMMMMd-..
    ..hMMN...............:dMMMy......+MMMMMMMMMMMo...dMMMMMMM/......-MMMhhMMMd+-....
    ../MMMy...............oMMM-......+MMMo++++dMMM:..dMMm+++/.......-MMMo.sMMMs.....
    ...+MMMy..............oMMM-......+MMM:....:MMM+..dMMm...........-MMMo..+MMMh....
    ....+MMMdsssss/.......oMMM-......+MMMysssymMMN-..dMMNssssssss/..-MMMo.../NMMm-..
    ...../dMMMMMMMN......./MMN.......+MMMMMMMMMNy-...dMMMMMMMMMMMN...NMM+....-mMMs..
    .......-::::::.........-:........-::::::::-......::::::::::::.....:-.......::...
    ................................................................................
            """
        log.info("There are %s new urls to onboard! %s" % (never_onboarded.count(), cyber))
    else:
        log.info("No new urls to onboard.")

    onboard_urls(never_onboarded[0:8])


@app.task(queue='storage')
def finish_onboarding(url):
    url.onboarded = True
    url.onboarded_on = datetime.now(pytz.utc)
    url.save()


# this will of course only work while debugging on a __single__ worker :)
@app.task(queue='scanners')
def onboard_status(url, message):
    log.info('Now performing %s on %s', message, url)


# TODO: make queue explicit, split functionality in storage and scanner
@app.task(queue='storage')
def onboard_urls(urls: List[Url]):

    if not urls:
        return

    # is this executed per group, and do we wait to start with another group when everything in a certain group is done?
    # Chaining a group together with another task will automatically upgrade it to be a chord
    # all tasks per group of urls: url(a), url(b), url(c)...
    # saved since it documents another approach...
    # tasks = (group(nsec.si(urls=[url]) for url in urls)
    #          | group(certificate_transparency.si(urls=[url]) for url in urls)
    #          | group(brute_known_subdomains.si(urls=[url]) for url in urls)
    #          | group(scanner_http.discover_endpoints_on_standard_ports.si(urls=[url]) for url in urls)
    #          | group(scanner_plain_http.scan_url.si(url=url) for url in urls)
    #          | group(scanner_security_headers.compose_task.si(urls_filter={"url": url}) for url in urls)
    #          | group(finish_onboarding.si(url=url) for url in urls)
    #          )

    # all tasks sequentially per url... url(a,b,c).

    # it's possible that a task is finished, while the results are still being added in the worker queue.
    # this means the following task will fail :( -> it should also wait for the storage task etc...
    # But even if there are things already, the chain does not complete, without warnings or errors.
    tasks = group([
        chain(
            onboard_status.si(url, '1/9 certificate_transparency'),
            certificate_transparency.si(urls=[url]) if url.is_top_level() else ignore_hack.si(),
            onboard_status.si(url, '2/9 nsec'),
            nsec.si(urls=[url]) if url.is_top_level() else ignore_hack.si(),
            onboard_status.si(url, '3/9 brute'),
            brute_known_subdomains.si(urls=[url]) if url.is_top_level() else ignore_hack.si(),
            onboard_status.si(url, '4/9 dnssec, if toplevel'),
            scanner_dnssec.compose_task.si(urls_filter={"url": url}) if url.is_top_level() else ignore_hack.si(),
            onboard_status.si(url, '5/9 discover endpoints'),
            scanner_http.discover_endpoints_on_standard_ports.si(urls=[url]),
            onboard_status.si(url, '6/9 unsecured endpoints'),
            scanner_plain_http.scan_url.si(url=url),
            onboard_status.si(url, '7/9 security headers'),
            # we don't really NEED to wait for scan_security headers to finish. It will break the chain somehow
            # therefore we're just running the last three things in parallel. But it gets executed right away.
            scanner_security_headers.compose_task.si(urls_filter={"url": url}),
            onboard_status.si(url, '8/9 tls scan'),
            scanner_tls_qualys.compose_task.si(urls_filter={"url": url}),
            onboard_status.si(url, '9/9 finish'),
            finish_onboarding.si(url=url)) for url in urls])

    # really don't wait for the output.
    Job.create(tasks, "onboard", None, priority=PRIO_HIGH)


@app.task
def ignore_hack():
    return True
