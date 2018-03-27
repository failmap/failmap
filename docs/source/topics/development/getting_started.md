# Getting Started

This quickstart results in this:
![Web Application](shared/screenshot.png)

Including a nice admin interface:
![Admin Interface](shared/admin_interface.png)

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

Or download and install each package seperately:

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
Install Tox, which helps to install the rest of the dependancies of this project:

```bash
pip3 install --user tox
```

In a directory of your choosing:

download the software

```bash
git clone --recursive https://gitlab.com/failmap/failmap/
```

enter the directory of the downloaded software

```bash
cd failmap/
```

This prepares the shell environment for local development.

```bash
direnv allow
```

Running Tox once creates a development Virtualenv in .tox/default/ which is automatically used after creation due to Direnv setup. Running Tox without arguments by default also runs basic checks and tests to verify project code quality.

```bash
tox
```

After completing succesfully Failmap is available to run. For example, to show a list of commands:

```bash
failmap help
```
Now run the following command to start a full development server.

```bash
failmap devserver
```

Now visit the [map website](http://127.0.0.1:8000/) and/or the
[admin website](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000 (credentials: admin:faalkaart).

## 4. Optional Steps
This shows the current data on the map:

```bash
failmap rebuild_ratings
```

It is possible to start the server without redis and without (re)loading data:

```bash
failmap devserver --no-backend --no-data
```


Give everyone an F rating!

```bash
https://www.youtube.com/watch?v=a14Y2V5zJlY
```

```bash
https://www.youtube.com/watch?v=eAwq2QV7f1k
```


## Troubleshooting
This repository uses [submodules](https://git-scm.com/docs/git-submodule) to pull in
external dependencies. If you have not cloned the repository with `--recursive` or you need to
restore the submodules to the expected state run:

```bash
git submodule update
```

Git submodules are an unreliable mess if you already have the system up and running. Updating submodules by force can be
done using this command:

```bash
git submodule update --init --force --remote
```

## About Versioning

Version for the project is losely semver with no specific release schedule or meaning to version numbers (eg: stable/unstable).

Formal releases are created by creating a Git tag with the desired version number. These tags will trigger automated
builds which will release the specified code under that version. Tags can be pushed from a local repository or created
through the Gitlab interface: https://gitlab.com/failmap/failmap/tags/new

Informal releases are created by new commits pushed/merged to the master. The version number of the last formal release
will be suffixed with the current short Git SHA.

For all releases artifacts will be created. Currently only Docker containers are pushed into the
[registry](https://gitlab.com/failmap/failmap/container_registry). Each artifact will be tagged with the appropriate
version (formal or informal). Where needed abstract tags will also be created/updated for these artifacts (eg: Docker
build/staging/latest tags).

For local development informal release or a special `dev0` build release is used which indicates a different state
from the formal releases.


## Known Issues

### Docker installation

#### ERROR: for failmap_database_1  Cannot start service database: Mounts denied:
As the error suggests, you're running the installation from a directory that is not shared with Docker. Change the
docker configuration or run the installation from your user directory. You might receive this error if you run
`docker-composer up` from /var/www/ or /srv/www/ as docker by default only has access to your user directory.
