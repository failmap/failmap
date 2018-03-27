# Writing a scanner
Scanners check for basic vulnerability issues on a large scale. Scanners exist for endpoints and urls.

## Basic scanning requirements
The goal is to scan things without intrusion or disruption of services. To this end make sure that your scanner
closes connections, does not burst or hammer a service and does not trigger firewalls or other protective measures.

The second goal is to show security competence. We do so by displaying the quality of the most basic security
configuration. For us there is no value in showing all places that have SQL injections: doing so would make things
worse for everyone.

Only scan basic mistakes that can easily be detected and do not create a bigger risk when publicly known. For example
do publish header scans, but do not publish SQL injections.

Document clearly why you are doing things. This is hard.

## Get Coding
Failmap is written in Python and uses (wraps) scanners that mostly already exist. See: scanners_scanning_and_ratings.

To get you started a dummy scanner is created and various implementations exist. The scanners, including the dummy, are
visible here:

```
/failmap/scanners/scanner_*.py
```

Several scanners have been implemented using this pattern. For example the DNSSEC scanner. Just copy and start
implementing the functions.

## What to do after implementation?

### Translate
Translation instructions are shown in the dummy scanner.

### Add command line feature
Add your scanner to the following file:
```python
/failmap/scanners/management/commands/scan.py
```

### Create ratings/points
Add your points algorithm here. Document very well why certain points are given.
```
/failmap/map/calculate.py
```

### Add the scanner to rating.py
This is very hard to do correctly. Please ask the more experienced developers to do this for you.

Do note that UrlGenericScans are not added to the report yet, only EndpointGenericScans.


## Advanced / optional documentation

### Need to store more information?

The Endpoint/UrlGenericScan functions store one value, a message and evidence. If this is not enough, you have to write
your own storage feature. This is done for example for TLS_Qualys, as they give two ratings: one with and without trust.

Data deduplication is very important and it's sometimes wise to only add records if there are problems detected. Follow
the pattern of EndpointGenericScan and UrlGenericScan to do so.

### Make sure it's used on the map
Failmap uses a process of "building ratings". This is a cache of all discovered findings, so the map can
quickly query the current state. Ratings are in sequential order and built frequently.

To get a rating on the map, add your scanner type to the below file at lines X, Y and Z. This is very
easy if you use EndpointGenericScan.

```
/failmap/map/rating.py
```

Then you have to determine the severity of your discovery. The choice is yours if it counts for high,
medium and low. Add your scanner to the below file:

```
/failmap/map/calculation.py
```

and implement the routine that returns a result. Note that we're phasing out the "points" field.
