from websecmap.pro.models import ProUser


def has_account(request):
    try:
        return ProUser.objects.all().filter(user=request.user).first().account
    except AttributeError:
        return False


def get_account(request):
    try:
        return ProUser.objects.all().filter(user=request.user).first().account
    except AttributeError:
        raise AttributeError(
            "Logged in user does not have a pro user account associated. "
            "Please associate one or login as another user."
        )
