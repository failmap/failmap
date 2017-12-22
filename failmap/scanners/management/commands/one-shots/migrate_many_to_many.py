from django.core.management.base import BaseCommand


# Only the latest ratings...
class Command(BaseCommand):
    help = 'Fill empty many to many relationship with the current values.'

    def handle(self, *args, **options):
        # urls = Url.objects.all()
        # for url in urls:
        #     url.organizations.add(url.organization)
        return
