#!/bin/sh

set -ve

# run simple smoketests to verify docker image build is sane

host=${1:-localhost}

if test -f /bin/busybox;then
  timeout="timeout -t 15"
else
  timeout="timeout 15"
fi

handle_exception(){
  docker logs failmap;
  docker stop failmap&
}

# start docker container
docker run --rm --name failmap -e "ALLOWED_HOSTS=$host" -p 8000:8000 -d \
  "${IMAGE:-registry.gitlab.com/failmap/failmap:latest}" \
  production --migrate --loaddata development
trap "handle_exception" EXIT

# wait for server to be ready
$timeout /bin/sh -c "while ! curl -sSIk http://$host:8000 | grep 200\ OK;do sleep 1;done"

# index page
curl -s "http://$host:8000" |grep MSPAINT.EXE
# static files
curl -sI "http://$host:8000/static/images/red-dot.png" |grep 200\ OK
# compressed static files
curl -sI "http://$host:8000/static/$(curl -s "http://$host:8000/static/CACHE/manifest.json"|sed -n 's,.*\(CACHE/js/.*js\).*,\1,p')"|grep 200\ OK
# admin login
curl -si --cookie-jar cookie --cookie cookie "http://$host:8000/admin/login/"|grep 200\ OK
curl -si --cookie-jar cookie --cookie cookie --data "csrfmiddlewaretoken=$(grep csrftoken cookie | cut -f 7)&username=admin&password=faalkaart" "http://$host:8000/admin/login/"|grep 302\ Found

trap "" EXIT

# cleanup
docker stop failmap&

echo "All good!"
