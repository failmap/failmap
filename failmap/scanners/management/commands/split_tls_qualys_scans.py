import logging

from django.core.management.base import BaseCommand

from failmap.scanners.models import EndpointGenericScan, TlsQualysScan
from failmap.scanners.scanmanager.endpoint_scan_manager import EndpointScanManager

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = """Splits TLS qualys findings into two endpoint generic scans. This because when
    trust or the rating changes, the explanation of trust or the other finding is gone.

    For example:
    Scan    Trust   Quality     Explained
    1       No      A           Yes
    2       No      B           ... explanation is gone while trust is still the same.

    So we're splitting those grades into two generic scans. This is part of a bigger operation that also influences:
    [X] Scanmanager
    [X] Rebuild ratings
    [X] User interface
    [X] Views / filters, reports
    [X] Existing TLS scanner has to adjust to this
    [future] The new TLS scanner also has to adjust to this
    [X] Set the latest scan
    [ ] The manual / comply or explain tutorial
    [X] Afterwards set_is_the_latest_scan, add this to that function. (taken from existing dataset)
    [X] Translations of new findings
    [ ] Remove old TLS Qualys code after a while
    [ ] Possible other features

    The scans are currently saved as tls_qualys scans. They will be split into:
    tls_qualys_certificate_trusted
    tls_qualys_encryption_quality

    The big benefit is that those two are also individually displayed on the map and individually have explanations etc.
    Another benefit is that there is no "special" scan to work with anymore. It's just another scan in the list.
    The downside it's that it's some work. This is the first attempt to fix the issue.
    """

    def handle(self, *args, **options):

        # undo previous splits
        EndpointGenericScan.objects.all().filter(type="tls_qualys_certificate_trusted").delete()
        EndpointGenericScan.objects.all().filter(type="tls_qualys_encryption_quality").delete()

        scans = TlsQualysScan.objects.all().order_by("id")
        nr_of_scans = scans.last().id  # count doesn't work as the number of id's is higher than the count.

        print_progress_bar(0, nr_of_scans, prefix='Progress:', suffix='Complete', length=50)

        for scan in TlsQualysScan.objects.all().order_by("id"):
            # log.debug(scan.pk)

            # skip outdated nonsense scans:
            if scan.qualys_rating in ["0", 0] or scan.qualys_rating_no_trust in ["0", 0]:
                continue

            # todo: add better motivation why something is not trusted, qualys returns a message for this.
            if scan.qualys_rating == "T":
                trust = "not trusted"
            else:
                trust = "trusted"

            EndpointScanManager.add_historic_scan(
                scan_type="tls_qualys_certificate_trusted", endpoint=scan.endpoint, rating=trust, message="",
                evidence="", rating_determined_on=scan.rating_determined_on, last_scan_moment=scan.last_scan_moment,
                is_latest=scan.is_the_latest_scan)

            EndpointScanManager.add_historic_scan(
                scan_type="tls_qualys_encryption_quality", endpoint=scan.endpoint, rating=scan.qualys_rating_no_trust,
                message="", evidence="", rating_determined_on=scan.rating_determined_on,
                last_scan_moment=scan.last_scan_moment, is_latest=scan.is_the_latest_scan)

            print_progress_bar(scan.pk, nr_of_scans, prefix='Progress:', suffix='Complete', length=50)


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█'):
    """
    @thanks https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console

    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end='\r')
    # Print New Line on Complete
    if iteration == total:
        print()
