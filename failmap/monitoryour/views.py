from django.shortcuts import render


def index(request):
    return render(request, 'monitoryour/templates/monitoryour/index.html')
