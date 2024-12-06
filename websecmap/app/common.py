import datetime

from celery.result import ResultBase
import simplejson
import logging

log = logging.getLogger(__name__)


# Note that the variable "o" is mandatory
class ResultEncoder(simplejson.JSONEncoder):
    """JSON encoder that serializes results from celery tasks."""

    def default(self, o: ResultBase | BaseException):
        if isinstance(o, Exception):
            log.debug("Result is exception:", exc_info=True)
            error = {"error": o.__class__.__name__, "message": str(o)}
            if o.__cause__:
                error["cause"] = self.default(o.__cause__)
            return error

        return super().default(o)


class JSEncoder(simplejson.JSONEncoder):
    """JSON encoder to serialize results to be consumed by Javascript web apps."""

    def default(self, o):
        # convert python datetime objects into a standard parsable by javascript
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        if isinstance(o, datetime.date):
            return o.isoformat()
        if isinstance(o, datetime.timedelta):
            return (datetime.datetime.min + o).time().isoformat()

        return super().default(o)
