# Beta: Docker Support

This is still in development.

To use any of the docker features, install docker first and make sure the path your code is on is known within docker.

Installation instructions for docker are here: https://docs.docker.com/install/

## Available commands:
Several commands exist to either run Web Security Map as well to update the docker container.

### docker-build
Creates a docker container with a host of dependencies baked in. Works especially well for running dnssec scans.


### docker-websecmap
Run the Web Security Map command in a container. Does not have access to a database.


### docker-websecmap-with-db
Uses the development database (db.sqlite3). It will allow you to run complete scans in a steady environment.
