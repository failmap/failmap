import json


class ResultEncoder(json.JSONEncoder):
    """JSON encoder that serializes results from celery tasks."""

    def default(self, value):
        if isinstance(value, Exception):
            error = {
                'error': value.__class__.__name__,
                'message': str(value)
            }
            if value.__cause__:
                error['cause'] = self.default(value.__cause__)
            return error
