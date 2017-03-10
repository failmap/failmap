from dal import autocomplete
from django.http import HttpResponseRedirect
from django.shortcuts import render

from failmap_admin.organizations.models import Url

from .forms import QualysScanForm
from .scanner_tls_qualys import ScannerTlsQualys


def index(request):
    # now return the rendered template

    if request.method == "POST":
        form = QualysScanForm(request.POST)
        if form.is_valid():
            u = Url.objects.get(id=form.data.get('url'))
            s = ScannerTlsQualys()
            s.scan([u.url])
            return HttpResponseRedirect("/")

    else:
        form = QualysScanForm
        return render(request, 'index.html', {'form': form})


class UrlAutocomplete(autocomplete.Select2QuerySetView):

    def get_queryset(self):
        qs = Url.objects.all()

        if self.q:
            qs = qs.filter(url__istartswith=self.q)

        return qs
