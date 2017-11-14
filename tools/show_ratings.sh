#!/usr/bin/env bash

set -x

# output a sorted list of all urls/organizations and their respective rating

failmap-admin shell <<EOF | sort
from failmap_admin.map.models import UrlRating, OrganizationRating

# output url and ratings for urls
for urlrating in UrlRating.objects.all().values('url__url', 'rating'):
  print('{url__url}\t{rating}'.format(**urlrating))

# output name and rating for organizations
for organizationrating in OrganizationRating.objects.all().values('organization__name', 'rating'):
  print('{organization__name}\t{rating}'.format(**organizationrating))
EOF


