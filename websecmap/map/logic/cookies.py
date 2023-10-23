from websecmap.scanners.models import ProductCookieIndicator


def get_cookie_database():
    # Return as lookup table, saves time and easy to convert to a list when needed.
    # Get as much stuff as possible to make the cookie metric more interesting. This re\quires fetching some more
    # stuff from cookie database and a more careful making of notes. Probably notes wont make the cut.
    indicator = ProductCookieIndicator.objects.all().prefetch_related(
        "product", "product__vendor", "most_significant_purpose"
    )

    return {
        str(i.id): {
            "cookie_database_link": i.cookiedatabase_link,
            "most_significant_purpose": i.most_significant_purpose.name if i.most_significant_purpose else None,
            "notes": i.notes,
            "product_id": i.product.id if i.product else None,
            "product_vendor_id": i.product.vendor.id if i.product.vendor else None,
        }
        for i in indicator
    }
