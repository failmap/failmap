import datetime
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
        else:
            return super(ResultEncoder, self).default(value)


class JSEncoder(json.JSONEncoder):
    """JSON encoder to serialize results to be consumed by Javascript web apps."""

    def default(self, obj):
        # convert python datetime objects into a standard parsable by javascript
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return (datetime.datetime.min + obj).time().isoformat()
        else:
            return super(JSEncoder, self).default(obj)
