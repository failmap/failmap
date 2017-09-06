# This is going to scan DNS using well known tools.

# DNS Recon:
# The Harvester: (using an API?) - or write something yourself?

"""
Context matters, given certain subdomains will be everpresently available in certain branches.
For example, municipalities will have some CMS vendors, hospitals will have some data transfer
capabilities and so on...

So you need to check at least all subdomains that are available in your branche / category.


DNS Recon in some cases things all subdomains are valid, correctly, because there is always an
answer. So we're going to test if a few random domains exist and such.

Afterwards, we do know that a subdomain exist, but we don't know what ports give results we can
audit. We will check for TLS on 443. There are infinite possibilities.


And what do we want to check?

Version 1: just expand the domains we have. We'll see what we do with it later.
Many urls can be added by hand in the admin interface anyway.
"""


class ScannerDns:

    def scan(self, domains):

        # dnsrecon / soft approach
        # https://github.com/darkoperator/dnsrecon
        # run check if the host will accept any subdomain as valid
        # get a list of subdomains usual for the branche from the database
        # try if those subdomains exist or not, and act accordingly
        #   use the XML export feature.

        # dnsrecon / hard approach: brute force domains out of scope... with dictionaries.

        # theharvester (and such)
        # https://github.com/laramies/theHarvester
        # search for subdomains in search engine
        # extract subdomains
        # test if they exist (in some way?!)
        # add to organization (a lot will still be manual work) - googleCSE
        # given the harvester is still being developed, undestands google CSE and also
        # can brute force DNS, AND is written in python, this might be the better approach...

        # instead of writing all kinds of complex logic to deduct the correct subdomains etc, we're
        # going to make two lists that suggest subdomains for other organizations (a dictionary per
        # branche). Main reason is that humans will find a new way to have weird DNS names, typos,
        # etc... based of that we will make suggestions as to what subdomains to scan and vice versa
        # this helps preventing a list that has 99% mis.
        return
