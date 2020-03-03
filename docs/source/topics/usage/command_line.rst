======================
Command Line Interface
======================

The WebSecMap commandline interface allows for scanning and adding urls. It is most useful in day to day application
management as it provides swift access to scanners. Paired with using the web interface and admin pages, you'll be able
to accomplish everything quickly.


Note that the websecmap command runs the application only. There are other commands available during development, mostly
via make. This help page will not go into those.

After installing a development installation or production installation of WebSecMap, you will be able to call the
websecmap command. It will show a plethora of options and features, some of which are used for development or 'one-shot'
upgrades of older websecmap installations.

This guide will go over the most useful commands and details them a bit.

Note that many of these tasks are also automatically performed. This is done using periodic tasks. These can be
seen and enabled in the admin web interface.


.. code-block:: sh

    user@computer:~# websecmap

    Type 'websecmap help <subcommand>' for help on a specific subcommand.

    Available subcommands:

    [adminsortable2]
        reorder

    [app]
        celery
        crashtest
        devserver
        one_shot_failmap_to_websecmap
    ...


Importing map data
-------------------
To get you started with a new installation, data from open streetmaps and wikidata can be downloaded and imported.

Everything that can be imported is listed in the "AdministrativeRegion" second in the admin interface. A standard
installation of websecmap comes prepared with a large list of regions that can be imported. Do note that this list
is by no means complete, and in the admin interface you will find instructions to how to add more.

To list all regions that can be imported via the command line, use the following command:

.. code-block:: sh

    # list all regions that can be imported
    websecmap import_coordinates --list


For example, let's import all Dutch municipalities. This can be done with the following command:

.. code-block:: sh

    # import all dutch municipalities
    websecmap import_coordinates --country=NL --region=municipality

    # It's also possible to update coordinates, it will not import new organizations, only change the borders
    # websecmap update_coordinates --country=NL --region=municipality


Importing can take a while. It will download information from open streetmaps and wikidata. If you have set a OSM key
in the admin webinterface, you'll be able to download even better mapping information from a server that already has
removed larger water-bodies from the map: this is useful for coastal countries.

Next to geographical data, organization names and some first urls are automatically added as well.

After importing all regions, a report will automatically be created. After a while your local map will have a number
of gray areas on them in the shape of the Netherlands. This means your import was successful.


Adding URLs
------------

URLs are uniquely stored addresses. They can be shared amongst organizations that have been imported before. The
tooling for adding urls are limited via the command line. It is only possible to add urls to existing organizations.
The tool will guide you to add urls and find the organizations these urls should be tied to.

.. code-block:: sh

   websecmap add_urls -u url.example.com anotherurl.example.com



Discovery, verification and scanning
----------------------------------------

The real meat of the websecmap command line tools is scanning. Before we can actually scan, we need something that can
be scanned. These can be one of two things: endpoints and urls (only DNSSEC).

Both urls and endpoints can be discovered and verified, the same way a scan is called. They all share the same general
syntax that allows for somewhat flexible actions.

Let's go over the process of finding endpoints, and running a few scans on them. In our example, we use six domains:

- example.com
- subdomain.example.com
- evildoma.in
- mydomain.evildoma.in
- proc.live
- reverse.proc.live

All commands regarding scanning, discovery and verification can be run on a separate worker: a separate process that
performs these actions. A live installation will have these workers running for you. Developers may have to start a development
worker with "make run_broker" and "make run_worker". A worker is multithreaded (=faster), while local scans are single threaded.

Commands are performed locally unless specified they should be run on a worker. To run a scan on a worker, add ' -m async' to the command.


.. code-block:: sh

    # let's extend the amount of subdomains, by scanning for them:
    websecmap discover subdomains

    # let's discover HTTP endpoints for these domains:
    websecmap discover http

    # let's also discover FTP servers, locally:
    websecmap discover ftp

    # then, let's see if we can find mail endpoints suitable for internet.nl scans
    websecmap discover dns_endpoints

    # all other options are in the help of websecmap:
    # websecmap discover --help


It's possible to perform even more complex operations on all these commands. For example to discover things on a certain domain.
Here are some examples that are run on two domains, or even a wildcard:


.. code-block:: sh

    # discover http endpoints on two domains:
    websecmap discover http -u example.com evaildoma.in

    # discover ftp on a wildcard url:
    websecmap discover ftp -u *.domain.*

    # discover ftp on all urls that start with test
    websecmap discover ftp -u "test.*"


It is also possible to filter on organizations names or even entire map layer types using the -o or -y switches:


.. code-block:: sh

    # discover http endpoints on everything by Evil Corp:
    websecmap discover http -o "Evil Corp"

    # discover http on all municipalities and test layers:
    websecmap discover http -y municipality test


Scanning and verification works pretty much the same way. Verification is a way to check if the discovered items (endpoints and urls)
are still there. It is more efficient than discovering them again. Here are some examples:

.. code-block:: sh

    # Scan TLS at Qualys for all domains
    websecmap scan tlsq

    # scan FTP at evil corp:
    websecmap scan ftp -o "Evil Corp"

    # figure out all scanning options, note that for some you need access keys via the admin interface.
    websecmap scan --help

    # verify that HTTP services are still up
    websecmap verify http -u example.com


Reporting
---------

After scanning, we want to add some color to the map. We can do that using the report function. The report command
works pretty much like the discovery, scan and verify commands: it allows the same filters, which makes updating a
specific organization or url easy.

Creating a report is an extensive process and can take a while. It will rebuild all url data first, and then
will create reports on them on specific moments: every day something changed a report will be created.

In order to make the map render quickly, these reports are cached. At the end of the report process, the map and
statistics caches are updated with the latest values based on all of todays changes.

Here are some example report commands:


.. code-block:: sh

    # Create a report for everything in the system
    websecmap report

    # Create a report that only updates one organization, and only rebuilds the caches afterwards.
    websecmap report -o "Evil Corp"

    # Or create a report that only updates on url (and all bound organizations), and rebuilds the caches afterwards:
    websecmap report -u proc.live


Reports contain all issues that are enabled to be reported on. These are settings that can be altered in the admin
interface in the "Configuration" section. There are a lot of things that can be reported, the default is everything.



Development / Debugging command highlights
-------------------------------------------

These are the highlights of the command line interface. There are many other command line tools available, yet most
of these are created for development and debugging purposes.

.. code-block:: sh

    # load testdata:
    websecmap loaddata production
    websecmap loaddata development_user
    websecmap loaddata development_periodic_tasks
    websecmap loaddata development_scandata

    # export organizations, to import on a development machine:
    websecmap export_organization --organization_name Arnhem Zutphen "Evil Corp"

    # remove short endpoint outages
    websecmap clean_short_outages

    # access the django shell
    websecmap shell

    # show a timeline of all events on an url, useful for debugging reports:
    websecmap timeline -u example.com
