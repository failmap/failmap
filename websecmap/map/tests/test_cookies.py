from websecmap.map.logic.cookies import get_cookie_database
from websecmap.scanners.models import ProductCookieIndicator, CookiePurpose, Product, ProductVendor


def test_get_cookie_database(db):
    v = ProductVendor.objects.create(name="Google")
    p = Product.objects.create(
        name="Google Analytics",
        vendor=v,
    )

    p2 = Product.objects.create(
        name="OWA",
    )
    marketing_cookie = CookiePurpose.objects.create(name="marketing")
    session_cookie = CookiePurpose.objects.create(name="session")

    ProductCookieIndicator.objects.create(match_name="_gat?", product=p, most_significant_purpose=marketing_cookie)
    ProductCookieIndicator.objects.create(
        match_name="cookieTest", match_path="/owa/auth.*", product=p2, most_significant_purpose=session_cookie
    )

    # add a link
    ProductCookieIndicator.objects.create(
        match_name="marco_v",
        product=p2,
        match_path="/dutyfree/indicator.*",
        cookiedatabase_link="http://example.com",
    )

    data = get_cookie_database()

    assert data == [
        {
            "cookie_database_link": None,
            "most_significant_purpose": "marketing",
            "notes": None,
            "product_id": 1,
            "product_vendor_id": 1,
        },
        {
            "cookie_database_link": None,
            "most_significant_purpose": "session",
            "notes": None,
            "product_id": 2,
            "product_vendor_id": None,
        },
        {
            "cookie_database_link": "http://example.com",
            "most_significant_purpose": None,
            "notes": None,
            "product_id": 2,
            "product_vendor_id": None,
        },
    ]
