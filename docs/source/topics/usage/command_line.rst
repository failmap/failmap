.. highlight:: bash

======================
Command Line Interface
======================

When failmap is installed, the failmap command is available to perform all kinds of scans and other (more developer oriented)
tasks on the command line.

Note that in general you don't need to use the command line as scans and configurations are all available in the admin interface. But
for those who want to dig deeper this guide might be of use.

.. code-block:: bash

    elger@stitchbook /A/X/x/h/f/a/docs> failmap

    Type 'failmap help <subcommand>' for help on a specific subcommand.

    Available subcommands:
    ...
    [map]
        import_coordinates
        rebuild_ratings

    [organizations]
        create_dataset
        docs
        load_dataset

    [scanners]
        check_network
        discover
        scan

A lot more commands are available, mostly for development purposes. You can play around with the risk of deleting or
corrupting your installation or database. Caution is advised. Please check the help and or the source of the other commands
before trying.


Scanning
--------
Performing scans with failmap is pretty easy. I'll explain the following command, so you can play with it yourself.

Examples:

Distributed dnssec scan on a specific url:

.. code-block:: bash
   

   failmap scan dnssec -u arnhem.nl -m async


Local header scan on a specific organization:

.. code-block:: bash
   

   failmap scan headers -o Arnhem


Local ftp scan on all organizations:

.. code-block:: bash
   

   failmap scan ftp

If you need to debug scan permissions and configurations, you can do so using:

.. code-block:: bash
   

   failmap scan debug -u arnhem.nl

Which results in a report showing what endpoints / urls will be scanned. This might be helpful when debugging:

.. code-block:: bash

    2018-09-17 13:33	INFO     - Database settings: django.db.backends.sqlite3, db.sqlite3, ,
    2018-09-17 13:33	INFO     - Debug info for scanners:
    2018-09-17 13:33	INFO     -
    2018-09-17 13:33	INFO     - Scan permissions:
    2018-09-17 13:33	INFO     - Can be adjusted in the admin interface at Configuration
    2018-09-17 13:33	INFO     - SCAN_AT_ALL                   : True
    2018-09-17 13:33	INFO     - SCAN_DNS_DNSSEC               : True
    2018-09-17 13:33	INFO     - SCAN_FTP                      : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_HEADERS_HSTS        : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_HEADERS_XFO         : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_HEADERS_X_CONTENT   : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_HEADERS_X_XSS       : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_MISSING_TLS         : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_TLS_OSAFT           : True
    2018-09-17 13:33	INFO     - SCAN_HTTP_TLS_QUALYS          : True
    2018-09-17 13:33	INFO     -
    2018-09-17 13:33	INFO     - Scan configurations (regions set allowed to be scanned)
    2018-09-17 13:33	INFO     - Can be adjusted in the admin interface at __MAP__ Configuration
    2018-09-17 13:33	INFO     - Empty means nothing will be scanned (basically exceptions)
    2018-09-17 13:33	INFO     - Organizations: (OR: (AND: ), (AND: ('country', 'NL'), ('type', 1)))
    2018-09-17 13:33	INFO     - Urls: (OR: (AND: ), (AND: ('organization__country', 'NL'), ('organization__type', 1)))
    2018-09-17 13:33	INFO     - Endpoints: (OR: (AND: ), (AND: ('url__organization__country', 'NL'), ('url__organization__type', 1)))
    2018-09-17 13:33	INFO     -
    2018-09-17 13:33	INFO     - Endpoints that are selected based on parameters:
    2018-09-17 13:33	INFO     - Other filters may apply depending on selected scanner. For example: scan ftp only selects ftp endpoints
    2018-09-17 13:33	INFO     - NL  Arnhem               arnhem.nl                     : IPv4 https/443
    2018-09-17 13:33	INFO     - NL  Arnhem               arnhem.nl                     : IPv4 http/80
    2018-09-17 13:33	INFO     - NL  Arnhem               arnhem.nl                     : IPv4 http/80
    2018-09-17 13:33	INFO     - NL  Arnhem               arnhem.nl                     : IPv4 https/443
    2018-09-17 13:33	INFO     -
    2018-09-17 13:33	INFO     - End of scan debug
    2018-09-17 13:33	INFO     -
    2018-09-17 13:33	INFO     - Executing task directly.



