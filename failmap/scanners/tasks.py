"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
from . import scanner_dummy, scanner_security_headers, scanner_tls_qualys, scanner_http

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [scanner_tls_qualys, scanner_security_headers, scanner_dummy, scanner_http]
