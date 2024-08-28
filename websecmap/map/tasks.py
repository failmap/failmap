"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
from websecmap.map.logic import openstreetmap, MapFlow
from websecmap.map.prepare_caches import prepare_daily_caches_for_everything

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [openstreetmap, MapFlow, prepare_daily_caches_for_everything]
