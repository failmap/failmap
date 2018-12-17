from django.shortcuts import render
from django.http import JsonResponse
from failmap.app.common import JSEncoder


# Create your views here.
def dummy(request):
    return JsonResponse({'hello': 'world'}, encoder=JSEncoder)
