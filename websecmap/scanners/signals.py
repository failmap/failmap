from django.db.models.signals import post_save
from django.dispatch import receiver

from websecmap.scanners.models import Scanner, ScanType
from websecmap.scanners.scanmetadata import dump_scan_config_to_file


# @receiver(config_updated)
# def constance_updated(sender, key, old_value, new_value, **kwargs):
#     # A reboot is needed until it goes into effect. This is fragile because of a misconfig app can crash
#     dump_scan_config_to_file()

import sys

# Only when running. During testing you should not re-dump stuff to a file and polute that file
if "pytest" not in "".join(sys.argv):

    @receiver(post_save, sender=Scanner)
    def update_scanner_config(sender, instance, **kwargs):
        # Only via the admin interace, you don't want during tests that this file is overwritten(!)
        dump_scan_config_to_file()

    @receiver(post_save, sender=ScanType)
    def update_scanner_config_2(sender, instance, **kwargs):
        dump_scan_config_to_file()
