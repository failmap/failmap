"""
Creating screenshots isn't easy.

There are some examples on the web of how to make screenshots with python, yet they all have significant issues.
During development of this feature we came accross the following solutions:

- Discarded: PyQt
Is not copy-paste installable, no pip command, little howto's, but ready code samples.

- Discarded: pyside
does not support newer python versions, it's not important enough to lag versions over it

- Discarded: cefpython
example is convoluted due to scoping, results in "illegal instruction 4"
when trying to run a second screenshot, even though shutdown etc have been called.

- Discarded: selenium + phantomjs
where extremely slow

- Superseeded: headless chrome
Was bleeding edge when we started doing this. Aside that all screenshots are named screenshot.png it worked
pretty well: easy, and chrome handles dozens of connection problems, TLS issues and whatnot. Therefore this
was the way to go.

- Chosen: headless firefox

Headless Firefox is now the default. It's faster mainly and writes directly to the correct directory. Still can have
only one of them running at a time. It creates about 16 screenshots a minute. 1250 minutes for 20000 screenshots.
= 20 hours. So in a day you've got everything.

FireFox requires a user.js file to be in the profile. This user file contains a series of variables that will be used
when starting firefox. On Mac the profile is at:
/Users/elger/Library/Application\ Support/Firefox/Profiles/8ygqcbcw.default/

"""

import logging
import os
import platform
import re
import subprocess
from datetime import datetime, timedelta

import pytz
from celery import Task, group
from django.conf import settings
from django.db.models import Q
from PIL import Image

from failmap.celery import app
from failmap.scanners.models import Endpoint, Screenshot
from failmap.scanners.scanner.scanner import (allowed_to_scan, endpoint_filters,
                                              q_configurations_to_scan)
from failmap.scanners.timeout import timeout

log = logging.getLogger(__package__)


# basically updates screenshots. It will ignore whatever parameter you throw at it as creating screenshots every day
# is a bit nonsense. It will update every month.
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    # We might not be allowed to scan for this at all.
    if not allowed_to_scan("scanner_screenshot"):
        return group()  # An empty group fits this callable's signature and does not impede celery.

    one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

    no_screenshots = Endpoint.objects.all().filter(
        q_configurations_to_scan(level="endpoint"),
        is_dead=False,
        url__not_resolvable=False,
        url__is_dead=False,
    )
    # Without screenshot OR with a screenshot over a month ago
    no_screenshots = no_screenshots.filter((Q(screenshot__isnull=True) | Q(screenshot__created_on__lt=one_month_ago)))

    # It's possible to overwrite the above query also, you can add whatever you want to the normal query.
    no_screenshots = endpoint_filters(no_screenshots, organizations_filter, urls_filter, endpoints_filter)

    # unique endpoints only
    endpoints = list(set(no_screenshots))

    log.info("Trying to make %s screenshots." % len(endpoints))
    task = group(screenshot_endpoint.si(endpoint) for endpoint in endpoints)

    return task


# only one screenshot-task per worker. And only one task per 20 seconds. You want that sequentially.
# This will enforce a minimum delay of 20 seconds between starting two tasks on the same worker instance.
# A worker instance is a host that contains multiple workers. So setting it for 20 seconds, you will only have
# a limited set of tasks running, thus no concurrency on the same worker instance.
@app.task(queue='storage', rate_limit="3/m")
def screenshot_endpoint(endpoint):
    try:
        return screenshot_with_firefox(endpoint)
    except TimeoutError:
        log.error("Screenshot timed out.")


def screenshots_of_new_urls():
    one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

    # never had a screenshot or only has screenshots older than a month
    no_screenshots = Endpoint.objects.all().filter(is_dead=False,
                                                   url__not_resolvable=False,
                                                   url__is_dead=False,
                                                   screenshot__isnull=True)
    outdated_screenshots = Endpoint.objects.all().filter(
        is_dead=False,
        url__is_dead=False,
        url__not_resolvable=False,
        screenshot__created_on__lt=one_month_ago)
    endpoints = list(no_screenshots) + list(outdated_screenshots)

    # unique endpoints only
    endpoints = list(set(endpoints))

    if len(endpoints):
        log.info("Trying to make %s screenshots." % len(endpoints))

    for endpoint in endpoints:
        screenshot_endpoint(endpoint)


