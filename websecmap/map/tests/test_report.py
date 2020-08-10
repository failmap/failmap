from datetime import datetime
import random

import pytz
from freezegun import freeze_time

from websecmap.map.report import reduce_to_days, reduce_to_weeks, reduce_to_months, reduce_to_save_data


def test_reduce_to_days():

    dates = [
        datetime(2020, 1, 1, 20, 0, 0, tzinfo=pytz.utc),
        datetime(2020, 1, 1, 21, 0, 0, tzinfo=pytz.utc),
        datetime(2020, 1, 1, 22, 0, 0, tzinfo=pytz.utc),
        datetime(2020, 1, 2, 23, 0, 0, tzinfo=pytz.utc),
        datetime(2020, 1, 2, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2020, 1, 2, 1, 0, 0, tzinfo=pytz.utc),
    ]

    new_dates = reduce_to_days(dates)

    assert sorted(new_dates) == sorted([datetime(2020, 1, 1, tzinfo=pytz.utc), datetime(2020, 1, 2, tzinfo=pytz.utc)])

    # empty should result empty
    new_dates = reduce_to_days([])
    assert new_dates == []


def test_reduce_to_weeks():

    dates = [
        datetime(2019, 1, 1, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 2, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 3, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 4, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 5, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 6, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 7, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 8, 0, 0, 0, tzinfo=pytz.utc),
        datetime(2019, 1, 9, 0, 0, 0, tzinfo=pytz.utc),
    ]

    new_dates = reduce_to_weeks(dates)

    # last day of the week
    assert sorted(new_dates) == sorted([datetime(2019, 1, 7, tzinfo=pytz.utc), datetime(2019, 1, 14, tzinfo=pytz.utc)])

    new_dates = reduce_to_weeks([])
    assert new_dates == []


def test_reduce_to_months():

    # tzinfo should be kept
    dates = [
        datetime(2018, 1, 1, 20, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 1, 2, 21, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 1, 3, 22, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 1, 4, 23, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 2, 1, 20, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 2, 2, 21, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 2, 3, 22, 0, 0, tzinfo=pytz.utc),
        datetime(2018, 2, 4, 23, 0, 0, tzinfo=pytz.utc),
    ]

    new_dates = reduce_to_months(dates)

    # last day of the month, so you're sure there is data
    assert sorted(new_dates) == sorted([datetime(2018, 1, 31, tzinfo=pytz.utc), datetime(2018, 2, 28, tzinfo=pytz.utc)])

    new_dates = reduce_to_months([])
    assert new_dates == []


def test_reduce_to_save_data():
    """
    Users are generally not really interested in old data, aside from some graphs. They are fine when the
    graph is up to date, but the rest isn't. We're not going to go this far, but will reduce the amount
    of data when rebuilding ancient reports.

    < 2 years = 1 / month
    < 1 year = 1 / week
    < 0 years = 1 / day

    Dates + times over a year are reduced to 1 per week / month

    Dates + times in the last year are once per day (so the year graphs look nice)

    """

    # the cutoff depends on the actual time, so make sure the time is always the same:
    with freeze_time("2020-06-01"):

        dates = [
            # dailies this year, will reduce to
            #   [datetime(2020, 1, 1, tzinfo=pytz.utc), datetime(2020, 1, 2, tzinfo=pytz.utc)]
            # until 2019-06-01
            datetime(2020, 1, 1, 20, 0, 0, tzinfo=pytz.utc),
            datetime(2020, 1, 1, 21, 0, 0, tzinfo=pytz.utc),
            datetime(2020, 1, 1, 22, 0, 0, tzinfo=pytz.utc),
            datetime(2020, 1, 2, 23, 0, 0, tzinfo=pytz.utc),
            datetime(2020, 1, 2, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2020, 1, 2, 1, 0, 0, tzinfo=pytz.utc),

            # weeks last year:
            #  will reduce to two weeks
            # from 2018-06-01 to 2019-06-01
            datetime(2019, 1, 1, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 2, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 3, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 4, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 5, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 6, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 7, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 8, 0, 0, 0, tzinfo=pytz.utc),
            datetime(2019, 1, 9, 0, 0, 0, tzinfo=pytz.utc),

            # months two years ago and before:
            #  will reduce to two months
            # earlier than 2018-06-01
            datetime(2018, 1, 1, 20, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 1, 2, 21, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 1, 3, 22, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 1, 4, 23, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 2, 1, 20, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 2, 2, 21, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 2, 3, 22, 0, 0, tzinfo=pytz.utc),
            datetime(2018, 2, 4, 23, 0, 0, tzinfo=pytz.utc),
        ]

        # order doesn't matter:
        random.shuffle(dates)

        new_dates = reduce_to_save_data(dates)
        print(sorted(new_dates))

        assert sorted(new_dates) == sorted([
            # days
            datetime(2020, 1, 1, 23, 59, 59, 999999, tzinfo=pytz.utc),
            datetime(2020, 1, 2, 23, 59, 59, 999999, tzinfo=pytz.utc),

            # weeks
            datetime(2019, 1, 7, 23, 59, 59, 999999, tzinfo=pytz.utc),
            datetime(2019, 1, 14, 23, 59, 59, 999999, tzinfo=pytz.utc),

            # months
            datetime(2018, 1, 31, 23, 59, 59, 999999, tzinfo=pytz.utc),
            datetime(2018, 2, 28, 23, 59, 59, 999999, tzinfo=pytz.utc),
        ])

        assert reduce_to_save_data([]) == []

