from django.test import TestCase

from websecmap.api.logic import get_map_configuration


class ApiTest(TestCase):
    # https://stackoverflow.com/questions/2470634/loading-fixtures-in-django-unit-tests

    fixtures = ["development_scandata.json"]

    def test_SIDN_data(self):

        mapconfigs = get_map_configuration()
        assert len(mapconfigs) == 1

        # domains = get_2ndlevel_domains('NL', 'municipality')
        # assert len(domains) == 783
        # assert "arnhem.nl" in domains

        """
        csv_data = ,2ndlevel,qname,distinct_asns
123,arnhem.nl.,*.arnhem.nl.,1
124,arnhem.nl.,01.arnhem.nl.,1
163,arnhem.nl.,01daf671c183434584727ff1c0c29af1.arnhem.nl.,1
125,arnhem.nl.,03.arnhem.nl.,1
158,arnhem.nl.,04www.arnhem.nl.,1
632,arnhem.nl.,0dad9a9d41934e82827cfb38ab233b6d.arnhem.nl.,1
23,arnhem.nl.,10.255.254.35www.arnhem.nl.,1
1122,arnhem.nl.,12.arnhem.nl.,1
324,arnhem.nl.,12afc08dce594035ac8df74f08e780f6.arnhem.nl.,1
4334,arnhem.nl.,144eed4f73574e2c91b26f30654e0995.arnhem.nl.,1
2123,arnhem.nl.,www.arnhem.nl.,1
325,arnhem.nl.,14809963d1b7.arnhem.nl.,1
        # urls_added = sidn_domain_upload(csv_data)
        # assert len(urls_added) == 10
        """
