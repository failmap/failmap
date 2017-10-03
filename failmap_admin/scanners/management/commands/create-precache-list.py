from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization


class Command(BaseCommand):
    help = "Creates output with all urls of this application, for precaching purposes."

    """
    6 basic urls = 6
    4 * 80 weekly urls = 320
    390 * 81 organization urls = 31590

    The url's that are slow and _really_ need precaching are the stats: 81 urls.
    """

    def handle(self, *args, **options):

        print('/')  # main website
        print('/data/stats/')
        print('/data/map/')
        print('/data/topfail/')
        print('/data/topwin/')
        print('/data/wanted/')
        print('/data/terrible_urls/')

        weeks = range(0, 99)
        for week in weeks:
            print('/data/stats/%s' % week)
            print('/data/map/%s' % week)
            print('/data/topfail/%s' % week)
            print('/data/topwin/%s' % week)
            print('/data/terrible_urls/%s' % week)

        organisations = Organization.objects.all()
        for organisation in organisations:
            print('/data/report/%s' % organisation.id)

            for week in weeks:
                print('/data/report/%s/%s' % (organisation.id, week))
