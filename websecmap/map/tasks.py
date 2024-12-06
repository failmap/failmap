"""Import modules containing tasks that need to be auto-discovered by Django Celery."""

from websecmap.map.logic import openstreetmap, MapFlow
from websecmap.map import prepare_caches

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [openstreetmap, MapFlow, prepare_caches]
