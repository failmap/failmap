from datetime import date, datetime

from freezegun import freeze_time

from websecmap.map.logic.map_defaults import determine_when


def test_determine_when():

    with freeze_time("2021-02-03 13:37:42"):

        # make sure freeze time supports time
        assert datetime.now().hour == 13

        # at today means at any moment today, so the maximum amount of time in this day will be returned
        assert determine_when(days_back=0, at_date=None) == datetime(2021, 2, 3, 23, 59, 59, 999999)

        # now the same for yesterday:
        assert determine_when(days_back=1, at_date=None) == datetime(2021, 2, 2, 23, 59, 59, 999999)

        # and 40 days back should not be an issue, it goes into past year:
        assert determine_when(days_back=40, at_date=None) == datetime(2020, 12, 25, 23, 59, 59, 999999)

        # now test that we're at a certain point in time for time traveling:
        assert determine_when(days_back=0, at_date=date(2020, 5, 5)) == datetime(2020, 5, 5, 23, 59, 59, 999999)

        # and 40 days back in the past
        assert determine_when(days_back=40, at_date=date(2020, 5, 5)) == datetime(2020, 3, 26, 23, 59, 59, 999999)
