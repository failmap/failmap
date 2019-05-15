# Web Security Map

[![Code Climate](https://codeclimate.com/github/failmap/failmap/badges/gpa.svg)](https://codeclimate.com/github/failmap/failmap)
[![pipeline status](https://gitlab.com/internet-cleanup-foundation/web-security-map/badges/master/pipeline.svg)](https://gitlab.com/internet-cleanup-foundation/web-security-map/commits/master)
[![Test Coverage](https://codeclimate.com/github/failmap/failmap/badges/coverage.svg)](https://codeclimate.com/github/internet-cleanup-foundation/web-security-map/coverage)
[![Badges](https://img.shields.io/badge/badges-6-yellowgreen.svg)](https://shields.io)
[![Cyberveiligheid](https://img.shields.io/badge/Cyberveiligheid-97%25-yellow.svg)](https://eurocyber.nl)
[![Join the chat at https://gitter.im/internet-cleanup-foundation/Lobby](https://badges.gitter.im/internet-cleanup-foundation/Lobby.svg)](https://gitter.im/internet-cleanup-foundation/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

## Why Web Security Map

We believe privacy and information integrity are the basics of a resilient information society.

By providing unprecedented transparency on the most basic levels of information security, insight in
the quality and capability of organizations regarding their responsibilities is displayed.

Web Security Map uses the complexity of a traffic light anyone is able to determine if organizations that are responsible
for safeguarding information are doing what they are supposed to do.

It is perfectly possible to run Web Security Map software for yourself, allowing you to independently verify the
state of information security basics. All our products are open source.

## What is it

Web Security Map is an open source web application that continuously evaluates the implementation of security standards and
best practices at (governmental) organizations.

This repository contains the mapping application fo Web Security Map: the public frontend, an administrative interface and scanners.

![screenshot](docs/screenshot.png)

![screenshot](docs/admin_interface.png)

## Getting started

Keywords: quickstart, installation

### If you want a complete production setup

Then read the installation tutorial, which is significantly easier than the below development setup!

For full installation with everything and anything, check: https://gitlab.com/internet-cleanup-foundation/server/

### If you want a local test or development environment

Please follow these instructions to setup a development environment for Web Security Map:

#### Install OS specific dependencies

**macOS** via `brew`

```bash
brew install git python3 direnv docker shellcheck
```

**Debian Linux** via `apt`

```bash
apt-get install -y git python3 direnv docker.io shellcheck
```

**Redhat/CentOS Linux** via `yum`

```bash
yum install -y epel-release
yum install -y git python3 direnv docker ShellCheck
```

Or download and install each package separately:

- [make](https://www.gnu.org/software/make/) (required, pre-installed on most systems)
- [git](https://git-scm.com/downloads) (required, download and install)
- [python3](https://www.python.org/downloads/) (required, download and install, 3.6 or higher)
- [direnv](https://direnv.net/) (recommended, download and install, then follow [setup instructions](https://direnv.net/), see Direnv section below)
- [Docker](https://docs.docker.com/engine/installation/) (recommended, follow instructions to install.)
- [ShellCheck](https://github.com/koalaman/shellcheck#installing) (recommended, follow instructions to install

#### Generic install steps

In a directory of your choosing, download the software and enter the directory:

```bash
git clone --recursive https://gitlab.com/internet-cleanup-foundation/web-security-map/ && cd web-security-map/
```

Running `make` once to create a development Virtualenv and setup the App and its dependencies. Running `make` without arguments by default also runs basic checks and tests to verify project code quality.

```bash
make
```

After completing successfully Web Security Map development server is available to run:

```bash
make run
```

Now visit the [map website](http://127.0.0.1:8000/) and/or the
[admin website](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000 (credentials: admin:faalkaart).

#### Optional Steps

If your shell support tab completion you can get a complete list of supported commands by tabbing `make`:

```bash
make <tab><tab>
```

This shows the current data on the map:

```bash
make rebuild_reports
```

It is possible to start the server without redis and without (re)loading data:

```bash
make devserver args="--no-backend --no-data"
```

Give everyone an F rating!

```bash
https://www.youtube.com/watch?v=a14Y2V5zJlY
```

```bash
https://www.youtube.com/watch?v=eAwq2QV7f1k
```

## Documentation

Documentation is provided at [ReadTheDocs](http://websecmap.readthedocs.io/).

## Get involved

Internet Cleanup Foundation is open organisation run by volunteers.

- Talk to us via [gitter.im/internet-cleanup-foundation](https://gitter.im/internet-cleanup-foundation/Lobby#).
- Or using IRC: #internet-cleanup-foundation/Lobby @ irc.gitter.im (see https://irc.gitter.im for information)
- E-mail us at: [info@faalkaart.nl](mailto:info@faalkaart.nl),
- Or simply start hacking on the code, open an [Gitlab Issue](https://gitlab.com/internet-cleanup-foundation/websecmap/issues/new) or send a [Gitlab Merge Request](https://gitlab.com/internet-cleanup-foundation/websecmap.org/merge_requests/new).

## Thanks to

This project is being maintained by the [Internet Cleanup Foundation](https://internetcleanup.foundation).
Special thanks to the SIDN Fonds for believing in this method of improving privacy.

Thanks to the many authors contributing to open software.
