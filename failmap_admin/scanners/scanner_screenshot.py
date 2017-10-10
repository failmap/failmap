# Research
# PyQt is not copy-paste installable, no pip command, little howto's, but ready code samples.
# pyside does not support newer python versions, it's not important enough to lag versions over it
# cefpython screenshot example is convoluted due to scoping, results in "illegal instruction 4"
#    when trying to run a second screenshot, even though shutdown etc have been called.
# headless chrome is the one we're using: a single command line, easy code. Worked in a few minutes
# the screenshot.png of headless chrome is always placed in the current working directory:
# meaning: if there are multiple threads, all screenshots are dumped in 1 directory, instead of
# seperate one for every thread. So multithreaded is actually useless.
# Then we moved to selenium and phantomjs. The code had a beautiful case sensitivity troll
# phantomjs has all kinds of tls things, and is extremely slow with real / existing sites.

# chrome / firefox headless are the way to go: great render engines, fast, know to handle thousands
# of terrible situations with certificates and other unexpected things you can encounter on the web.

import logging
import os
import platform
import re
from datetime import datetime
from time import sleep

import pytz
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from PIL import Image

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint, Screenshot
from failmap_admin.scanners.timeout import timeout

logger = logging.getLogger(__package__)


# todo: wait: https://bugzilla.mozilla.org/show_bug.cgi?id=1378010, FFX 57
# todo: how to instruct the environment that there is a chrome present.
chrome = settings.TOOLS['chrome']['executable'][platform.system()]
firefox = settings.TOOLS['firefox']['executable'][platform.system()]

# deprecated
working_directory = '../map/static/images/screenshots'  # deprecated
script_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)))  # deprecated


@timeout(30, 'Took too long to make screenshot')
def screenshot_url(url):
    """
    Contains a pointer to the most accurate and fastes screenshot method.
    Will remove the hassle of chosing the right screenshot tool.
    :param url:
    :return:
    """
    endpoints = Endpoint.objects.all().filter(url=url)
    for endpoint in endpoints:
        screenshot_with_chrome(endpoint)


@timeout(30, 'Took too long to make screenshot')
def screenshot_endpoint(endpoint):
    return screenshot_with_chrome(endpoint)


# only one copy of firefox can be open at a time
# can't we keep it open?
# it's faster than chrome now, so why not use this.
# also cleaned up code.
# Firefox doesn't quit after making the screenshot.
# And you can't have multiple firefoxes open. So you need to quit it
# some way.
# filed bug:
# https://bugzilla.mozilla.org/show_bug.cgi?id=1403934
def screenshot_with_firefox(endpoint, skip_if_latest=False):
    import subprocess

    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    screenshot_image = settings.TOOLS['firefox']['screenshot_output_dir'] + \
        str(re.sub(r'[^a-zA-Z0-9_]', '', endpoint.uri_url() + now)) + '.png'
    screenshot_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + \
        str(re.sub(r'[^a-zA-Z0-9_]', '',
                   endpoint.uri_url() + now)) + '_small.png'
    latest_thumbnail = settings.TOOLS['firefox']['screenshot_output_dir'] + \
        str(re.sub(r'[^a-zA-Z0-9_]', '',
                   endpoint.uri_url() + now)) + '_latest.png'

    logger.debug("screenshot image: %s" % screenshot_image)
    logger.debug("screenshot thumbnail: %s" % screenshot_thumbnail)
    logger.debug("latest thumbnail: %s" % latest_thumbnail)

    if skip_if_latest and os.path.exists(latest_thumbnail):
        logger.debug("Skipped making screenshot, by request")
        return

    subprocess.call([firefox,
                     '-screenshot',
                     screenshot_image,
                     endpoint.uri_url(),
                     '--window-size=1920,3000',
                     ])

    save_screenshot(endpoint, screenshot_image)  # administration
    thumbnail(screenshot_image, screenshot_thumbnail)

    # make copies of these images, so the latest are easily accessible.
    subprocess.call(['cp', screenshot_thumbnail, latest_thumbnail])


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


