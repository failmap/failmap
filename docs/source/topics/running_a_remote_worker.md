# Running a remote worker
By running such a worker you can contribute to this project with very little effort.

Failmap performs thousands of scans daily. This comes with rate limitations and the need to spread out tasks over
various workers.

Running a worker currently requires we have to trust you, and you have to trust us. This is because you're
willing to run code from us on your machine. You'll also be able to access parts of the system that might not
be secured very well or inject fake results (or other terrible things :)).

## How to start the worker
1: Install Docker, see here: https://docs.docker.com/install/

2: Obtain a .p12 file from us, you can do so by asking here: https://gitter.im/internet-cleanup-foundation/Lobby or
sending a mail to info@faalkaart.nl

3: Go to a directory of your choosing, and place the .p12 file there. Logs will be created in this directory.

4: Start the worker:
```bash
curl -s https://gitlab.com/failmap/failmap/raw/master/tools/faalwerker.sh | /bin/bash
```

This starts a worker in the background. It will give a lot of output.

Do note that you're piping to bash whatever we send you. So better check the code first, which can change any moment.
Here is exactly where the trust thing starts :)

## How to stop the worker
Run this command:
```
pkill -f "docker logs -f failmap-worker"
```

## What does the worker do?
The worker receives tasks that are described here: [scanners, scanning and ratings.](scanners_scanning_and_ratings).

In general it will try to contact websites trough your internet connection to perform scans. This is done at
decent frequency and will consume little system resources.

## Example on Debian

Install docker, as described here: https://docs.docker.com/install/linux/docker-ce/debian/#install-docker-ce
To get docker running, follow the post install instructions: https://docs.docker.com/install/linux/linux-postinstall/#configure-docker-to-start-on-boot

Verify docker daemon is running:
```bash
docker ps
```

Create a nice directory for the output.
``` bash
mkdir ~/failtasks
```

Make sure the .p12 file is also in this directory.

Start docker
```bash

```

todo: docker as user, aka, pl0x don't run it as root.

## Suppress output:

Like this:
```bash
curl -s https://gitlab.com/failmap/failmap/raw/master/tools/faalwerker.sh | /bin/bash &> /dev/null
```
