# Scanning policy

Failmap tries to scan with all scanners every day. This means the map shows new results on a daily basis.


## What does failmap scan?

Failmap scans the following:

Daily scans:

- Endpoint discovery (looking for new endpoints and cleaning up old ones)
- HTTP headers
- Endpoints missing encryption
- DNSSEC

Weekly scans:

- New subdomains (using various methods)
- TLS quality using Qualys SSL Labs


**Endpoint discovery**
Failmap tries to auto-discover endpoints for urls. A normal website today has about four endpoints:

- One on IPv4, port 80 that redirects to port 443. Example: http://example.com
- One on IPv4, port 443 that contains the website. Example: https://example.com
- One on IPv6, port 80 that redirects to port 443. Example: http://example.com
- One on IPv6, port 443 that contains the website. Example: https://example.com

Since it's possible to host a website on any port, failmap also scans for the existence of websites on well known
(official) alternative ports such as 8080.

The existence of an endpoint in itself is not rated. This is implicit: the more endpoints, the more risk.

**HTTP Headers**



## Special cases

Since failmap is completely automated, there are some special cases that could help improving the result.

These are:

**No HSTS header requirement when there are only encrypted endpoints available.**
Only if there are no unencrypted endpoints available on the url, the HSTS header is not required.

Many products do not use the HSTS header as they don't provide an unsecured endpoint. Those products usually also
use their own client which (should) only try to communicate securely. Forcing HSTS everywhere would require every
vendor to add a header that will be removed soon (and that does not provide additional security for it's clients).

Since it's impossible to distinguish websites from specific services running over HTTPS, we're allowing to omission
of the HSTS header when there are only secure endpoints available on the url.

The HSTS header, as HTTPS preloading are quickfixes to help migrate to a more secure internet. Eventually browsers
will not contact websites on port :80 (unencrypted) anymore. For the time being this header and possibly preloading
can help against downgrading in various scenario's.


**X-Frame Options is ignored on redirects.**

Citing: https://stackoverflow.com/questions/22077618/respect-x-frame-options-with-http-redirect
Source: https://tools.ietf.org/html/rfc7034
Thanks to: antoinet.

From the terminology used in RFC 7034,

The use of "X-Frame-Options" allows a web page from host B to declare that its content (for example, a
button, links, text, etc.) must not be displayed in a frame (<frame> or <iframe>) of another page (e.g.,
from host A). This is done by a policy declared in the HTTP header and enforced by browser implementations
as documented here.

The X-Frame-Options HTTP header field indicates a policy that specifies whether the browser should render
the transmitted resource within a <frame> or an <iframe>. Servers can declare this policy in the header of
their HTTP responses to prevent clickjacking attacks, which ensures that their content is not embedded
into other pages or frames.


Similarly, since a redirect is a flag not to render the content, the content can't be manipulated.
This also means no X-XSS-Protection or X-Content-Type-Options are needed. So just follow all redirects.





## Supported scans

| Scan                | Port(s)     | IPv Support | Protocols | Rate limit | Rotation               |
| :------------------ | :---------- | :---------- | :-------- | :--------- | :---------             |
| DNS                 | A/AAAA      | -           | DNS       | No         | Not yet automated      |
| Endpoint discovery  | Defaults    | 4           | http(s)   | No         | Per 3 days             |
| TLS (qualys)        | 443         | 4, 6        | TLS       | 1/minute   | Per 3 days             |
| Headers             | Any http(s) | 4           | http(s)   | No         | Daily                  |
| Screenshots         | Any http(s) | 4           | http(s)   | 1 thread   | Not yet automated      |
| Plain HTTPS         | Any http(s) | 4           | http(s)   | No         | Daily                  |
| DNSSEC              | -           | -           | DNS       | No         | Daily                  |


### DNS
The DNS scanner tries to find hostnames using various strategies:
- Brute force on a subdomain list (existing subdomains only)
- Looking at NSEC1 hashes
- Looking at Certificate transparency

Less popular, not fully automated, but also implemented:
- brute forcing dictionaries
- looking in search engines

### Endpoint Discovery
Tries to find HTTP(s) endpoints on standard HTTP(s) ports. A normal website currently has about four endpoints:
- IPv6 port 80, redirect to port 443
- IPv6 port 443, actual website
- IPv4 port 80, redirect to port 443
- IPv4 port 443, actual website

We store them separately as implementation mistakes might occur on any of these endpoints.

### TLS (qualys)
Runs a scan on ssllabs from Qualys and incorporates the result.

### Headers
Contacts an endpoint and verifies HTTP headers for various security settings. (HSTS etc)

### Screenshots
Uses chrome headless to contact a website and make a screenshot for it. This screenshow it displayed next to the results
in the report.

### Plain HTTPS
Checks if a website that only has a site on port 80 also has a secure equivalent. No port-80-only sites should exist.

### DNSSEC
Checks if the toplevel domain implements DNSSEC correctly. Uses the dotSE scanner which is included.

## Scheduling
Scanners are scheduled as periodic tasks in Django admin. They are disabled by default and might not all be included in
the source distribution. Creating a scan is actually easy. For example:

- General/Name: discover-endpoints
- General/Enabled: Yes
- General/Task: discover-endpoints
- Schedule/Interval: every 3 days
- Arguments/Arguments: ["failmap.scanners.scanner_http"]
- Execution Options/Queue: storage

## Manual scans

### Command line
The Scan command can help you:

```bash
failmap scan 'scanner name'
```

The message returned will tell you what scanners you can run manually. All scanners have the same set of options.

### Admin interface
It's possible to run manual scans, at the bottom of a selection.
Note that this is beta functionality and please don't do this too much as the "priority" scanning queue is not functioning.
You can try out a scan or two, some take a lot of time.

![admin_actions](scanners_scanning_and_ratings/admin_actions.png)
