# Translation

Failmap uses the Django translation system.

We've tried to automate most of the quirks this system has to make translations straightforward.

This tutorial assumes you've got a working installation, follow the (quickstart)[getting_started.md]

## Adding a language
A list of languages is stored in /failmap/settings.py. You can modify the LANGUAGES variable to add your language. We
prefer that you use the 2-letter ISO country codes where possible, but we already break from that with some languages.

To change failmap to the language you're working on, set the LANGUAGE_CODE to your language and run failmap.

Once your language has been added and you've changed the default language, run:

```
failmap translate
```

This will create the language files for your languages here:
* /failmap/map/locale/'iso code'/django.po
* /failmap/map/locale/'iso code'/djangojs.po

You can edit the .po files.

After you're done, run:
```
failmap translate
```
