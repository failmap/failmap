#!/bin/sh

set -ve

# simple testsuite for docker-compose environment

host=${1:-localhost}

if test -f /bin/busybox;then
  timeout="timeout -t 15"
else
  timeout="timeout 15"
fi

# start complete failmap environment using docker-composer
export ALLOWED_HOSTS="$host"
export ADMIN_PORT=8000
export FRONTEND_PORT=8001
docker-compose up -d
trap "docker-compose logs;docker-compose down&" EXIT

# wait for server to be ready
$timeout /bin/sh -c "while ! curl -sSIk http://$host:$ADMIN_PORT | grep 200\ OK;do sleep 1;done"


# index page
curl -s "http://$host:$ADMIN_PORT" |grep MSPAINT.EXE
# static files
curl -sI "http://$host:$ADMIN_PORT/static/images/red-dot.png" |grep 200\ OK
# compressed static files
curl -sI "http://$host:$ADMIN_PORT/static/$(curl -s "http://$host:$ADMIN_PORT/static/CACHE/manifest.json"|sed -n 's,.*\(CACHE/js/.*js\).*,\1,p')"|grep 200\ OK
# admin login
curl -si --cookie-jar cookie --cookie cookie "http://$host:$ADMIN_PORT/admin/login/"|grep 200\ OK
curl -si --cookie-jar cookie --cookie cookie --data "csrfmiddlewaretoken=$(grep csrftoken cookie | cut -f 7)&username=admin&password=faalkaart" "http://$host:8000/admin/login/"|grep 302\ Found

echo "All good!"
