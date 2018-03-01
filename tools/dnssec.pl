#!/usr/bin/perl
#
# $Id$

require 5.008;
use warnings;
use strict;

use DNSCheck;

######################################################################

# configuration changes compared to examples/dnssec.pl:
# Use meaningful translated messages (localefile)
# Minimize the output: debug: 0
my $check = new DNSCheck({ interactive => 1, extras => { debug => 0 }, localefile => 'locale/en.yaml' });

die "usage: $0 zonename\n" unless ($ARGV[0]);

$check->dnssec->test($ARGV[0]);
