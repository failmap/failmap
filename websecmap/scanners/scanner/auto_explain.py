"""
This was an idea to automatically explain a number of issues, starting with TLS Qualys scans on the sip. and
lyncdiscover. subdomains. It appears that there are a number of organizations that DO have these subdomains trusted.

I wonder WHY we should mark these specific services as trusted: it still means that another organization can read and
alter the data stream that's going over that service, which is not desirable.

It's also technically insanely hard: we don't get a reason back from Qualys why something is not trusted. This could be
many reasons such as a Comodo certificate, an expired certificate, a domain name mismatch, revocation or something else.

We can Scan for a specific set of urls, but then will have to check the issuer and the CN. If those match, it can be
set to trusted automatically, but that isn't fair towards the other organizations that did get their stuff right.

Also, automatically generating explanations lessens the involvement and risk management of the organizations.

Lastly: it may also blow up in our face, if there is a bug or if there is doubt in our systems. It will also mean more
maintenance. So a script that automatically explains is very unwise and we shouldn't start with this: we don't know
where it will end.
"""
