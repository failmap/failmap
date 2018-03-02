#!/usr/bin/env bash

set -e -o pipefail

# this will start a remote worker using docker

faalcontainernaamvoorvoegsel=failmap-worker
faalcontainerfaalimagenaam=registry.gitlab.com/failmap/failmap:latest
faalredis=redis://faalkaart.nl:1337/0
faalp12bestand=$(realpath client.p12)
faallogfaallevel=info
faalaantalprocessen=10
faalaantalprocessenvoorqualys=1
faalgeheim=geheim

faalrolqualys=scanner_qualys

kloptalles? (){
  if ! test -f "$faalp12bestand";then
    echo "Falen: Je hebt waarschijnlijk een bestand dat eindigt op .p12 gekregen, hernoem het naar client.p12 en zorg dat het in deze folder staat."
    exit 1
  fi

  if ! command -v docker >/dev/null;then
    echo "Falen: Installeer docker, sudo apt install docker-engine of kijk op https://docs.docker.com/install/."
    exit 1
  fi

  if ! docker ps >/dev/null;then
    echo "Falen: Zorg dat docker daemon gestart is."
    exit 1
  fi
}

startmetfalen (){
  if ping6 faalkaart.nl -c3 &>/dev/null;then
    faalrol=scanner
  else
    faalrol=scanner_ipv4_only
  fi

  # (stop en) verwijder huidige faalcontainers (voor de zekerheid)
  docker rm -f $faalcontainernaamvoorvoegsel-$faalrol $faalcontainernaamvoorvoegsel-$faalrolqualys &>/dev/null || true

  # haal nieuwe faalcontainerfaalimage op vanuit de server
  docker pull $faalcontainerfaalimagenaam

  # start nieuwe faalcontainers
  echo $faalgeheim | docker run -d --rm -ti --name $faalcontainernaamvoorvoegsel-$faalrol -u nobody:nogroup \
    -e WORKER_ROLE=$faalrol \
    -e BROKER=$faalredis \
    -e PASSPHRASE=$faalgeheim \
    -v "$faalp12bestand:/client.p12" \
    $faalcontainerfaalimagenaam \
    celery worker --loglevel $faallogfaallevel --concurrency=$faalaantalprocessen
  echo $faalgeheim | docker run -d --rm -ti --name $faalcontainernaamvoorvoegsel-$faalrolqualys -u nobody:nogroup \
    -e WORKER_ROLE=$faalrolqualys \
    -e BROKER=$faalredis \
    -e PASSPHRASE=$faalgeheim \
    -v "$faalp12bestand:/client.p12" \
    $faalcontainerfaalimagenaam \
    celery worker --loglevel $faallogfaallevel --concurrency=$faalaantalprocessenvoorqualys

  echo "Begonnen met falen"
  docker wait $faalcontainernaamvoorvoegsel-$faalrol $faalcontainernaamvoorvoegsel-$faalrolqualys
}

faalafsluiten (){
  docker rm -f $faalcontainernaamvoorvoegsel-$faalrol $faalcontainernaamvoorvoegsel-$faalrolqualys &>/dev/null || true
  echo "Klaar met falen"
}

trap faalafsluiten EXIT

kloptalles?

# blijf net zo lang doorgaan als we willen
while sleep 5;do
  startmetfalen
done
