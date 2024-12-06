import logging
import os

from django.db.models.query_utils import DeferredAttribute

logger = logging.getLogger(__name__)
attrs_seen = set()


def _DeferredAttribute_get(self, instance, cls=None):
    # taken from https://suor.github.io/blog/2023/03/26/ban-1-plus-n-in-django/
    # monkeys go early, settings might not be available yet
    from django.conf import settings  # pylint: disable=import-outside-toplevel

    if instance is None:
        return self
    data = instance.__dict__
    field_name = self.field.attname

    # Normally this accessor won't be called if field_name is in __dict__,
    # we need this part so that DeferredAttribute descendants with __set__ play nice.
    if field_name in data:
        return data[field_name]

    # If it's not there already then prevent an SQL query or at least notify we are doing smth bad
    attr = f"{instance.__class__.__name__}.{field_name}"
    # Only trigger this check once per attr to not flood Sentry with identical messages
    if attr not in attrs_seen:
        attrs_seen.add(attr)
        message = f"Lazy fetching of {attr} may cause 1+N issue"
        # We stop in DEBUG mode and if inside tests but let production to proceed.
        # Using LookupError instead of AttributeError here to prevent higher level "handling" this.
        if settings.DEBUG or "PYTEST_CURRENT_TEST" in os.environ:
            raise LookupError(message)

        # make sure this ends up in Sentry
        logger.exception(message)

    # Proceed normally
    return _DA_get_original(self, instance, cls)


_DA_get_original, DeferredAttribute.__get__ = DeferredAttribute.__get__, _DeferredAttribute_get
