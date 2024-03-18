from django.db import models
from jsonfield.fields import JSONFieldMixin
import gzip
from gzip import BadGzipFile

from websecmap.app import log


class CompressedJSONField(JSONFieldMixin, models.TextField):
    """
    This is exactly the same as a JSONField, except that the storage is compressed transparently with gzip.
    This saves a lot of space while the app stays functioning the way it does.

    GZIP might not have the best compression ratio, but the compression speed and decompression time are the best.
    The advice in the article (gzip -6 or xz -1) makes sense for this type of data.

    Compression level 4 is chosen as that's twice as fast while only losing about a percent of compression ratio.
    Some CPU speed is important and shaving off 90 or 89% at twice the CPU cost matters.

    Todo: the column needs to be bytes. How does that work in django database? -> seems to work instantly already.
    But perhaps not in postgres of mariadb. We'll see what happens during tests.

    Also tested by hand in the admin interface.
    """

    def to_python(self, value):
        try:
            # when migrating the data may not be compressed, so fallback to returning the data as json
            data = gzip.decompress(value)
        except (BadGzipFile, TypeError) as e:
            log.error("Unable to decompress data, using original: %s", e)
            data = value
        return super().to_python(data)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None

        try:
            # when migrating the data may not be compressed, so fallback to returning the data as json
            data = gzip.decompress(value)
        except (BadGzipFile, TypeError) as e:
            log.error("Unable to decompress data, using original: %s", e)
            data = value
        return super().from_db_value(data, expression, connection)

    def get_prep_value(self, value):
        string = super().get_prep_value(value)
        return gzip.compress(bytes(string, 'UTF-8'), compresslevel=4)

    def value_to_string(self, obj):
        string = super().value_to_string(obj)
        return gzip.compress(bytes(string, 'UTF-8'), compresslevel=4)
