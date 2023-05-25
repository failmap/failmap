ARG PYTHON_VERSION=3.10
ARG NUCLEI_VERSION=2.9.4
ARG GOLANG_VERSION=1.20
ARG AMASS_VERSION=3.23.1

# create Python virtualenv with Python dependencies
FROM python:${PYTHON_VERSION} AS virtualenv

RUN python3 -mvenv /pyenv
ENV VIRTUAL_ENV = /pyenv
ENV PATH=/pyenv/bin:$PATH
ENV CRYPTOGRAPHY_DONT_BUILD_RUST 1

COPY requirements-deploy.txt /source/
RUN --mount=type=cache,target=/root/.cache pip install --quiet --requirement /source/requirements-deploy.txt
COPY requirements.txt /source/
RUN --mount=type=cache,target=/root/.cache pip install --quiet --requirement /source/requirements.txt

# copy dependencies that are not in pypi or otherwise not available with ease
COPY ./vendor/ /source/vendor/

# copy and install websecmap source last, as this changes most often, this improves docker cache
COPY pyproject.toml README.md /source/
COPY tools/ /source/tools/
COPY websecmap/ /source/websecmap/
WORKDIR /source

RUN pip install --editable . --no-deps

FROM python:${PYTHON_VERSION} AS dnscheck

RUN apt-get update && apt-get install -yqq \
  perl \
  libfile-sharedir-install-perl

# install dnscheck
COPY vendor/dnscheck /vendor/dnscheck
COPY tools/docker-install-dnscheck.sh /tools/docker-install-dnscheck.sh
RUN tools/docker-install-dnscheck.sh
COPY tools/dnssec.pl /tools/dnssec.pl

FROM golang:${GOLANG_VERSION} AS nuclei

# import variable
ARG NUCLEI_VERSION

RUN go install -v "github.com/projectdiscovery/nuclei/v2/cmd/nuclei@v${NUCLEI_VERSION}"

FROM golang:${GOLANG_VERSION} AS amass

# import variable
ARG AMASS_VERSION

RUN go install -v "github.com/owasp-amass/amass/v3/...@v${AMASS_VERSION}"

# restart with a clean image
FROM python:${PYTHON_VERSION} AS release

USER root

RUN apt-get update && apt-get install -yqq \
  # nmap scans require nmap-scripts for banner grabbing
  nmap \
  nmap-common \
  # dnscheck dependencies, from engine/debian/control file
  perl \
  libcrypt-openssl-random-perl \
  libdbd-mysql-perl \
  libdbi-perl \
  libdigest-bubblebabble-perl \
  libdigest-sha-perl \
  libio-socket-inet6-perl \
  libmail-rfc822-address-perl \
  libmime-base32-perl \
  libmime-lite-perl \
  libnet-dns-perl \
  libnet-dns-sec-perl \
  libnet-ip-perl \
  libsocket6-perl \
  libtext-template-perl \
  libtimedate-perl \
  libyaml-libyaml-perl \
  libconfig-any-perl \
  libfile-sharedir-perl \
  liblist-moreutils-perl \
  libyaml-perl \
  libjson-xs-perl \
  # nuclei dependencies
  chromium \
  ca-certificates \
  dnsutils \
  && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV = /pyenv
ENV PATH=/pyenv/bin:$PATH

# expose relevant executable(s)
RUN ln -s /pyenv/bin/websecmap /usr/local/bin/
RUN ln -s /pyenv/bin/uwsgi /usr/local/bin/
RUN ln -s /pyenv/bin/celery /usr/local/bin/
RUN ln -s /pyenv/bin/dnssec.pl /usr/local/bin/

COPY --from=nuclei /go/bin/nuclei /usr/local/bin/nuclei

RUN install -o nobody -g nogroup -d /opt/nuclei
USER nobody:nogroup
RUN HOME=/opt/nuclei /usr/local/bin/nuclei -update-templates
USER root

COPY --from=amass /go/bin/amass /usr/local/bin/amass

# copy artifacts from dnscheck build
COPY --from=dnscheck /usr/local/share/perl /usr/local/share/perl

# copy artifacts from dnssec install
COPY /tools/dnssec.pl /usr/local/bin/dnssec.pl

# install the Python App
COPY --from=virtualenv /pyenv /pyenv
COPY --from=virtualenv /source /source

# copy dependencies that are not in pypi or otherwise not available with ease
COPY ./vendor/ /source/vendor/

WORKDIR /

# configuration for django-uwsgi to work correct in Docker environment
ENV UWSGI_GID root
ENV UWSGI_UID root
ENV UWSGI_MODULE websecmap.wsgi
# serve static files (to caching proxy) from collected/generated static files
ENV UWSGI_STATIC_MAP /static=/srv/websecmap/static
# set proxy and browser caching for static files to 1 month
ENV UWSGI_STATIC_EXPIRES /* 2678400
# disable exception message when client interrupts request, (OSError: write error)
ENV UWSGI_DISABLE_WRITE_EXCEPTION true
ENV TOOLS_DIR /usr/local/bin/
ENV VENDOR_DIR /source/vendor/

# collect all static files form all django applications into static files directory
RUN /pyenv/bin/websecmap collectstatic

ARG VERSION=0.0.0-dev0
RUN echo "VERSION='$VERSION'" >> /source/websecmap/__version__.py

EXPOSE 8000

USER nobody:nogroup

# Todo: add working healthcheck, should be depending on role of the worker what healthy means.
# All containers report as being unhealthy. Localhost:8000 is not running anything. Nor is 80.
# HEALTHCHECK CMD curl --silent --fail http://localhost:8000/ || exit 1

ENTRYPOINT [ "/usr/local/bin/websecmap" ]

CMD [ "help" ]

FROM release AS selftest

USER nobody:nogroup

RUN websecmap --version | grep -E '[0-9]+\.[0-9]+\.[0-9]+'
RUN dnssec.pl 2>&1 | grep usage:
RUN HOME=/opt/nuclei nuclei -disable-update-check
ARG AMASS_VERSION
RUN amass -version 2>&1 | grep ${AMASS_VERSION}
