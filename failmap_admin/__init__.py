# also add a return true on def check_constraints(self, table_names=None):
# it's an absolute misfeature to force integrity of the data on loaddata, while there are no
# checks on the dumpdata. Terrible. Should be made into an issue.
#
# from django.db.backends.signals import connection_created
#
#
# def activate_foreign_keys(sender, connection, **kwargs):
#     print('test')
#
#     """Enable integrity constraint with sqlite."""
#     if connection.vendor == 'sqlite':
#         cursor = connection.cursor()
#         cursor.execute('PRAGMA foreign_keys = 0;')
#
#
# connection_created.connect(activate_foreign_keys)
#