# s.make_screenshot_threaded(urllist)  # doesn't work well with cd.
# Affects all threads (and the main thread) since they all belong to the same process.
# chrome headless has no option to start with a working directory...
# working with processes also results into the same sorts of troubles.
# maybe chrome shares some state for the cwd in their processes?
# as long as we can't specify the filename for chrome headless, it's not going to work.

# The browser will hang when the site to make a screenshot delivers a binary to download instead
# of html.

# todo: what about directories? directory = application_endpoint?
def screenshot_with_chrome(endpoint, skip_if_latest=False):
    import subprocess

    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    logger.debug("Chrome Headless : Making screenshot: %s, on %s" % (endpoint.uri_url(), now))

    safe_filename = str(re.sub(r'[^a-zA-Z0-9_]', '', endpoint.uri_url() + now)) + '.png'
    safe_filename_resized = str(re.sub(r'[^a-zA-Z0-9_]', '',
                                       endpoint.uri_url() + now)) + '_small.png'

    xd = settings.TOOLS['chrome']['screenshot_output_dir']

    tmp_dir = xd + now
    output_filepath = xd + safe_filename
    output_filepath_resized = xd + safe_filename_resized
    output_filepath_latest = xd + str(re.sub(r'[^a-zA-Z0-9_]', '',
                                             endpoint.uri_url() + "_latest")) + '.png'

    # skip if there is already a latest image, just to speed things up.
    if skip_if_latest and os.path.exists(output_filepath_latest):
        logger.debug("Skipped making screenshot, by request")
        return

    # Save the screenshot _before_ it was made.
    # why: some sites deliver binaries instead of HTML. This means chrome will hang. Without
    # any administration this will cause a loop for this site to be scanned again and again.
    # todo: save that no screenshot was made on a hang.
    save_screenshot(endpoint, output_filepath)

    # since headless always creates the file "screenshot.png", just work in a
    # temporary dir:
    # timeout doesn't work, it just blocks the process and hangs it.
    subprocess.call(['mkdir', tmp_dir])
    subprocess.call(['cd', tmp_dir])
    subprocess.call([chrome,
                     '--disable-gpu',
                     '--headless',
                     '--screenshot',
                     '--window-size=1920,3000',
                     endpoint.uri_url()])
    subprocess.call(['mv', "screenshot.png", safe_filename])
    subprocess.call(['mv', safe_filename, output_filepath])
    subprocess.call(['cd', '..'])
    subprocess.call(['rmdir', tmp_dir])

    # and some django stuff to save the things in the database
    thumbnail(output_filepath, output_filepath_resized)

    # make copies of these images, so the latest are easily accessible.
    subprocess.call(['cp', output_filepath_resized, output_filepath_latest])
    logger.info('Made screenshot of: %s' % endpoint.uri_url())


