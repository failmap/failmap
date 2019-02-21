[![Code Climate](https://codeclimate.com/github/Web Security Map/Web Security Map/badges/gpa.svg)](https://codeclimate.com/github/Web Security Map/Web Security Map) [![pipeline status](https://gitlab.com/Web Security Map/Web Security Map/badges/master/pipeline.svg)](https://gitlab.com/Web Security Map/Web Security Map/commits/master) [![Test Coverage](https://codeclimate.com/github/Web Security Map/Web Security Map/badges/coverage.svg)](https://codeclimate.com/github/Web Security Map/Web Security Map/coverage)
[![Badges](https://img.shields.io/badge/badges-6-yellowgreen.svg)](https://shields.io) [![Cyberveiligheid](https://img.shields.io/badge/Cyberveiligheid-97%25-yellow.svg)](https://eurocyber.nl) [![Join the chat at https://gitter.im/internet-cleanup-foundation/Lobby](https://badges.gitter.im/internet-cleanup-foundation/Lobby.svg)](https://gitter.im/internet-cleanup-foundation/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Why Web Security Map
===========
We believe privacy and information integrity are the basics of a resilient information society.

By providing unprecedented transparency on the most basic levels of information security, insight in
the quality and capability of organizations regarding their responsibilities is displayed.

Web Security Map uses the complexity of a traffic light anyone is able to determine if organizations that are responsible
for safeguarding information are doing what they are supposed to do.

It is perfectly possible to run Web Security Map software for yourself, allowing you to independently verify the
state of information security basics. All our products are open source.


What is it
----------
Web Security Map is an open source web application that continuously evaluates the implementation of security standards and
best practices at (governmental) organizations.

This repository contains the mapping application fo Web Security Map: the public frontend, an administrative interface and scanners.

![screenshot](docs/screenshot.png)

![screenshot](docs/admin_interface.png)


Getting started
===============
Keywords: quickstart, installation

## 0: If you want a complete production setup
Then read the installation tutorial, which is significantly easier than the below development setup!

For full installation with everything and anything, check: https://gitlab.com/Web Security Map/server/


## 1: Install dependencies on your system
Setup your system to run this software using your favourite package manager.

**MacOS (brew)**
```bash
brew install git python3 direnv
```

**Debian Linux (apt)**
```bash
apt-get install git python3 direnv
```

**Redhat/CentOS (yum)**
```bash
yum install git python3 direnv
```

Or download and install each package separately:

- [git](https://git-scm.com/downloads) (download and install)
- [python3.6](https://www.python.org/downloads/) (download and install)
- [Tox](http://tox.readthedocs.io/) (`pip3 install --user tox`)
- [direnv](https://direnv.net/) (download and install, then follow [setup instructions](https://direnv.net/), see Direnv section below)
- [Docker](https://docs.docker.com/engine/installation/) (recommended, follow instructions to install.)

## 2: Install direnv correctly
Then set up direnv, the right command depends on your shell:

**BASH**
Add the following line at the end of the ~/.bashrc file:
```bash
eval "$(direnv hook bash)"
```

Make sure it appears even after rvm, git-prompt and other shell extensions that manipulate the prompt.

**ZSH**
Add the following line at the end of the ~/.zshrc file:
```bash
eval "$(direnv hook zsh)"
```

**FISH**
Add the following line at the end of the ~/.config/fish/config.fish file:

```bash
eval (direnv hook fish)
```

**TCSH**
Add the following line at the end of the ~/.cshrc file:

```bash
eval `direnv hook tcsh`
```


## 3: Generic install steps
Install Tox, which helps to install the rest of the dependencies of this project:

```bash
pip3 install --user tox
```

In a directory of your choosing:

download the software

```bash
git clone --recursive https://gitlab.com/Web Security Map/Web Security Map/
```

enter the directory of the downloaded software

```bash
cd Web Security Map/
```

This prepares the shell environment for local development.

```bash
direnv allow
```

Running Tox once creates a development Virtualenv in .tox/default/ which is automatically used after creation due to Direnv setup. Running Tox without arguments by default also runs basic checks and tests to verify project code quality.

```bash
tox
```

After completing successfully Web Security Map is available to run. For example, to show a list of commands:

```bash
Web Security Map help
```
Now run the following command to start a full development server.

```bash
Web Security Map devserver
```

Now visit the [map website](http://127.0.0.1:8000/) and/or the
[admin website](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000 (credentials: admin:faalkaart).

## 4. Optional Steps
This shows the current data on the map:

```bash
Web Security Map rebuild_ratings
```

It is possible to start the server without redis and without (re)loading data:

```bash
Web Security Map devserver --no-backend --no-data
```


Give everyone an F rating!

```bash
https://www.youtube.com/watch?v=a14Y2V5zJlY
```

```bash
https://www.youtube.com/watch?v=eAwq2QV7f1k
```


Documentation
=============
Documentation is provided at [ReadTheDocs](http://Web Security Map.readthedocs.io/).

Get involved
============

Web Security Map is open organisation run by volunteers.

- Talk to us via [gitter.im/internet-cleanup-foundation](https://gitter.im/internet-cleanup-foundation/Lobby#).
- Or using IRC: #internet-cleanup-foundation/Lobby @ irc.gitter.im (see https://irc.gitter.im for information)
- E-mail us at: [info@faalkaart.nl](mailto:info@faalkaart.nl),
- Or simply start hacking on the code, open an [Gitlab Issue](https://gitlab.com/Web Security Map/Web Security Map/issues/new) or send a [Gitlab Merge Request](https://gitlab.com/Web Security Map/Web Security Map.org/merge_requests/new).

Thanks to
=========
This project is being maintained by the [Internet Cleanup Foundation](https://internetcleanup.foundation).
Special thanks to the SIDN Fonds for believing in this method of improving privacy.

Thanks to the many authors contributing to open software.
