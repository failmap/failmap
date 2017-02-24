# http://jet.readthedocs.io/en/latest/dashboard_custom_module.html
# needs: http://jet.readthedocs.io/en/latest/dashboard_custom_module.html#inherit-dashboard-module
# https://github.com/john-kurkowski/tldextract
# https://www.dabapps.com/blog/higher-level-query-api-django-orm/
# https://docs.djangoproject.com/en/1.10/intro/overview/#enjoy-the-free-api
# https://docs.djangoproject.com/en/1.10/topics/db/queries/

from jet.dashboard.modules import DashboardModule
from failmap_admin.organizations.models import Url
import tldextract
from django import forms


# todo: evaluate if we should clean domains after importing,
# i think not: now it's easy to see what the last action was, even after reloading and over time

# works only on edit, ok... fine, then we're abusing that.
class SmartAddUrlForm(forms.Form):
    newUrls = forms.CharField(label='URL Input', widget=forms.Textarea(), required=False,
                              help_text="Use one line per domain. Empty lines are fine.")


# A helping class to nicely display results on the module output.
class SmartAddUrlResult:

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

    addresult = []

    def load_settings(self, settings):
        self.newUrls = settings.get('newUrls')
        self.add(self.newUrls)

    def settings_dict(self):
        return {
            'newUrls': self.newUrls,
        }

    def init_with_context(self, context):
        self.children = self.addresult  # todo: make sure the results are added here

    def add(self, urls):

        self.addresult = []

        if urls is None:
            self.addresult.append(SmartAddUrlResult('-', 1, 'No url was added ever via this module.'))
            return False

        lines = urls.split('\n')

        # We're expecting the most ridiculous crap, which hopefully gets filtered by tldextract
        # Checked: tldextract removed queries, usernames, passwords, protocols, ports, etc.
        # It seems this has no problems with xss, but what about unicode (international names?) (with db)
        for line in lines:

            # ExtractResult(subdomain='forums.news', domain='cnn', suffix='com')
            # todo: remove the xss problems by filtering input (on what?)
            xtrct = tldextract.extract(line)
            domainandtld = xtrct.domain + '.' + xtrct.suffix
            completedomain = xtrct.subdomain + '.' + xtrct.domain + '.' + xtrct.suffix

            if xtrct.domain == "":
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'No domain entered.'))
                continue

            if xtrct.subdomain == "":
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'Can\'t determine what organisation a '
                                                                           'domain belongs to without a subdomain.'))
                continue

            if xtrct.subdomain == "" and xtrct.suffix == "":
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'Can\'t determine organization by IP or '
                                                                           'unknown top level domain.'))
                continue

            if not Url.objects.filter(url=domainandtld).exists():
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'Can\'t determine the organization if there '
                                                                           'is no organization that uses this domain.'))
                continue

            if Url.objects.filter(url=domainandtld).count() > 1:
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'Can\'t determine the organization if there '
                                                                           'are more organizations that use the same '
                                                                           'domain.'))
                continue

            if Url.objects.filter(url=completedomain).count() > 0:
                self.addresult.append(SmartAddUrlResult(completedomain, 1, 'This domain is already in the database.'))
                continue

            # looks legit, let's add it.

            # todo: things can still go wrong here, database errors and such.
            # There are a lot of silent errors (the module just stops) when you're not working
            # correctly with querysets inside this module. So errors will in most cases be
            # silent. Fortunately the manual hints a GET which is really easy to work with.
            # the pprint(vars( of the queryset didn't give a hint how to get the first/only object.
            o = Url.objects.get(url=domainandtld)  # should always be one, domain and organization are unique together.
            newurl = Url(organization_id=o.organization_id, url=completedomain)
            newurl.save()

            self.addresult.append(SmartAddUrlResult(completedomain, 0, 'Domain Added'))