To find the complete syntax of the scan command:

.. code-block:: bash
   

   failmap help scan

Which results in:

.. code-block:: bash

    usage: failmap scan [-h] [--version] [-v {0,1,2,3}] [--settings SETTINGS]
                        [--pythonpath PYTHONPATH] [--traceback] [--no-color]
                        [-m {direct,sync,async}] [-i INTERVAL]
                        [-t TASK_ID | -o [ORGANIZATION_NAMES [ORGANIZATION_NAMES ...]]
                        | -u [URL_ADDRESSES [URL_ADDRESSES ...]]]
                        {dnssec,headers,plain,endpoints,tls,tlsq,ftp,screenshot,onboard,dummy,debug}

    Can perform a host of scans. Run like: failmap scan [scanner_name] and then
    options.

    positional arguments:
      {dnssec,headers,plain,endpoints,tls,tlsq,ftp,screenshot,onboard,dummy}
                            The scanner you want to use.

    optional arguments:
      -h, --help            show this help message and exit
      --version             show program's version number and exit
      -v {0,1,2,3}, --verbosity {0,1,2,3}
                            Verbosity level; 0=minimal output, 1=normal output,
                            2=verbose output, 3=very verbose output
      --settings SETTINGS   The Python path to a settings module, e.g.
                            "myproject.settings.main". If this isn't provided, the
                            DJANGO_SETTINGS_MODULE environment variable will be
                            used.
      --pythonpath PYTHONPATH
                            A directory to add to the Python path, e.g.
                            "/home/djangoprojects/myproject".
      --traceback           Raise on CommandError exceptions
      --no-color            Don't colorize the command output.
      -m {direct,sync,async}, --method {direct,sync,async}
                            Execute the task directly or on remote workers.
      -i INTERVAL, --interval INTERVAL
                            Interval between status reports (sync only).
      -t TASK_ID, --task_id TASK_ID
                            Report status for task ID and return result (if
                            available).
      -o [ORGANIZATION_NAMES [ORGANIZATION_NAMES ...]], --organization_names [ORGANIZATION_NAMES [ORGANIZATION_NAMES ...]]
                            Perform scans on these organizations (default is all).
      -u [URL_ADDRESSES [URL_ADDRESSES ...]], --url_addresses [URL_ADDRESSES [URL_ADDRESSES ...]]
                            Perform scans on these urls (default is all).


Reporting
---------
Reports can be updated with the following command:

.. code-block:: bash

   failmap report

This command also takes in the organization and url filters. Filtering always updates the entire organization over the entire
timespan. This means it can take a while before the command has finished.


.. code-block:: bash

   failmap report -o Arnhem

See failmap help report for more info.


Endpoint discovery and verification
-----------------------------------

.. code-block:: bash

    failmap discover http -o Texel
    failmap verify http -u www.texel.nl
    failmap verify ftp -o Apeldoorn

See failmap help verify