"""
# delivers transparent / empty pages all the time.
# also looks to be clogging the cybers.
def make_screenshot_phantomjs(url):
    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    print("PhantomJS: Making screenshot of %s, storing in %s" % (url, now))

    safe_filename = str(re.sub(r'[^a-zA-Z0-9_]', '', url + now)) + '.png'
    safe_filename_resized = str(re.sub(r'[^a-zA-Z0-9_]', '', url + now)) + '_small.png'
    tmp_dir = \
        script_directory + "/" + \
        working_directory + "/" + now
    output_filepath = \
        script_directory + \
        "/" + working_directory + "/" + safe_filename
    output_filepath_resized = \
        script_directory + "/" + \
        working_directory + "/" + safe_filename_resized

    from selenium import webdriver  # Import selenium web driver
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    dcap = dict(DesiredCapabilities.PHANTOMJS)
    dcap["phantomjs.page.settings.userAgent"] = ("Mozilla/5.0 (X11; Linux x86_64) "
                                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                 "Chrome/48.0.2564.116 Safari/537.36")
    dcap["phantomjs.page.settings.resourceTimeout"] = 3000

    driver = webdriver.PhantomJS(desired_capabilities=dcap,
                                 service_args=['--ignore-ssl-errors=true',
                                               '--ssl-protocol=any',
                                               '--web-security=false'])
    driver.set_window_size(1920, 3000)
    # driver.set_page_load_timeout(10)
    driver.get(url)
    driver.save_screenshot(output_filepath)
    driver.close()

    scr = Screenshot()
    scr.created_on = datetime.now(pytz.utc)
    scr.domain = url
    scr.filename = safe_filename
    scr.width_pixels = 1920
    scr.height_pixels = 3000
    try:
        # remove the protocol.
        url = url.replace("https://", "")
        url = url.replace("http://", "")
        scr.url = Url.objects.all().filter(url=url).first()
    except ObjectDoesNotExist:
        print("No URL exists for url: %s, saving without one." % url)
        pass
    scr.save()

    # resizing a bit? a 320px wide version.
    im = Image.open(output_filepath)
    size = 320, 500
    im.thumbnail(size, Image.ANTIALIAS)
    im.save(output_filepath_resized, "PNG")

def make_screenshot_selenium_firefox(url):
    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    print("PhantomJS: Making screenshot of %s, storing in %s" % (url, now))

    safe_filename = str(re.sub(r'[^a-zA-Z0-9_]', '', url + now)) + '.png'
    safe_filename_resized = str(re.sub(r'[^a-zA-Z0-9_]', '', url + now)) + '_small.png'
    tmp_dir = \
        script_directory + "/" + \
        working_directory + "/" + now
    output_filepath = \
        script_directory + "/" + \
        working_directory + "/" + safe_filename
    output_filepath_resized = \
        script_directory + "/" + \
        working_directory + "/" + \
        safe_filename_resized

    from selenium import webdriver  # Import selenium web driver
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    dcap = dict(DesiredCapabilities.FIREFOX)
    dcap["firefox.page.settings.userAgent"] = ("Mozilla/5.0 (X11; Linux x86_64) "
                                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                                               "Chrome/48.0.2564.116 Safari/537.36")
    dcap["firefox.page.settings.resourceTimeout"] = 3000

    driver = webdriver.Firefox()
    driver.set_window_size(1920, 3000)
    # driver.set_page_load_timeout(10)
    driver.get(url)
    driver.save_screenshot(output_filepath)
    driver.close()

    scr = Screenshot()
    scr.created_on = datetime.now(pytz.utc)
    scr.domain = url
    scr.filename = safe_filename
    scr.width_pixels = 1920
    scr.height_pixels = 3000
    try:
        # remove the protocol.
        url = url.replace("https://", "")
        url = url.replace("http://", "")
        scr.url = Url.objects.all().filter(url=url).first()
    except ObjectDoesNotExist:
        print("No URL exists for url: %s, saving without one." % url)
        pass
    scr.save()

    # resizing a bit? a 320px wide version.
    im = Image.open(output_filepath)
    size = 320, 500
    im.thumbnail(size, Image.ANTIALIAS)
    im.save(output_filepath_resized, "PNG")


def make_screenshot_threaded(urls):
    # Exception("This function is not yet thread safe.")
    from multiprocessing import Pool
    pool = Pool(processes=20)

    print("Making screenshots of %s urls." % len(urls))
    # making a screenshot takes max about 10 seconds, then it times out.
    for url in urls:
        print("Trying %s " % url)
        pool.apply_async(make_screenshot, [url],
                         callback=success_callback,
                         error_callback=error_callback)

        # p = Process(target=ScannerScreenshot.make_screenshot, args=(url, ))
        # p.start()
        sleep(5)
    pool.close()
    pool.join()


def success_callback(x):
    print("Success!")


def error_callback(x):
    print("Error!")
    print(x)
    print(vars(x))

"""
