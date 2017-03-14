from dal import autocomplete
from django import forms

from failmap_admin.organizations.models import Url


# Dit moet een lijst worden uit de Urls die we al hebben.
# Het is een autocomplete en een scan button. Er moet een link bij naar de admin.
# Dit zou een actie kunnen zijn in de admin, maar flatpages staan dit niet toe.
# of wel? wss niet.


class QualysScanForm(forms.ModelForm):
    url = forms.ModelChoiceField(
        queryset=Url.objects.all(),
        widget=autocomplete.ModelSelect2(url='url-autocomplete')
    )

    class Meta:
        fields = ('url', )
        model = Url