Subdomain discovery
-------------------
(doesn't work atm)

.. code-block:: bash

    failmap discover subdomains -o Texel


Running a development server
-----------------------------

To start a development server, that does not tamper with any data, and accepts connections from anywhere (which are then
filtered by settings.py), run:

.. code-block:: bash

   failmap devserver --no-backend --no-data 0.0.0.0:8000


Importing coordinates
---------------------

Downloads map data from Open Streetmaps (...), simplifies it and adds it to the database. In order for imports to work,
region information has to be added in the database. This is because OSM uses admin_levels for various types of regions
and these need to be translated into something sensible. An extensive set of these regions are available at a default
installation. They can also be loaded from a fixture that is included (don't know which one currently). For this command
to work you need an active internet connection.

To import Dutch municipalities, you'll run the following command:

.. code-block:: bash
   

   failmap import_coordinates --country=NL --region=municipality


This translates to admin_level 8, and all imported data is added to the database a being in NL and the OrganizationType
municipality. The list of regions that can be requested with the --list command, like so:

.. code-block:: bash
   

   failmap import_coordinates --list



.. code-block:: bash

    usage: failmap import_coordinates [-h] [--version] [-v {0,1,2,3}]
                                      [--settings SETTINGS]
                                      [--pythonpath PYTHONPATH] [--traceback]
                                      [--no-color] [--country COUNTRY]
                                      [--region REGION] [--date DATE]

    Connects to OSM and gets a set of coordinates. Example:failmap
    import_coordinates --country=SE --region=municipality --date=2018-01-01

    optional arguments:
      -h, --help            show this help message and exit
      --version             show program's version number and exit
      -v {0,1,2,3}, --verbosity {0,1,2,3}
                            Verbosity level; 0=minimal output, 1=normal output,
                            2=verbose output, 3=very verbose output
      --settings SETTINGS   The Python path to a settings module, e.g.
                            "myproject.settings.main". If this isn't provided, the
                            DJANGO_SETTINGS_MODULE environment variable will be
                            used.
      --pythonpath PYTHONPATH
                            A directory to add to the Python path, e.g.
                            "/home/djangoprojects/myproject".
      --traceback           Raise on CommandError exceptions
      --no-color            Don't colorize the command output.
      --country COUNTRY     Country code. Eg: NL, DE, EN
      --region REGION       Region: municipality, province, water\ board ...
      --date DATE           Date since when the import should be effective. -
                            format YYYY-MM-DD


Loading datasets / fixtures
---------------------------

You can load a fixture with the following command:

.. code-block:: bash
   

    failmap load_dataset dataset_24_juli_2018.json

A list of possible fixtures is in the fixtures directory of each django app. For example: /organizations/fixtures/

Loading a fixture can take a while, depending on it's size and format. Be somewhat patient.



Creating new datasets / exporting data
--------------------------------------

To create a new dataset


To create a new dataset from a production environment, take in account you're working with docker containers. As root
you can run the following command to retrieve data from the database:

.. code-block:: bash
   

   failmap create_dataset -o -> dataset_24_juli_2018.json


As with django, create dataset allows all kinds of options. Some defaults are chosen when running create_dataset over
using the django command.


.. code-block:: bash
   

    usage: failmap create_dataset [-h] [--version] [-v {0,1,2,3}]
                                  [--settings SETTINGS] [--pythonpath PYTHONPATH]
                                  [--traceback] [--no-color] [--format FORMAT]
                                  [--indent INDENT] [--database DATABASE]
                                  [-e EXCLUDE] [--natural-foreign]
                                  [--natural-primary] [-a] [--pks PRIMARY_KEYS]
                                  [-o OUTPUT]
                                  [app_label[.ModelName] [app_label[.ModelName]
                                  ...]]

    Create a near complete export for testing and migrating to another server.

    positional arguments:
      app_label[.ModelName]
                            Restricts dumped data to the specified app_label or
                            app_label.ModelName.

    optional arguments:
      -h, --help            show this help message and exit
      --version             show program's version number and exit
      -v {0,1,2,3}, --verbosity {0,1,2,3}
                            Verbosity level; 0=minimal output, 1=normal output,
                            2=verbose output, 3=very verbose output
      --settings SETTINGS   The Python path to a settings module, e.g.
                            "myproject.settings.main". If this isn't provided, the
                            DJANGO_SETTINGS_MODULE environment variable will be
                            used.
      --pythonpath PYTHONPATH
                            A directory to add to the Python path, e.g.
                            "/home/djangoprojects/myproject".
      --traceback           Raise on CommandError exceptions
      --no-color            Don't colorize the command output.
      --format FORMAT       Specifies the output serialization format for
                            fixtures.
      --indent INDENT       Specifies the indent level to use when pretty-printing
                            output.
      --database DATABASE   Nominates a specific database to dump fixtures from.
                            Defaults to the "default" database.
      -e EXCLUDE, --exclude EXCLUDE
                            An app_label or app_label.ModelName to exclude (use
                            multiple --exclude to exclude multiple apps/models).
      --natural-foreign     Use natural foreign keys if they are available.
      --natural-primary     Use natural primary keys if they are available.
      -a, --all             Use Django's base manager to dump all models stored in
                            the database, including those that would otherwise be
                            filtered or modified by a custom manager.
      --pks PRIMARY_KEYS    Only dump objects with given primary keys. Accepts a
                            comma-separated list of keys. This option only works
                            when you specify one model.
      -o OUTPUT, --output OUTPUT
                            Specifies file to which the output is written.