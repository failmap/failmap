FROM python:3 as build

COPY requirements*.txt /
RUN pip install -r requirements.txt
RUN pip install -r requirements.deploy.txt

COPY . /source/
WORKDIR /source/
RUN python setup.py sdist

# switch to lightweight base image for distribution
FROM python:3-alpine
COPY --from=build /root/.cache /root/.cache
COPY --from=build /source/dist/* /

RUN pip install /failmap-admin-*.tar.gz

WORKDIR /

# configuration for django-uwsgi to work correct in Docker environment
ENV UWSGI_GID root
ENV UWSGI_UID root
ENV UWSGI_MODULE failmap_admin.wsgi
ENV UWSGI_STATIC_MAP /static=/srv/failmap_admin/static

RUN /usr/local/bin/failmap-admin collectstatic

ENTRYPOINT [ "/usr/local/bin/failmap-admin" ]

CMD [ "help" ]
