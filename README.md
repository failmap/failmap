# Web Security Map

[![Code Climate](https://codeclimate.com/github/failmap/failmap/badges/gpa.svg)](https://codeclimate.com/github/failmap/failmap)
[![pipeline status](https://gitlab.com/internet-cleanup-foundation/web-security-map/badges/master/pipeline.svg)](https://gitlab.com/internet-cleanup-foundation/web-security-map/commits/master)
[![Test Coverage](https://codeclimate.com/github/failmap/failmap/badges/coverage.svg)](https://codeclimate.com/github/internet-cleanup-foundation/web-security-map/coverage)
[![Badges](https://img.shields.io/badge/badges-6-yellowgreen.svg)](https://shields.io)
[![Cyberveiligheid](https://img.shields.io/badge/Cyberveiligheid-97%25-yellow.svg)](https://eurocyber.nl)
[![Join the chat at https://gitter.im/internet-cleanup-foundation/Lobby](https://badges.gitter.im/internet-cleanup-foundation/Lobby.svg)](https://gitter.im/internet-cleanup-foundation/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

## Why Web Security Map
Use Web Security Map to create a tangible view on how well security and privacy practices are applied.

Anyone can understand this map while stakeholders are motivated to solve issues and prove their online proficiency.

Web Security Map uses data from Open Streetmaps and Wikidata, amongst other public sources of information.

## What is it

Web Security Map is an open source web application that continuously evaluates the implementation of security standards and
best practices at (governmental) organizations.

Here is a short feature overview of what you can do with Web Security Map:

![screenshot](docs/screenshot2020.png)
Above screenshot: map of Dutch Municipalities showing all possible issues together.

![screenshot](docs/screenshot2020_dots.png)
Above screenshot: map of DNSSEC issues at all Dutch government agencies. Areas and locations can be used together.


![screenshot](docs/statistics2020.png)
Above screenshot: statistics are kept over time, here statistics are shown for Dutch municipalities over a year.

![screenshot](docs/complyorexplain2020.png)
Above screenshot: it's possible to deal with exceptional situations using "comply or explain".

![screenshot](docs/report2020_1_of_3.png)
Above screenshot: reporting, part 1 of 3, showing statistics for a single organization. This is the municipality of
Amsterdam.

![screenshot](docs/report2020_2_of_3.png)
Above screenshot: reporting, part 2 of 3, showing a summary of all urls that are scanned, with all tests.

![screenshot](docs/report2020_3_of_3.png)
Above screenshot: reporting, part 3 if 3, showing a detailed report of each finding, including the possibility of a
second opinion and reading documentation.

![screenshot](docs/admin_interface2020.png)
Above screenshot: the administrative interface allows direct database access as well as configuration options.

## Installation and training videos

This repository contains the front end application for Web Security Map: the map, scanners and administrative web interface.

To run a full installation of this software, please use the below videos.

For time indexes on these videos, visit: https://monitoryourgovernment.org/

- How To: Installation: https://youtu.be/yhx0b1k_Ag0
- How To: Import Countries: https://youtu.be/esv6G8hmwpE
- Exploring the admin interface: https://youtu.be/Yjq5klYbQww
- Configuration options: https://youtu.be/LX5_lHgljxY
- Add organizations using Data sets: https://youtu.be/YvK79QGaHTY

For all server and deployment related topics, visit: https://gitlab.com/internet-cleanup-foundation/server/


The source repository you're watching right now will only get you a development setup.


## Getting started

Keywords: quickstart, installation

### If you want a complete production setup

Then read the installation tutorial, which is significantly easier than the below development setup!

For full installation with everything and anything, check: https://gitlab.com/internet-cleanup-foundation/server/

### If you want a local test or development environment

Please follow these instructions to setup a development environment for Web Security Map:

#### Install OS specific dependencies

The project uses Nix and Devenv.sh to bootstrap an isolated and reproducable development environment. Please follow the instructions on https://devenv.sh/getting-started/ to install Nix and Devenv.sh. Below is a summary of setup commands for common OS environments:


- **macOS**

```bash
sh <(curl -L https://nixos.org/nix/install)
nix-env -iA cachix -f https://cachix.org/api/v1/install
cachix use devenv
nix-env -if https://github.com/cachix/devenv/tarball/v0.4
```

- **Linux**

```bash
sh <(curl -L https://nixos.org/nix/install) --daemon
nix-env -iA cachix -f https://cachix.org/api/v1/install
cachix use devenv
nix-env -if https://github.com/cachix/devenv/tarball/v0.4
```

- **Windows (WSL2)**

```bash
sh <(curl -L https://nixos.org/nix/install) --no-daemon
nix-env -iA cachix -f https://cachix.org/api/v1/install
cachix use devenv
nix-env -if https://github.com/cachix/devenv/tarball/v0.4
```

#### Cloning source

In a directory of your choosing, download the project source and enter the directory:

```bash
git clone --recursive https://gitlab.com/internet-cleanup-foundation/web-security-map/ && cd web-security-map/
```

#### Direnv (optional, recommended)

To automatically enter the development shell when entering the project directory install and enable Direnv: https://direnv.net

Allow this project's `.envrc` file to be automatically loaded when entering the project directory:

```bash
direnv allow
```

#### Building, testing and running the project

Active the Devenv shell (not needed with Direnv):

```bash
devenv shell
```

Running `make` once to create a development Virtualenv and setup the App and its dependencies. Running `make` without arguments by default also runs basic checks and tests to verify project code quality.

```bash
make
```

After completing successfully Web Security Map development server is available to run:

```bash
devenv up
```

Now visit the [map website](http://127.0.0.1:8000/) and/or the
[admin website](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000 (credentials: admin:faalkaart).

To fill up the empty installation with some data, use the data included with the following commands:

```bash
websecmap load_dataset development_user
websecmap load_dataset periodic_tasks
websecmap load_dataset development_scandata
websecmap report
```

This will provide some municipalities in the Netherlands with a report and stats.


#### Getting started with development

For development purposes it's possible to run the major components of websecmap separately, as they can be rebooted
as such. After a complete installation, use:

```bash
make run-frontend  # to run the django website
make run-broker  # to run redis (when you need to develop tasks)
make run-worker  # to run a worker that processes tasks from redis
```

Do not forget to restart your worker after altering tasks.

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

## FAQ / Troubleshooting

### Missing xcode (mac users)
During installation mac users might get the following error, due to not having xcode installed or updated.

```
xcrun: error: invalid active developer path (/Library/Developer/CommandLineTools), missing xcrun at: /Library/Developer/CommandLineTools/usr/bin/xcrun
```

You can update / install xcode tools with the following command:

```
xcode-select --install
```


Dealing with compiling mysql and other software that uses SSL.
You can look at the detailed issue here, mostly compilation fails because of a missing environment variable.

The LDFLAGS need to point to your openssl installation, for example:
"ld: library not found for -lssl" ->
```bash
set -gx LDFLAGS "-L/usr/local/opt/openssl@3/lib"
set -gx CPPFLAGS "-I/usr/local/opt/openssl@3/include"
```
Note: for this you need the X86 (not the arm64!) openssl, because life is pain. So running your "brew install openssl"
does not work, as that installs to: "/opt/homebrew/opt/openssl/lib/".

On m1 macs you can do:
`arch -x86_64 /bin/bash`  # start an x86 shell, which means homebrew will install in /usr/local/Homebrew
`rm -rf /usr/local/Homebrew/`  # to start a new homebrew, without 'missing taps' and other possible weirdness.
`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` taken from https://brew.sh/
`/usr/local/Homebrew/bin/brew install openssl`  # There you go, now retry.




Fish shell, mac, archx86 ld: library not found for -lzstd, you need the x86 brew:
```bash
arch -x86_64 /usr/local/bin/brew reinstall zstd
set -x LDFLAGS -L/usr/local/Homebrew/Cellar/zstd/
```



If you get issues like these:
OSError: dlopen(/usr/local/lib/libgdal.dylib, 6): Library not loaded: /usr/local/opt/openssl/lib/libssl.1.0.0.dylib
  Referenced from: /usr/local/opt/libpq/lib/libpq.5.dylib
  Reason: image not found


Then look here:
https://github.com/kelaberetiv/TagUI/issues/86


### Missing Docker Daemon (mac users)
While docker is installed using brew in prior steps, you probably want to have
a gui controlling docker.

Docker for mac can be downloaded here:
https://download.docker.com/mac/stable/Docker.dmg

You can also visit the docker website and get the link using the time tested Oracle(tm) download strategy, here:
https://hub.docker.com/editions/community/docker-ce-desktop-mac


### Manage NPM modules for the map

npm install --prefix websecmap/map/static/js/vendor [packagename]

The --prefix is the key, and allows for multiple repositories.


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
