from django.contrib.auth.middleware import RemoteUserMiddleware


class CustomRemoteUserMiddleware(RemoteUserMiddleware):
    header = "HTTP_REMOTE_USER"

    def process_request(self, request):
        super().process_request(request)
        # add staff permissions to newly created remote users
        if not request.user.is_superuser:
            request.user.is_staff = True
            request.user.is_superuser = True
            request.user.save()
