#!/usr/bin/env bash

set -e -o pipefail

# stop de resultaten van deze scriptie in een logbestand
logfile=faalwerker-$$.log
exec 3>&1
exec > $logfile 2>&1

set -x

faalcontainernaamvoorvoegsel=failmap-worker
faalcontainerfaalimagenaam=registry.gitlab.com/failmap/failmap:latest
faalredis=redis://faalkaart.nl:1337/0
faalp12bestand=$(realpath client.p12)
faallogfaallevel=info
faalaantalprocessen=10
faalaantalprocessenvoorqualys=1
faalgeheim=geheim
faalrol=scanner
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

wegmetdieouwezooi (){
  docker ps -aq --filter name=$faalcontainernaamvoorvoegsel | xargs docker rm -f || true
}

startmetfalen (){
  if ping6 faalkaart.nl -c3 &>/dev/null;then
    faalipv6=
  else
    faalipv6=_ipv4_only
  fi

  # (stop en) verwijder huidige faalcontainers (voor de zekerheid)
  docker ps -aq --filter name=$faalcontainernaamvoorvoegsel | xargs docker rm -f &>/dev/null || true

  # haal nieuwe faalcontainerfaalimage op vanuit de server
  docker pull $faalcontainerfaalimagenaam

  # start nieuwe faalcontainers
  docker run -d --rm -ti -u nobody:nogroup \
    --name $faalcontainernaamvoorvoegsel-$faalrol$faalipv6 \
    -e WORKER_ROLE=$faalrol$faalipv6 \
    -e BROKER=$faalredis \
    -e PASSPHRASE=$faalgeheim \
    -v "$faalp12bestand:/client.p12" \
    $faalcontainerfaalimagenaam \
    celery worker --loglevel $faallogfaallevel --concurrency=$faalaantalprocessen
  docker run -d --rm -ti -u nobody:nogroup \
    --name $faalcontainernaamvoorvoegsel-$faalrolqualys \
    -e WORKER_ROLE=$faalrolqualys \
    -e BROKER=$faalredis \
    -e PASSPHRASE=$faalgeheim \
    -v "$faalp12bestand:/client.p12" \
    $faalcontainerfaalimagenaam \
    celery worker --loglevel $faallogfaallevel --concurrency=$faalaantalprocessenvoorqualys

  echo "Begonnen met falen"
  docker logs -f $faalcontainernaamvoorvoegsel-$faalrol$faalipv6 | sed -l "s/^/$faalrol$faalipv6 /" &
  docker logs -f $faalcontainernaamvoorvoegsel-$faalrolqualys | sed -l "s/^/$faalrolqualys /" &
  faalcontainers=($(docker ps -aq --filter name=$faalcontainernaamvoorvoegsel))
  docker wait "${faalcontainers[@]}"

}

faalafsluiten (){
  docker ps -aq --filter name=$faalcontainernaamvoorvoegsel | xargs docker rm -f || true
  echo "Klaar met falen"
}

kloptalles?

wegmetdieouwezooi

# blijf net zo lang doorgaan als we willen
while sleep 5;do
  trap faalafsluiten EXIT
  echo "Poging to falen begonnen"
  startmetfalen
done &

echo "Falen in de achtergrond is gestart." 1>&3

tail -f $logfile 1>&3
