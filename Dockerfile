# base build on small footprint image
FROM alpine:3.12 as build

RUN apk --no-cache add \
  build-base \
  zlib-dev \
  jpeg-dev \
  libffi-dev \
  libressl-dev \
  mariadb-dev \
  postgresql-dev \
  linux-headers \
  # build dependencies for dnscheck perl module
  perl \
  perl-utils \
  perl-file-sharedir-install \
  make \
  # required to install osmtogeojson module
  nodejs \
  nodejs-npm \
  libxml2-dev \
  libxslt-dev \
  python3-dev \
  git \
  # build cffi module, requires compile because no wheel is available.
  # cffi is needed in certificate tests and in remote workers.
  gcc

# install dnscheck
COPY vendor/dnscheck /vendor/dnscheck
COPY tools/docker-install-dnscheck.sh /tools/docker-install-dnscheck.sh
RUN tools/docker-install-dnscheck.sh

# install osmtogeojson
RUN npm install --global osmtogeojson

# this warning most often just leads to false positives
ENV PIP_DISABLE_PIP_VERSION_CHECK 1  
RUN python3 -mvenv /pyenv
ENV VIRTUAL_ENV /pyenv
ENV PATH $VIRTUAL_ENV/bin:$PATH

# a module wants to build a wheel, which is fine. But wheel needs to be available first. (is this still valid after
# removing proxybroker and django-geojson?)
RUN python3 -m pip install wheel

COPY requirements.txt /source/
RUN pip install -qr /source/requirements.txt

# restart with a clean image
FROM websecmap/o-saft:latest

USER root

# mailcap includes mimetypes required by uwsgi
RUN apk --no-cache add \
  zlib\
  libjpeg \
  libffi \
  libressl \
  libxml2 \
  libxslt \
  mariadb-connector-c \
  postgresql-libs \
  postgresql-client \
  sqlite \
  mailcap \
  python3 \
  # runtime dependencies for dnscheck perl module
  perl \
  perl-config-any \
  perl-date-format \
  perl-dbi \
  perl-file-sharedir \
  perl-net-dns \
  perl-net-dns-sec \
  perl-net-ip \
  perl-config-any \
  perl-dbi \
  perl-file-sharedir \
  perl-list-moreutils \
  perl-module-pluggable \
  perl-net-dns \
  perl-net-dns-sec \
  perl-net-ip \
  perl-yaml \
  # runtime dependencies for osmtogeojson
  nodejs \
  nodejs-npm

ENV VIRTUAL_ENV = /pyenv
ENV PATH=/pyenv/bin:$PATH

# expose relevant executable(s)
RUN ln -s /pyenv/bin/websecmap /usr/local/bin/
RUN ln -s /pyenv/bin/uwsgi /usr/local/bin/
RUN ln -s /pyenv/bin/celery /usr/local/bin/
RUN ln -s /pyenv/bin/dnssec.pl /usr/local/bin/

# install build application
COPY --from=build /pyenv /pyenv
COPY --from=build /source /source

# copy artifacts from dnscheck build
COPY --from=build /usr/local/share/perl5 /usr/local/share/perl5
COPY --from=build /usr/local/bin/dnscheck /usr/local/bin/dnscheck

# copy artifacts from osmtogeojson install
COPY --from=build /usr/lib/node_modules/osmtogeojson /usr/lib/node_modules/osmtogeojson
RUN ln -s /usr/lib/node_modules/osmtogeojson/osmtogeojson /usr/local/bin/

COPY /tools/dnssec.pl /usr/local/bin/dnssec.pl

# copy dependencies that are not in pypi or otherwise not available with ease
COPY ./vendor/ /source/vendor/

# copy and install websecmap source last, as this changes most often, this improves docker cache
COPY setup.py README.md /source/
COPY tools/ /source/tools/
COPY websecmap/ /source/websecmap/
WORKDIR /source

# no module named 'pip', cannot run pip directly
RUN python3 -m ensurepip
RUN python3 -m pip install -e .

WORKDIR /

# configuration for django-uwsgi to work correct in Docker environment
ENV UWSGI_GID root
ENV UWSGI_UID root
ENV UWSGI_MODULE websecmap.wsgi
# serve static files (to caching proxy) from collected/generated static files
ENV UWSGI_STATIC_MAP /static=/srv/websecmap/static
# set proxy and browser caching for static files to 1 month
ENV UWSGI_STATIC_EXPIRES /* 2678400
ENV TOOLS_DIR /usr/local/bin/
ENV VENDOR_DIR /source/vendor/

# collect all static files form all django applications into static files directory
RUN /pyenv/bin/websecmap collectstatic

# Compress JS/CSS before serving, using django-compressor, run after collectstatic
# COMPRESS=1 is a hack to disable django_uwsgi app as it currently conflicts with compressor
# https://github.com/django-compressor/django-compressor/issues/881
RUN env APPLICATION_MODE=admin COMPRESS=1 /pyenv/bin/websecmap compress

EXPOSE 8000

ENTRYPOINT [ "/usr/local/bin/websecmap" ]

CMD [ "help" ]
