from websecmap.app.models import Translation
from websecmap.app.translations import get_translations


def test_get_translations(db):
    tr = Translation.objects.create(language_code="en", key="key", value="value")
    tr.metadata_section.add("layer", "test")
    tr = Translation.objects.create(language_code="nl", key="sleutel", value="waarde")
    tr.metadata_section.add("layer", "test")
    tr = Translation.objects.create(language_code="si", key="යතුර", value="අගය")
    tr.metadata_section.add("layer", "test")
    tr = Translation.objects.create(language_code="en", key="alpha", value="beta")
    tr.metadata_section.add("test")
    tr = Translation.objects.create(language_code="nl", key="alfa", value="beta")
    tr.metadata_section.add("test")
    tr = Translation.objects.create(language_code="si", key="ඇල්ෆා", value="බීටා")
    tr.metadata_section.add("test")

    # no section, will not be returned:
    Translation.objects.create(language_code="en", key="no_section", value="not_visible")

    assert Translation.objects.count() == 7

    translations = get_translations()

    assert translations == {
        "en": {
            "layer": {
                "key": "value",
            },
            "test": {
                "key": "value",
                "alpha": "beta",
            },
        },
        "nl": {
            "layer": {
                "sleutel": "waarde",
            },
            "test": {
                "sleutel": "waarde",
                "alfa": "beta",
            },
        },
        "si": {
            "layer": {
                "යතුර": "අගය",
            },
            "test": {
                "යතුර": "අගය",
                "ඇල්ෆා": "බීටා",
            },
        },
    }
