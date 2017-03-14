# This script is a migration script that cleans and molds the existing data to the new
# database schema (version 0002_augi_20170226...)
# The scanner has been rewritten to also have a lot less data.

# This is done in a more traditional way since there has been a lot changed and i'm just more
# capable in this than to read tons of migration documentation.

# this can be fit into migrations:
# https://docs.djangoproject.com/en/1.10/ref/migration-operations/

# Warning: this is a one way migration. You cannot go back after this (and there should not be
# a need to.

# faalmigratie = source database
# newdatabase = target database
# they cannot co-exist since they both use the url table.

from django.db import migrations

"""
Preparation:
First migrate to 0002_auto_20170226_2007 from scanners... then run this, then migrate.
This could be added to that old migration there... should. i think i broked it... :)


Step 1:
The only downside from this approach is that it will take the first scan result that stayed the
same. This is acceptable: we know when the first result was measured, which is more important than
the last same-result. In short: it means more when a domain has a A rating longer. And it will be
rescanned by the scanner software soon anyway. So it's fine.

The previous software recorded all scans. This resulted in 194236 scans in the database.
If your're looking on how many sequential scans had the same data (query below), you'd see
that there are 187968 records with the same endpoint and scan result information. (96.77%)
If you would omit the scan result information, it has 189632 results (97.63%).

This means that only 1664 records have changed in 9 months...

These records have been accumulated over a 9 months period of about +/-1000 domains. The choice
of reducing the dataset to only record changes has saved 99.14 percent of data in the database.
This will make sure the map queries will stay fast for YEARS and the need for static proxies is
reduced a bit. :)

This query takes about 2 to 5 minutes to run on a development machine.

SELECT count(id) FROM scans_ssllabs source WHERE
    (SELECT id FROM scans_ssllabs trash WHERE trash.id > source.id AND
                        trash.url = source.url AND
                        trash.servernaam = source.servernaam AND
                        trash.ipadres = source.ipadres AND
                        trash.rating = source.rating AND
                        trash.ratingNoTrust = source.ratingNoTrust AND
                        trash.poort = source.poort ORDER BY trash.id ASC LIMIT 1)
                        ORDER BY source.id ASC;

Before (assuming arnhem changes):
mysql> select rating FROM scans_ssllabs WHERE url = "www.arnhem.nl" LIMIT 10
    -> ;
+--------+
| rating |
+--------+
| A      |
| A      |
| A      |
| A      |
| A      |
| A      |
| A      |
| A      |
| A      |
| A      |
+--------+
10 rows in set (0.00 sec)

After:
mysql> select rating FROM scans_ssllabs WHERE url = "www.arnhem.nl" LIMIT 10;
+--------+
| rating |
+--------+
| A      |
+--------+
1 row in set (0.00 sec)

mysql> select url, rating FROM scans_ssllabs ORDER BY url LIMIT 10;
+-------------------------------+--------+
| url                           | rating |
+-------------------------------+--------+
| aaenhunze.nl                  | 0      |
| aalburg.nl                    | 0      |
| aalsmeer.notubiz.nl           | A+     |
| aalten.nl                     | 0      |
| access.alphenaandenrijn.nl    | 0      |
| access.appingedam.nl          | 0      |
| access.capelleaandenijssel.nl | T      |
| access.capelleaandenijssel.nl | 0      |
| access.capelleaandenijssel.nl | A-     |
| access.delft.nl               | 0      |
+-------------------------------+--------+
10 rows in set (0.00 sec)


"""

# first make sure to use less memory. We're not migrating the scandata to the scratchpad.
# UPDATE scans_ssllabs SET rawData = "";


# we have to work with a temporary table due to
# ERROR 1093 (HY000): You can't specify target table 'scans_ssllabs' for update in FROM clause

migrations.RunSQL("CREATE TEMPORARY TABLE faalmigratie.cleanup \
                   SELECT id FROM faalmigratie.scans_ssllabs source WHERE \
                   (SELECT id FROM faalmigratie.scans_ssllabs trash WHERE trash.id > source.id AND \
                   trash.url = source.url AND \
                   trash.servernaam = source.servernaam AND \
                   trash.ipadres = source.ipadres AND \
                   trash.rating = source.rating AND \
                   trash.ratingNoTrust = source.ratingNoTrust AND \
                   trash.poort = source.poort ORDER BY trash.id ASC LIMIT 1) \
                   ORDER BY source.id ASC;")

# The delete will take a LONG time... LOOONNNNGGG time... Delete's can't inner join.
# migrations.RunSQL("DELETE FROM scans_ssllabs WHERE id IN (select id from cleanup);")

migrations.RunSQL("CREATE INDEX blaat ON faalmigratie.scans_ssllabs (id);")
migrations.RunSQL("CREATE INDEX blaat2 ON faalmigratie.cleanup (id);")

# this also doesn't seem to speed it up. It takes over half an hour. Maybe use non-atomic queries?
# the problem was indexes. With an index it's done in 2 minutes.

