from datetime import datetime

import pytz

from websecmap.map.report import reduce_to_days


def test_reduce_to_days():

    dates = [
        datetime(2020, 1, 1, 20, 0, 0),
        datetime(2020, 1, 1, 21, 0, 0),
        datetime(2020, 1, 1, 22, 0, 0),
        datetime(2020, 1, 2, 23, 0, 0),
        datetime(2020, 1, 2, 0, 0, 0),
        datetime(2020, 1, 2, 1, 0, 0),
    ]

    new_dates = reduce_to_days(dates)

    assert sorted(new_dates) == sorted([datetime(2020, 1, 1, tzinfo=pytz.utc), datetime(2020, 1, 2, tzinfo=pytz.utc)])

    # empty should result empty
    new_dates = reduce_to_days([])
    assert new_dates == []
