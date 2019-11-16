#!/bin/sh

set -e

# install dnscheck

cpan Mail::RFC822::Address

cd /vendor/dnscheck/engine

perl Makefile.PL
make
make install


