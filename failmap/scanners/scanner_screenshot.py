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

- Chosen: headless chrome
Was bleeding edge when we started doing this. Aside that all screenshots are named screenshot.png it worked
pretty well: easy, and chrome handles dozens of connection problems, TLS issues and whatnot. Therefore this
was the way to go.

- Runner up: headless firefox
Too bleeding edge: while you can specify a filename, it had a bug that prevented it to quit / restart.

"""

import logging
import os
import platform
import re
import subprocess
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from PIL import Image

from failmap.celery import app
from failmap.scanners.models import Endpoint, Screenshot
from failmap.scanners.timeout import timeout

logger = logging.getLogger(__package__)


@app.task
def screenshot_urls(urls):
    for url in urls:
        screenshot_url(url)


@app.task
def screenshot_url(url):
    """
    Contains a pointer to the most accurate and fastes screenshot method.
    Will remove the hassle of chosing the right screenshot tool.
    :param urls: list of url objects
    :return:
    """
    endpoints = Endpoint.objects.all().filter(url=url)
    for endpoint in endpoints:
        try:
            screenshot_with_chrome(endpoint)
        except TimeoutError:
            pass


def screenshot_endpoint(endpoint):
    try:
        return screenshot_with_chrome(endpoint)
    except TimeoutError:
        pass


def screenshots_of_new_urls():
    one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

    # never had a screenshot or only has screenshots older than a month
    no_screenshots = Endpoint.objects.all().filter(is_dead=False,
                                                   url__not_resolvable=False,
                                                   screenshot__isnull=True)
    outdated_screenshots = Endpoint.objects.all().filter(
        is_dead=False,
        url__not_resolvable=False,
        screenshot__created_on__lt=one_month_ago)
    endpoints = list(no_screenshots) + list(outdated_screenshots)

    if len(endpoints):
        logger.info("Trying to make %s screenshot!" % len(endpoints))

    for endpoint in endpoints:
        screenshot_endpoint(endpoint)


# only one copy of firefox can be open at a time
# Firefox doesn't close and show dialogs in headless: https://bugzilla.mozilla.org/show_bug.cgi?id=1403934
@timeout(30, 'Took too long to make screenshot')
def screenshot_with_firefox(endpoint, skip_if_latest=False):
    if not check_installation('firefox'):
        return

    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    filename = str(re.sub(r'[^a-zA-Z0-9_]', '', str(endpoint.ip_version) + '_' + endpoint.uri_url() + now))
    screenshot_image = settings.TOOLS['firefox']['screenshot_output_dir'] + filename + '.png'
    screenshot_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + filename + '_small.png'
    latest_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + filename + '_latest.png'

    logger.debug("screenshot image: %s" % screenshot_image)
    logger.debug("screenshot thumbnail: %s" % screenshot_thumbnail)
    logger.debug("latest thumbnail: %s" % latest_thumbnail)

    if skip_if_latest and os.path.exists(latest_thumbnail):
        logger.debug("Skipped making screenshot, by request")
        return

    subprocess.call([settings.TOOLS['firefox']['executable'][platform.system()],
                     '-screenshot',
                     screenshot_image,
                     endpoint.uri_url(),
                     '--window-size=1920,3000',
                     ])

    save_screenshot(endpoint, screenshot_image)  # administration
    thumbnail(screenshot_image, screenshot_thumbnail)

    # make copies of these images, so the latest are easily accessible.
    subprocess.call(['cp', screenshot_thumbnail, latest_thumbnail])


# s.make_screenshot_threaded(urllist)  # doesn't work well with cd.
# Affects all threads (and the main thread) since they all belong to the same process.
# chrome headless has no option to start with a working directory...
# working with processes also results into the same sorts of troubles.
# maybe chrome shares some state for the cwd in their processes?
# as long as we can't specify the filename for chrome headless, it's not going to work.
@timeout(30, 'Took too long to make screenshot')
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

    logger.debug("Chrome Screenshot: %s over IPv%s" % (endpoint.uri_url(), endpoint.ip_version))

    # using a temporary dir because all screenshots will be named screenshot.png, which might result in various issues.
    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    tmp_dir = settings.TOOLS['chrome']['screenshot_output_dir'] + now

    filename = str(re.sub(r'[^a-zA-Z0-9_]', '', str(endpoint.ip_version) + '_' + endpoint.uri_url() + now))
    screenshot_image = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '.png'
    screenshot_thumbnail = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '_small.png'
    latest_thumbnail = settings.TOOLS['chrome']['screenshot_output_dir'] + filename + '_latest.png'

    logger.debug("screenshot image: %s" % screenshot_image)
    logger.debug("screenshot thumbnail: %s" % screenshot_thumbnail)
    logger.debug("latest thumbnail: %s" % latest_thumbnail)

    # skip if there is already a latest image, just to speed things up.
    if skip_if_latest and os.path.exists(latest_thumbnail):
        logger.debug("Skipped making screenshot, by request")
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
        logger.error("Not possible to read configuration setting: TOOLS[browser]['executable'][platform].")
        logger.error("Platform can be Darwin, Unix. Browser can be chrome or firefox.")
        return False

    if not browser_binary:
        logger.error('%s is not available for %s, please update the configuration with the correct binary.'
                     % (browser, platform.system()))
        return False

    if not os.path.exists(browser_binary):
        logger.error('Supplied browser does not exist in configured path: %s' % browser_binary)
        return False

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
