from django.shortcuts import render


# Create your views here.
def index(request):
    """
    The map is simply a few files that are merged by javascript on the client side.
       We're not using the Django templating engine since it's a very poor way to develop a website.

    :param request:
    :return:
    """

    # now return the rendered template, it takes the wrong one... from another thing.
    return render(request, 'map/templates/index.html')
