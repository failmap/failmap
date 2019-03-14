#!/bin/sh

set -xe

# run simple smoketests to verify docker image build is sane

host=${1:-localhost}

if /bin/ls --help 2>&1 | grep BusyBox; then
  # Busybox shell, use different argument for timeout
  timeout="timeout -t ${TIMEOUT:-60}"
else
  timeout="timeout ${TIMEOUT:-60}"
fi

if [ "$(uname -s)" = Darwin ] && ! command -v timeout;then
  timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }
fi

exit_cleanup(){
  kill -15 "$logs_pid"
  docker rm -f websecmap-$$ >/dev/null &
}

# start docker container
docker run --rm --name websecmap-$$ -e "ALLOWED_HOSTS=$host" -p 8000 -d \
  "${IMAGE:-websecmap/websecmap:latest}" \
  production --migrate --loaddata development
docker logs websecmap-$$ -f 2>&1 | awk '$0="docker: "$0' &
logs_pid=$!
trap "exit_cleanup" EXIT INT QUIT HUP TERM ALRM USR1
port="$(docker port websecmap-$$ 8000/tcp | cut -d: -f2)"

# wait for server to be ready
sleep 3
$timeout /bin/sh -c "while ! curl -sSIk http://$host:$port 2>/dev/null| grep 200\\ OK;do sleep 1;done"

# index page
curl -s "http://$host:$port" |grep MSPAINT.EXE
# static files
curl -sI "http://$host:$port/static/images/fail_logo.png" |grep 200\ OK
# compressed static files
curl -sI "http://$host:$port/static/$(curl -s "http://$host:$port/static/CACHE/manifest.json"|sed -n 's,.*\(CACHE/js/.*js\).*,\1,p'|head -n1)"|grep 200\ OK

# admin login
# tests disabled due to:
# * Resolve address 'docker' found illegal!
# * Couldn't parse CURLOPT_RESOLVE entry 'websecmap.test:32768:docker'!
# curl -siv --cookie-jar cookie-$$ --cookie cookie-$$ "http://$host:$port/admin/login/"|grep 200\ OK
# curl -siv --cookie-jar cookie-$$ --cookie cookie-$$ --data "csrfmiddlewaretoken=$(grep csrftoken cookie-$$ | cut -f 7)&username=admin&password=faalkaart" "http://$host:$port/admin/login/"|grep 302\ Found


# Test if o-saft runs
docker exec websecmap-$$ /O-Saft/o-saft

# Test if hypersh CLI is available
docker exec websecmap-$$ /usr/local/bin/hyper

# cleanup
rm -f cookie-$$

echo "All good!"
