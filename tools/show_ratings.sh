#!/usr/bin/env bash

set -x

# output a sorted list of all urls id's and their respective rating

failmap-admin shell <<EOF | sort
from failmap_admin.map.models import UrlRating
print('\n'.join('{url__url}\t{rating}'.format(**x) for x in UrlRating.objects.all().values('url__url', 'rating')))
EOF