# Important note for mac users:
# When you're looking at the directory (finder window with the output directory open), firefox is not able to store
# new screenshots. All screenshots will time out without error, and you'll find that running firefox yourself does make
# a screenshot. The solution is not to have the output directory open. Hours have been wasted on this.

# Firefox needs to be configured before this will work properly. Without configuration Firefox will nag you about
# starting in safe-mode when it was killed via killall. There is no command parameter (such as safe-mode) that
# counteracts this behavior. So be sure that firefox is configured properly. You can do so by:

# Add the user.js file with user settings to firefox. This can be a copy of prefs.js in your ultimate-configured firefox
# The user.js file resided in the profile directory. On the mac this directory is at:
# /Users/[USERNAME]/Library/Application\ Support/Firefox/Profiles/[RANDOM].default/prefs.js

# The settings that prevent the safe-mode nag dialog are reachable in about:config. And thus set in prefs.js after quit.
# The settings are:
# toolkit.startup.max_resumed_crashes;-1
# browser.sessionstore.max_resumed_crashes;-1

# Note that the first boot of firefox make take a while, all subsequent starts are faster.
# Firefox will eat about 200 megabytes of ram including FirefoxCP. This task will not work on common workers as they
# don't have the capacity in megabytes. The storage queue usually does have this capacity.

