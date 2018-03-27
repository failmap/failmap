# User Guide
Failmap is split up into two user interfaces and several supporting administrative interfaces.

## The map website
The website is the site intended for humans. There are some controls on the website, such as the
time slider, twitter links and the possibilities to inspect organizations by clicking on them.

Using the map website should be straightforward.

## The admin website
Use the admin website to perform standard [data-operations](https://en.wikipedia.org/wiki/Create,_read,_update_and_delete),
run a series of actions on the data and read documentation of the internal workings of the failmap software.

The admin website is split up in four key parts:
1. Authentication and Authorization
This stores information about who can enter the admin interface and what they can do.

2. Map
Contains all information that is presented to normal humans.
This information is automatically filled based on the scans that have been performed over time.

3. Organizations
Lists of organizations, coordinates and internet adresses.

4. Scanners
Lists of endpoints and assorted scans on these endpoints.

All data in the scanners section of the admin interface is auto-generated. Changing data here makes no sense as it will
be overwritten by a scanner.
