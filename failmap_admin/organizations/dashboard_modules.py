# http://jet.readthedocs.io/en/latest/dashboard_custom_module.html
# needs: http://jet.readthedocs.io/en/latest/dashboard_custom_module.html#inherit-dashboard-module
# https://github.com/john-kurkowski/tldextract
# https://www.dabapps.com/blog/higher-level-query-api-django-orm/
# https://docs.djangoproject.com/en/1.10/intro/overview/#enjoy-the-free-api
# https://docs.djangoproject.com/en/1.10/topics/db/queries/

import tldextract
from django import forms
from jet.dashboard.modules import DashboardModule

from failmap_admin.organizations.models import Url


# Intended workings: after adding a list of domains, hitting save, you'll see
# the results of the attempt to add those domains to organizations. The results
# as well as well as the domains that have been added in the edit-modus stay there.
# this helps people to see what has been added most recently.

# This module can only manage data on it's edit form. So we're abusing that. There
# is no documented way to add modules to the jet dashboard otherwise. Also
# the Jet dashboard calls this a widget, which it just isn't :)


class SmartAddUrlForm(forms.Form):
    newUrls = forms.CharField(label='URL Input', widget=forms.Textarea(), required=False,
                              help_text="Use one line per domain. Empty lines are fine.")


# A helping class to nicely display results on the module output.
class AddResult:

    def __init__(self, domain, error, message):
        self.domain = domain
        self.error = error
        self.message = message
        return

    domain = ""
    error = ""
    message = ""


# todo: add history to action log.
class SmartAddUrl(DashboardModule):
    title = 'Smart Add Urls'
    title_url = 'Smart Add Urls'

    template = 'organizations/templates/SmartAddUrl.html'

    settings_form = SmartAddUrlForm

    newUrls = None
    addresults = []

    def load_settings(self, settings):
        self.newUrls = settings.get('newUrls')

    def settings_dict(self):
        return {
            'newUrls': self.newUrls,
        }

    def init_with_context(self, context):
        self.add(self.newUrls)
        self.children = self.addresults  # todo: make sure the results are added here

    # this is called 3 times per reload, highly inefficient. Can't really do much about it
    def add(self, urls):

        self.addresults = []  # todo: 3-times reload symptom suppression. I don't like it.

        if not urls:
            self.addresults.append(AddResult('', 1, 'No url was added ever via this module.'))
            return False

        # We're expecting the most ridiculous crap, which hopefully gets filtered by tldextract
        # Checked: tldextract removed queries, usernames, passwords, protocols, ports, etc.
        # Probably unicode is still a challenge, as it relies on underlying DB.
        for line in urls.splitlines():
            xtrct = tldextract.extract(line)

            valid_domain, add_result = self.is_valid_domain(xtrct)

            if not valid_domain:
                self.addresults.append(add_result)
            else:
                # looks legit, let's add it.

                # todo: things can still go wrong here, database errors and such.
                # There are a lot of silent errors (the module just stops) when you're not working
                # correctly with querysets inside this module. So errors will in most cases be
                # silent. Fortunately the manual hints a GET which is really easy to work with.
                # the pprint(vars( of the queryset didn't give a hint how to get
                # the first/only object.
                # are domains unique? no. Might cause issues.

                domainandtld = xtrct.domain + '.' + xtrct.suffix
                completedomain = xtrct.subdomain + '.' + xtrct.domain + '.' + xtrct.suffix

                o = Url.objects.get(url=domainandtld)
                newurl = Url(organization_id=o.organization_id, url=completedomain)
                newurl.save()

                self.addresults.append(AddResult(completedomain, 0, 'Domain Added'))

    @staticmethod
    def is_valid_domain(xtrct):

        # ExtractResult(subdomain='forums.news', domain='cnn', suffix='com')
        # Looks susceptible to xss, tested an xss wordlist on it: no problem.

        domainandtld = xtrct.domain + '.' + xtrct.suffix
        completedomain = xtrct.subdomain + '.' + xtrct.domain + '.' + xtrct.suffix

        if not xtrct.domain:
            return False, AddResult(completedomain, 1,
                                    'No domain entered.')

        if not xtrct.subdomain:
            return False, AddResult(completedomain, 1,
                                    'Can\'t determine what organisation a domain belongs to '
                                    'without a subdomain.')

        if not xtrct.subdomain and not xtrct.suffix:
            return False, AddResult(completedomain, 1,
                                    'Can\'t determine organization by IP or '
                                    'unknown top level domain.')

        if not xtrct.suffix:
            return False, AddResult(completedomain, 1,
                                    'Domain is missing a top level extension.'
                                    'such as .NL or .ORG...')

        if not Url.objects.filter(url=domainandtld).exists:
            return False, AddResult(completedomain, 1,
                                    'Can\'t determine the organization if '
                                    'there is no organization that uses this domain.')

        # this happens when two separate organizations use the same generic service provider
        # it will also result in an erroneous add with the first domain. Not much you
        # can do about it. One solution would be to check if the sub domain matches a domain.
        # and use that organization. That might work in 50% of the cases.

        # also: this test is just incorrect, it doesn't check for multiple organizations at all
        # todo: fix
        if Url.objects.filter(url=domainandtld).count() > 1:
            return False, AddResult(completedomain, 1,
                                    'Can\'t determine the organization if there are more '
                                    'organizations that use the same domain.')

        if Url.objects.filter(url=completedomain).count():
            return False, AddResult(completedomain, 1, 'This domain is already in the database.')

        if not Url.objects.filter(url=domainandtld).count():
            return False, AddResult(completedomain, 1,
                                    'The domain.tld is not in the database, so its'
                                    'impossible to determine the organization')

        return True, AddResult(completedomain, 0, 'Domain seems fine')
