# Scanning policy

Failmap tries to scan with all scanners every day. This means the map shows new results on a daily basis.


## What does failmap scan?

Failmap scans the following:

Daily scans:

- Endpoint discovery (looking for new endpoints and cleaning up old ones)
- HTTP headers
- Missing encryption
- DNSSEC

Weekly scans:

- New subdomains (using various methods)
- TLS quality using Qualys SSL Labs


Not all scans are published and a variety of scans will be implemented in the coming weeks.


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
The following HTTP headers are scanned:

- HTTP Strict Transport Security
Documented here:
Maximum severity: medium / orange

- X-Frame Options
Documented here:
Maximum severity: medium / orange

- X-XSS-Options:
Documented here:
Maximum severity: low / green

- X-Content-Type-Options:
Documented here:
Maximum severity: low / green

**Missing encryption**
Offering encryption is a must.

There are two sides to encryption: first it aims to make it impossible
to see what is being transmitted, second: it guarantees the integrity of the data during transport. This is also a
valuable property on public data that is often overlooked.

In discussion the confidentiality argument is often dismissed when "public" or "open" data is published. Yet, the act
of accessing this data (who, when) in itself is in itself an act that is private. Thus not providing encryption for
the "open" data means deciding to sacrifice the privacy of the user of that data.

In the case of "open" data offering both an encrypted and non-encrypted endpoint might be a solution for people and
devices that don't have access to encryption.

Maximum severity: high / red

**DNSSEC**
Documented here:
Maximum severity: -not published on the map yet-, probably orange or red.


**New subdomains**
Every week urls are scanned for new subdomains using various methods.

**Transport Layer Security (Qualys)**
Qualys offers the excellent tool SSL Labs, which does a very comprehensive scan of the TLS connection and the associated
trust. They have documented their scanning procedure here:

Maximum severity: high / red


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


## Decency
Failmap scans a lot of domains, subdomains and ulitmately endpoints. It tries to do so with minimum contact, as to
never interfere with operations.

Failmap does not publish issues that can lead to additional risk for either organizations
as for users of those websites. Any more severe issues are handled on a case by case base using responsible disclosure.


## Extra scans
Admins of failmap may choose to run any scan at any moment. For example when handling tickets or on request by the
organization (a re-scan). This doesn't happen too often.