migrations.RunSQL("DELETE FROM faalmigratie.scans_ssllabs WHERE id = \
                  (select id from faalmigratie.cleanup where id = faalmigratie.scans_ssllabs.id);")

# You'll see that some domains have > 40 IP addresses. Why is not 100% confirmed.
# Might be cloudcyber or anonimization extension in ipv6.
# sip.voerendaal.nl has a lot of changes over time.

# what do we do with the old / dead ip-adresses? Do they have value? The problem will remain.
# So we're not cleaning it here...

# 5: Clean up the duplicates storage
migrations.RunSQL("DROP TEMPORARY TABLE faalmigratie.cleanup;")


"""
Step 2:
Extract organizations and urls from the DB and put it in the new model.

We first have to upgrade the municipality information to the new dataset where we start this app.

There are no relations in the previous schema, so we can simply update the model.
"""
# Name changes and merges
migrations.RunSQL("UPDATE faalmigratie.URL set Organization = 'Súdwest-Fryslân' \
                   WHERE organization = 'Sudwest Fryslan';")
migrations.RunSQL("UPDATE faalmigratie.URL set Organization = 'Menameradiel' \
                   WHERE organization = 'Menaldumadeel';")
migrations.RunSQL("UPDATE faalmigratie.URL set Organization = 'Meierijstad' \
                   WHERE organization = 'Veghel';")
migrations.RunSQL("UPDATE faalmigratie.URL set Organization = 'Meierijstad' \
                   WHERE organization = 'Schijndel';")
migrations.RunSQL("UPDATE faalmigratie.URL set Organization = 'Meierijstad' \
                   WHERE organization = 'Sint-Oedenrode';")

# Now bluntly move the data to the new format
# be aware that the old database uses named foreign keys and the new database uses ID everywhere.
migrations.RunSQL("INSERT IGNORE INTO newdatabase.url \
                   (url, isdead, isdeadsince, isdeadreason, organization_id) \
                        SELECT url, isdead, IF(isdeadsince = '0000-00-00 00:00:00', NULL, \
                        isdeadsince ), isdeadreason, \
                        (SELECT id FROM newdatabase.organization ndbo \
                        WHERE ndbo.name = odbo.organization) \
                        FROM faalmigratie.url odbo;")

# both result in an empty set, while there is an warning of orgnaization_id not being null.
# it's good enough. Both have 3284 urls.
# select url FROM newdatabase.url where url NOT IN (select url from faalmigratie.url);
# select url from faalmigratie.url WHERE url NOT IN (select URL from newdatabase.url);

# we are losing the twitter information here, but that can be added in a future update as the
# data is still there.

# 3:
# Extract endpoints from the scans, there is no relation between endpoint and url (yet)
# its pretty easy, IGNORE to ignore any duplicate key errors
# There are about 6268 records, but that contains duplicates since there can be more ratings
# therefore do a shoddy "DISTINCT"
# This delivers 1 warnings:
# Incorrect datetime value: '0000-00-00 00:00:00' for column 'isdeadsince' at row 1
migrations.RunSQL("INSERT IGNORE INTO newdatabase.scanners_endpoint (domain, server_name, ip, \
                   port, protocol, is_dead, is_dead_since, is_dead_reason) \
                   SELECT DISTINCT url, servernaam, ipadres, poort, 'https', isdead, \
                   IF(isdeadsince = '0000-00-00 00:00:00', NULL, isdeadsince ) \
                   , isdeadreason FROM faalmigratie.scans_ssllabs;")

# 4:
# Migrate the scan results to the django model.
# In the old software an endpoint was also identified by is_dead and servernaam. We've changed
# those requirements in the new version: is_dead is still relevant, but servernaam is just a nice
# label. This is stored since we get it, but it's not used yet. There might be vulnerabilities
# discovered using this name. For now its here just because of A E S T H E T I C S
# This delivers 1 warning:  Field 'pending_since' doesn't have a default value
migrations.RunSQL("INSERT IGNORE INTO newdatabase.scanner_tls_qualys ( \
                   endpoint_id, qualys_rating, qualys_rating_no_trust, pending, pending_since, \
                   scan_date, scan_time, scan_moment, rating_determined_on ) \
                   SELECT (SELECT id FROM newdatabase.scanners_endpoint \
                        WHERE \
                            domain = faalmigratie.scans_ssllabs.url \
                        AND protocol = 'https' \
                        AND port = '443' \
                        AND ip = faalmigratie.scans_ssllabs.ipadres \
                        AND server_name = faalmigratie.scans_ssllabs.servernaam \
                        AND is_dead = faalmigratie.scans_ssllabs.isdead), \
                   rating, ratingnotrust, 0, NULL, DATE(scanmoment), TIME(scanmoment), \
                   scanmoment, scanmoment \
                   from faalmigratie.scans_ssllabs;")
