# Running a remote worker
Running a worker is an easy way to contribute to this project.

Workers help run our thousands of daily scans over various connections and additional capacity.

Running a worker comes with mutual trust: you'll run code from us (mostly in a container) and we're processing the
results without question. Additionally you'll be able to view some systems that might not be secure enough and your
responsible disclosure is welcome.

## How to start the worker
1: Install Docker, see here: https://docs.docker.com/install/.

(optional): If you don't want to run the script as root, install docker with the option not to require root to start containers.

2: Obtain a .p12 file from us, you can do so by asking here: https://gitter.im/internet-cleanup-foundation/Lobby or
sending a mail to info@faalkaart.nl

3: Go to a directory of your choosing, and place the .p12 file there.

4: Rename the .p12 file to client.p12.

5: Logs will be created in this directory.

6: Start the worker:
```bash
curl -s https://gitlab.com/failmap/failmap/raw/master/tools/faalwerker.sh | /bin/bash
```

This starts a worker in the background. It will generate a lot of output.

Do note that you're piping to bash whatever we send you. So better check the code first, which can change any moment.

## How to verify your worker is running
You'll probably see a lot of output: the container starting, celery running, the task being performed and such.

If you want to see that failmap is processing the result, there are two ways:
1: You can see your computer name pop up in the workers on https://admin.faalkaart.nl/admin/
2: You can see the amount of tasks processed increase on https://grafana.faalkaart.nl

Errors of these workers are logged here:
https://sentry.io/internet-cleanup-foundation/remote-workers/

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

``` bash
... todo
```

todo: docker as user, aka, pl0x don't run it as root.

## Suppress output:

Like this:
```bash
curl -s https://gitlab.com/failmap/failmap/raw/master/tools/faalwerker.sh | /bin/bash &> /dev/null
```
