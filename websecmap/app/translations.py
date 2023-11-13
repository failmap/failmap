from collections import defaultdict

from websecmap.app.models import Translation


def get_translations():
    trans = defaultdict(dict)
    translations = Translation.objects.all().filter().defer("metadata_notes")

    for translation in translations:
        for section in translation.metadata_section.names():
            if section not in trans[translation.language_code]:
                trans[translation.language_code][section] = {}

            trans[translation.language_code][section][translation.key] = translation.value

    # defaultdict is not serializable
    return dict(trans)