# todo: ignore security certificates and warnings in firefox, to create better screenshots, or have screenshots showing
# this warning.
@timeout(12, 'Took too long to make screenshot')
def screenshot_with_firefox(endpoint, skip_if_latest=False):
    if not check_installation('firefox'):
        return

    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    filename = str(re.sub(r'[^a-zA-Z0-9_]', '', str(endpoint.ip_version) + '_' + endpoint.uri_url() + now))
    filename_latest = str(re.sub(r'[^a-zA-Z0-9_]', '', str(endpoint.ip_version) + '_' + endpoint.uri_url()))
    screenshot_image = settings.TOOLS['firefox']['screenshot_output_dir'] + filename + '.png'
    screenshot_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + filename + '_small.png'
    latest_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + filename_latest + '_latest.png'

    log.debug("Filename: %s (+ _small and _latest)" % filename)
    log.debug("screenshot directory: %s" % settings.TOOLS['firefox']['screenshot_output_dir'])

    if skip_if_latest and os.path.exists(latest_thumbnail):
        log.debug("Skipped making screenshot, by request")
        return

    # have disregard of any previous firefox instanced
    log.debug("Killing other running instanced of firefox")
    process = subprocess.Popen(['killall', 'firefox'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    log.debug("Output: %s" % out)
    log.debug("Error: %s" % err)

    log.debug("Storing screenshot administration")
    save_screenshot(endpoint, screenshot_image)  # prevents the same site from being visited.

    """
    This is normal output:
    *** You are running in headless mode.
    2018-07-17 09:56:39.551 plugin-container[58976:4069143] *** CFMessagePort: bootstrap_register(): failed 1100 (0x44c)
     'Permission denied', port = 0x7643, name = 'com.apple.tsm.portname'
    See /usr/include/servers/bootstrap_defs.h for the error codes.
    2018-07-17 09:56:40.499 plugin-container[58977:4069304] *** CFMessagePort: bootstrap_register(): failed 1100 (0x44c)
     'Permission denied', port = 0x7843, name = 'com.apple.tsm.portname'
    See /usr/include/servers/bootstrap_defs.h for the error codes.
    """
    firefox = settings.TOOLS['firefox']['executable'][platform.system()]
    # '-screenshot', screenshot_image,
    command = [firefox, '-headless', '-screenshot', screenshot_image, endpoint.uri_url(),
               '--window-size=1920,1080']
    log.debug("Called command: %s" % " ".join(command))
    subprocess.call(command)

    log.debug("creating thumbnail")
    thumbnail(screenshot_image, screenshot_thumbnail)

    log.debug("creating latest thumbnail")
    # make copies of these images, so the latest are easily accessible without a db query.
    subprocess.call(['cp', screenshot_thumbnail, latest_thumbnail])

    # remove the original file to save 500kb per site, which quickly ramps up to several gigabytes
    log.debug("Removing original screenshot")
    subprocess.call(['rm', screenshot_image])


# This is a legacy function in case Firefox doesn't work properly.
# s.make_screenshot_threaded(urllist)  # doesn't work well with cd.
# Affects all threads (and the main thread) since they all belong to the same process.
# chrome headless has no option to start with a working directory...
# working with processes also results into the same sorts of troubles.
# maybe chrome shares some state for the cwd in their processes?
# as long as we can't specify the filename for chrome headless, it's not going to work.
@timeout(30, 'Took too long to make screenshot.')
def screenshot_with_chrome(endpoint, skip_if_latest=False):
    """
    Chrome headless, albeit single threaded, is pretty reliable and fast for existing urls.
    If you only visit existing domains (and have little timeouts), it results in about 20 screenshots/minute.

    Note that this is a full fledged browser: if a site contains auto-play audio, you'll hear it. :)

    Warning: killing this script might result in a chrome that is never killed.

    :param endpoint:
    :param skip_if_latest:
    :return:
    """
    if not check_installation('chrome'):
        return

    log.debug("Chrome Screenshot: %s over IPv%s" % (endpoint.uri_url(), endpoint.ip_version))

    # using a temporary dir because all screenshots will be named screenshot.png, which might result in various issues.
    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    tmp_dir = settings.TOOLS['chrome']['screenshot_output_dir'] + now

    filename = str(re.sub(r'[^a-zA-Z0-9_]', '', str(endpoint.ip_version) + '_' + endpoint.uri_url() + now))
    screenshot_image = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '.png'
    screenshot_thumbnail = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '_small.png'
    latest_thumbnail = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '_latest.png'

    log.debug("screenshot image: %s" % screenshot_image)
    log.debug("screenshot thumbnail: %s" % screenshot_thumbnail)
    log.debug("latest thumbnail: %s" % latest_thumbnail)

    # skip if there is already a latest image, just to speed things up.
    if skip_if_latest and os.path.exists(latest_thumbnail):
        log.debug("Skipped making screenshot, by request")
        return

    # Save the screenshot administration _before_ it was made.
    # The browser hangs when the site delivers downloads. Without administation this
    # script wil try again and again.
    save_screenshot(endpoint, screenshot_image)

    # since headless always creates the file "screenshot.png", just work in a
    # temporary dir:
    # chrome timeout doesn't work, it just blocks the process and hangs it.
    # so use a
    subprocess.call(['mkdir', tmp_dir])
    subprocess.call(['cd', tmp_dir])
    subprocess.call([settings.TOOLS['chrome']['executable'][platform.system()],
                     '--disable-gpu',
                     '--headless',
                     '--screenshot',
                     '--window-size=1920,3000',
                     endpoint.uri_url()])
    subprocess.call(['mv', "screenshot.png", screenshot_image])
    subprocess.call(['cd', '..'])
    subprocess.call(['rmdir', tmp_dir])

    thumbnail(screenshot_image, screenshot_thumbnail)

    # make copies of these images, so the latest are easily accessible.
    subprocess.call(['cp', screenshot_thumbnail, latest_thumbnail])


def check_installation(browser):
    try:
        browser_binary = settings.TOOLS[browser]['executable'][platform.system()]
    except KeyError:
        log.error("Not possible to read configuration setting: TOOLS[browser]['executable'][platform].")
        log.error("Platform can be Darwin, Unix. Browser can be chrome or firefox.")
        return False

    if not browser_binary:
        log.error('%s is not available for %s, please update the configuration with the correct binary.'
                  % (browser, platform.system()))
        return False

    if not os.path.exists(browser_binary):
        log.error('Supplied browser does not exist in configured path: %s' % browser_binary)
        return False

    # todo: are we able to write to disk?

    return True


def save_screenshot(endpoint, safe_filename):
    scr = Screenshot()
    scr.created_on = datetime.now(pytz.utc)
    scr.domain = endpoint.uri_url()
    scr.endpoint = endpoint
    scr.filename = safe_filename
    scr.width_pixels = 1920
    scr.height_pixels = 3000
    scr.save()


def thumbnail(image_path, output_path):
    # resizing a bit? a 320px wide version.
    im = Image.open(image_path)
    size = 320, 500
    im.thumbnail(size, Image.ANTIALIAS)
    im.save(output_path, "PNG")
