# FAQ for those on listed on failmap


## Why Failmap?

Many organizations (have to) transfer sensitive information over the internet. Sometimes they ask to share sensitive
information with them via forms, mail and etcetera. Anyone should be able to use internet services without worrying
their information is being altered or changed, whether unintentionally or malicious. Many responsible organizations
boast about their capability (so called "cyber") to protect.

Failmap adds an enormous amount of transparency. This is the driving force for many organizations to change / clean up
their online presence. With the launch of failmap, thousands of issues have been fixed in the Netherlands,
just because they have been made understandable and publicly accessible (naming and shaming).

We display the "base level" of security, which can be illustrative of the the quality and capability of organizations
in protecting your data. The base level are issues that are well documented and there are dozens of online web-services
that can discover these issues for years now. Might we find more severe vulnerabilities, we employ (and endorse)
Responsible Disclosure to address them: they will not ever be published (as that goes against our mission to increase
safety and trust).

The transparent, tendentious, and shaming approach has had a lot of impact in the Netherlands, where the tool has
become a must have for many municipalities. It's not all tendentious though: organizations strive to be "green" on the
map and they are given free reports on what was wrong, with pointers to public sources such as OWASP to help them
improve their services.


## What do the scores mean?

Failmap knows five colors:

- Green / Yellow: nothing that we scan is wrong
- Orange: there are some slicht issues, that need addressing
- Red: there are more severe compromises in the base level of security
- Gray: Unkown


## My organization is shown Red / Orange, now what?

Read the report on the bottom of the page to see what's wrong and how to fix it. When in doubt, read our scanning policy
to learn some specific quirks and features of our scanners.

An organization only needs one "high" issues to become red, as security is as strong as it's weakest link.


## My organization is completely green, has it won?

It's certainly an impressive feat, most of the time.

Unfortunately scanning only holds up for creating a baseline. The organization might still offer services that we
cannot (or will not) verify automatically. Such as outdated software, logic flaws and so on.


## How complete is failmap?

Failmap automatically scans the internet for subdomains of domains. This creates an enormous catalog of URL's that are
associated with organizations. However, failmap does only scan the "base level" of security and there might be many
domains of subdomains of organization we miss.

In the Netherlands, just for municipalities, we scan about 8000 endpoints daily or weekly.

We add all subdomains given to our e-mail address: info@faalkaart.nl


## What are endpoints?

A website usually has several endpoints. Every url can have a maximum of 65535 endpoints, of which usually very few are
used. Additionally there are usually two address to approach the url, but it's possible to have more. Usually we see
 an IPv4 and IPv6 address.

An average website wants to be reachable over both IPv4 and IPv6, on standard ports 80 (http) and 443 (https). This
means that an average website usually has four endpoints: 2 addresses * 2 ports/protocols.

More about this:
- IPv4: https://en.wikipedia.org/wiki/IPv4
- IPv6: https://en.wikipedia.org/wiki/Port_(computer_networking)
- Ports: https://en.wikipedia.org/wiki/Port_(computer_networking)
- Protocols: https://en.wikipedia.org/wiki/Application_layer


## The score is wrong / I've improved my stuff! Please rescan.

Rescanning for most issues happens daily, some weekly. See our scanning policy for more information.

If you think we're still reporting the wrong things, please use the "incorrect finding" button in the report to send
an e-mail to our service desk. Our service desk may be slow, but it might even result in software updates, policy
improvements and more.

Our goal is to accurately show the state of "base level" security: we're also not happy when things are displayed inaccurately.


## How to implement TLS correctly?

There are many tutorials online to do so. The Dutch Cert (Nationaal Cyber Security Centrum) has great general advice and
policies how to do so. Other governemental organizations (IBD for Dutch Municipalities for example) also provide fact
sheets and support.

The website Cipher List also shows a lot of config defaults for many services: https://cipherli.st/


## Since when did failmap start to annoy people?

March 2016 the first beta was written in PHP in a single days, for the "in het hoofd van de hacker" conference.


## Can i run my own failmap?

Yes, the source of failmap is open and can be used non-commercially.
