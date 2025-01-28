"""Import modules containing tasks that need to be auto-discovered by Django Celery."""

from websecmap.map import prepare_caches
from websecmap.map.logic import MapFlow, openstreetmap

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [openstreetmap, MapFlow, prepare_caches]
