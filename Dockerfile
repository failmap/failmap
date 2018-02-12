# use full image for build (compile) dependencies
FROM python:3.6 as build

# install app and dependencies in a artifact-able directory
RUN pip install virtualenv
RUN virtualenv /pyenv

# install requirements seperately as they change less often then source, improved caching
COPY requirements.txt /source/
RUN /pyenv/bin/pip install -r /source/requirements.txt
COPY requirements.deploy.txt /source/
RUN /pyenv/bin/pip install -r /source/requirements.deploy.txt

# copy all relevant files for python installation
COPY ./failmap/ /source/failmap/
# add wildcard to version file as it may not exists (eg: local development)
COPY setup.py setup.cfg MANIFEST.in requirements.dev.txt version* /source/

# Install app by linking source into virtualenv. This is against convention
# but allows the source to be overwritten by a volume during development.
RUN /pyenv/bin/pip install -e /source/ --no-deps

# switch to lightweight base image for distribution
FROM python:3.6-slim

# hack for slim image to fix broken install of postgres
RUN /bin/bash -c 'mkdir -p /usr/share/man/man{1..8}'

# install dependent libraries (remove cache to prevent inclusion in layer)
RUN apt-get update && \
  apt-get install -yqq libxml2 libmysqlclient18 mysql-client postgresql \
    postgresql-contrib mime-support python-watchdog python-setuptools && \
  rm -rf /var/lib/apt/lists/*

# install build application
COPY --from=build /pyenv /pyenv
COPY --from=build /source /source

# expose relevant executable(s)
RUN ln -s /pyenv/bin/failmap /usr/local/bin/
RUN ln -s /pyenv/bin/uwsgi /usr/local/bin/
RUN ln -s /pyenv/bin/celery /usr/local/bin/

WORKDIR /

# configuration for django-uwsgi to work correct in Docker environment
ENV UWSGI_GID root
ENV UWSGI_UID root
ENV UWSGI_MODULE failmap.wsgi
# serve static files (to caching proxy) from collected/generated static files
ENV UWSGI_STATIC_MAP /static=/srv/failmap/static
# set proxy and browser caching for static files to 1 month
ENV UWSGI_STATIC_EXPIRES /* 2678400

# collect all static files form all django applications into static files directory
RUN /pyenv/bin/failmap collectstatic

# Compress JS/CSS before serving, using django-compressor, run after collectstatic
# COMPRESS=1 is a hack to disable django_uwsgi app as it currently conflicts with compressor
# https://github.com/django-compressor/django-compressor/issues/881
RUN env COMPRESS=1 /pyenv/bin/failmap compress

EXPOSE 8000

ENTRYPOINT [ "/usr/local/bin/failmap" ]

CMD [ "help" ]
