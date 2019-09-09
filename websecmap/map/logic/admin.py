
from typing import Dict

from django.utils import timezone

from websecmap.organizations.models import Organization, Url


def operation_response(error: bool = False, success: bool = False, message: str = "", data: Dict = None):
    return {'error': error,
            'success': success,
            'message': message,
            'state': "error" if error else "success",
            'data': data,
            'timestamp': timezone.now()
            }


def add_urls(organization_id, urls: str):
    # todo: how does it behave with urls with protocol?

    # urls is basically garbage input on multiple lines with spaces and comma's and all kinds of unicode.
    # here we try to break up this garbage into small pieces text, some are a url, some are garbage...
    urls = urls.replace(",", " ")
    urls = urls.replace("\n", " ")
    urls = urls.split(" ")
    urls = [u.strip() for u in urls]

    not_valid = []
    valid = []
    for url in urls:
        if not Url.is_valid_url(url):
            not_valid.append(url)
        else:
            valid.append(url)

    if not Organization.objects.all().filter(id=organization_id).exists():
        return operation_response(error=True, message='Organization could not be found.')

    if not valid:
        return operation_response(error=True, message='No valid url found.')

    organization = Organization.objects.all().filter(id=organization_id).first()
    for url in valid:
        organization.add_url(url)

    if not_valid:
        return operation_response(
            success=True,
            message=f'{len(valid)} urls have been added.',
            data={'invalid_domains': not_valid}
        )
    else:
        return operation_response(success=True, message=f'{len(valid)} urls have been added.')
