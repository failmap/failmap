"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
from failmap.map import geojson

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [geojson]
