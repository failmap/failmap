import logging
from datetime import datetime, timedelta
from random import choice

import pytz
import tldextract
from constance import config
from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.forms import ValidationError
from django.utils.text import slugify

from failmap.organizations.models import Url
from failmap.pro.models import Account, ProUser, UrlList
from failmap.pro.urllist_report_historically import rate_urllist_on_moment

log = logging.getLogger(__package__)


class MailSignupForm(forms.Form):
    """
    The goal of the mailsignup form is to instantly setup an account, password and matching urls if that doesn't
    exist yet. This makes for the smoothest experience. Users should be able to invite collegues and others via
    another process in the system.

    The security of the account is as good as the security to the inbox, possibly with second factor in the future.

    This also implies that the organization isn't handing out emails to anyone who asks. (perhaps only support this for
    the first signup?)
    """
    field_order = ('email', )

    email_address = forms.EmailField(required=True)

    @transaction.atomic
    def save(self):

        email = self.cleaned_data.get('email_address', None)
        if not email:
            raise ValidationError('No e-mail supplied.')

        if not account_by_mail_exists(email) and account_by_mail_is_possible(email):
            create_account_with_email(email)
        else:
            # what should we do otherwise? Call to verify and attach to an account? Try to match to an existing account?
            # create and empty account in worst case, and let the user add some urls they want?
            raise NotImplementedError


def account_by_mail_exists(email):
    """
    On the base of an e-mail address, sees if an account is available that manages specifically the urls matching
    the mail address.

    user@moerdijk.nl will deliver a moerdijk.nl account with all moerdijk.nl urls.

    :return:
    """

    extract = tldextract.extract(email)

    return Account.objects.all().filter(name=extract.domain).exists()


def account_by_mail_is_possible(email):
    """
    :param email:
    :return:
    """
    extract = tldextract.extract(email)

    # here are some strategies, and the chosen strategy:

    # See if there is a map organization that has the same name. which will not work as you often spell things diffrent
    # Organization.objects.all().filter(name__iexact=extract.domain)

    # Select the organization that uses the same domain in their urls, and has most of them.
    # this is also not a working strategy, as it is complex and might change often. This will require a lot of work
    # for little benefit.

    # we can however simply check if it's worthwhile to create an account because there are matching domains?
    # and perhaps later we can determine if there is a failmap organization, but thats mostly manual labor anyway.
    return Url.objects.all().filter(computed_domain__iexact=extract.domain).exists()


@transaction.atomic
def create_account_with_email(email):
    extract = tldextract.extract(email)

    # create account
    account = Account()
    account.name = extract.domain.capitalize()
    account.save()

    # receive credits so the account can do a few things
    account.receive_credits(250, "Automatic signup.")

    # create a new user that will be associated to this account
    password = ''.join(choice("ACDEFGHKLMNPRSTUVWXZ234567") for i in range(20))
    password = "%s-%s-%s-%s-%s" % (password[0:4], password[4:8], password[8:12], password[12:16], password[16:20])

    # usernames might already exist, try a username with the domain. Just increment.
    first_part_username = slugify(email.split("@")[0], allow_unicode=True)
    if not first_part_username:
        first_part_username = "new_user"

    username = "%s_%s" % (first_part_username, extract.domain.lower())

    user_number = User.objects.all().filter(username__contains=username).count()

    if user_number > 3:
        raise ValidationError("There are too many users with this username.")

    if user_number:
        username = "%s_%s" % (username, user_number)

    user = User.objects.create_user(username=username,
                                    # can log into other things
                                    is_active=True,
                                    # No access to admin interface needed
                                    is_staff=False,
                                    # No permissions needed anywhere
                                    is_superuser=False,
                                    password=password)
    user.save()

    # associate the user with the account
    prouser = ProUser()
    prouser.user = user
    prouser.account = account
    prouser.notes = "Automatically generated user during email signup."
    prouser.save()

    # create an urllist using the domain of the email to fill the account.
    urllist = UrlList()
    urllist.name = extract.domain.capitalize()
    urllist.account = account
    urllist.save()

    # add urls from this domain to the account
    urls = Url.objects.all().filter(computed_domain__iexact=extract.domain)
    urllist.urls.add(*urls)

    # create a few reports so there are some stats in the timeline
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=300))
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=200))
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=100))
    # If they're already working on it, there should be changes visible.
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=14))
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=7))
    rate_urllist_on_moment(urllist, datetime.now(pytz.utc) - timedelta(days=0))

    # send an email to the mail address with the password, this confirms the mail address.
    # rate limiting etc is needed here. User can just generate a new account to receive a new password, without limit.
    # todo: rate limit creation of users.
    send_password_mail(email, username, password)


# todo: pro is enabled setting.
# todo: pro team reply to mail address setting.
# todo: captcha https://github.com/kbytesys/django-recaptcha3
def send_password_mail(email: str, username: str, password: str):
    """
    We're not using the django shorthands for sending mail, as we want the mail settings to come from constance.
    This makes configuration and deployment easier, as you don't have to set environment variables (which is pain) or
    change the source code of this application through settings.py (which is a design choice i don't like).

    Additionally this also allows BCC sending.

    :return:
    """
    from django.core import mail

    message = """Hi %(username)s,

Somebody, probably you, registered an account on this e-mail address on %(project_name)s Pro. If this wasn't you, then
you're in luck, as you can now use this account :). If this was you, you're also in luck because you can not log in!

If you go to the below you can log in with the following credentials:
Website: %(website)s
Username: %(username)s
Password: %(password)s

Kind regards,
The %(project_name)s Pro team


""" % {
        'username': username,
        'password': password,
        'project_name': config.PROJECT_NAME,
        'website': config.PROJECT_WEBSITE
    }

    mail_configuration = get_mail_configuration()
    with mail.get_connection(**mail_configuration) as connection:
        mail.EmailMessage(
            "Your new password for %s Pro" % config.PROJECT_NAME, message, config.PRO_REPLY_TO_MAIL_ADDRESS, [email],
            connection=connection,
        ).send()


def get_mail_configuration():

    # warning: settings touch database each time when accessed
    configuration = {
        'host': config.PRO_EMAIL_HOST,
        'port': config.PRO_EMAIL_PORT,
        'username': config.PRO_EMAIL_USERNAME,
        'password': config.PRO_EMAIL_PASSWORD,
        # https://docs.djangoproject.com/en/2.1/ref/settings/#email-use-tls
        'use_tls': config.PRO_EMAIL_USE_TLS,
        'use_ssl': config.PRO_EMAIL_USE_SSL,

        # should these be in the config, just like other certs?
        # https://docs.djangoproject.com/en/2.1/ref/settings/#std:setting-EMAIL_SSL_KEYFILE
        'ssl_keyfile': config.PRO_EMAIL_SSL_KEYFILE,
        # https://docs.djangoproject.com/en/2.1/ref/settings/#email-ssl-certfile
        'ssl_certfile': config.PRO_EMAIL_SSL_CERTFILE
    }

    return configuration
