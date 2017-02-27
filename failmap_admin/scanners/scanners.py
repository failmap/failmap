"""Functional implementation of scanners."""

import random


class ThisScannerFailedException(Exception):
    pass


def blascanner(domain):
    """Implementation of the bla scanner."""

    if 'fail' in domain:
        raise ThisScannerFailedException('o noes')

    rating = random.choice(['A', 'B', 'C'])

    return {
        'rating': rating,
    }
