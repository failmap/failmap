#!/usr/bin/env sh

set -e -o pipefail

# install dnscheck

cpan Mail::RFC822::Address

cd /vendor/dnscheck/engine

perl Makefile.PL
make
make install


