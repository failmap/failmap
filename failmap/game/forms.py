from django import forms

from failmap.game.models import Team


# todo: this doesn't work yet
# don't show the secret (only in the source)
# should this be in forms.py or in admin.py?
# https://stackoverflow.com/questions/17523263/how-to-create-password-field-in-model-django
class TeamForm(forms.ModelForm):
    secret = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Team
        fields = ('name', 'secret', 'participating_in_contest', 'allowed_to_submit_things')
