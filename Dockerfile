# base build on small footprint image
FROM python:3.6-alpine3.7 as build

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
  make

# install app and dependencies in a artifact-able directory
RUN pip install virtualenv
RUN virtualenv /pyenv

# install requirements seperately as they change less often then source, improved caching
COPY requirements.txt /source/
RUN /pyenv/bin/pip install -r /source/requirements.txt
COPY requirements.deploy.txt /source/
RUN /pyenv/bin/pip install -r /source/requirements.deploy.txt

COPY vendor/dnscheck /vendor/dnscheck
COPY tools/docker-install-dnscheck.sh /tools/docker-install-dnscheck.sh
RUN tools/docker-install-dnscheck.sh


# restart with a clean image
FROM python:3.6-alpine3.7

# mailcap includes mimetypes required by uwsgi
RUN apk --no-cache add \
  zlib\
  libjpeg \
  libffi \
  libressl \
  libxml2 \
  mariadb-client-libs \
  postgresql-libs \
  mailcap \
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
  perl-yaml

# expose relevant executable(s)
RUN ln -s /pyenv/bin/failmap /usr/local/bin/
RUN ln -s /pyenv/bin/uwsgi /usr/local/bin/
RUN ln -s /pyenv/bin/celery /usr/local/bin/
RUN ln -s /pyenv/bin/dnssec.pl /usr/local/bin/

# install build application
COPY --from=build /pyenv /pyenv
COPY --from=build /source /source

# copy artifacts from dnscheck build
COPY --from=build /usr/local/share/perl5 /usr/local/share/perl5
COPY --from=build /usr/local/bin/dnscheck /usr/local/bin/dnscheck


# copy all relevant files for python installation
COPY ./failmap/ /source/failmap/
COPY /tools/dnssec.pl /source/tools/dnssec.pl

# add wildcard to version file as it may not exists (eg: local development)
COPY setup.py setup.cfg MANIFEST.in requirements.dev.txt version* /source/

# Install app by linking source into virtualenv. This is against convention
# but allows the source to be overwritten by a volume during development.
RUN /pyenv/bin/pip install -e /source/ --no-deps

WORKDIR /

# configuration for django-uwsgi to work correct in Docker environment
ENV UWSGI_GID root
ENV UWSGI_UID root
ENV UWSGI_MODULE failmap.wsgi
# serve static files (to caching proxy) from collected/generated static files
ENV UWSGI_STATIC_MAP /static=/srv/failmap/static
# set proxy and browser caching for static files to 1 month
ENV UWSGI_STATIC_EXPIRES /* 2678400
ENV TOOLS_DIR /usr/local/bin/

# collect all static files form all django applications into static files directory
RUN /pyenv/bin/failmap collectstatic

# Compress JS/CSS before serving, using django-compressor, run after collectstatic
# COMPRESS=1 is a hack to disable django_uwsgi app as it currently conflicts with compressor
# https://github.com/django-compressor/django-compressor/issues/881
RUN env COMPRESS=1 /pyenv/bin/failmap compress

EXPOSE 8000

ENTRYPOINT [ "/usr/local/bin/failmap" ]

CMD [ "help" ]
