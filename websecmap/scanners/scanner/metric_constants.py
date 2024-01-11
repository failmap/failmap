# This file:
# prevents a circular import where multiple scanners refer to the same constants but need functions from each other

# Privacy Metrics:
WEB_PRIVACY_THIRD_PARTY_REQUESTS = "web_privacy_third_party_requests"
WEB_PRIVACY_THIRD_PARTY_FOUND = "web_privacy_third_party_found"
WEB_PRIVACY_THIRD_PARTY_OK = "web_privacy_third_party_ok"
WEB_PRIVACY_THIRD_PARTY_ERROR = "web_privacy_third_party_error"

WEB_PRIVACY_TRACKING = "web_privacy_tracking"
WEB_PRIVACY_TRACKING_TRACKERS_FOUND = "web_privacy_tracking_trackers_found"
WEB_PRIVACY_TRACKING_OK = "web_privacy_tracking_ok"
WEB_PRIVACY_TRACKING_ERROR = "web_privacy_tracking_error"

WEB_PRIVACY_COOKIES = "web_privacy_cookies"
WEB_PRIVACY_COOKIES_NEUTRAL = "web_privacy_cookies_neutral"
WEB_PRIVACY_COOKIES_ERROR = "web_privacy_cookies_error"

WEB_PRIVACY_THIRD_PARTY_DOMAINS = "web_privacy_third_party_domains"
WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL = "web_privacy_third_party_domains_neutral"
WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR = "web_privacy_third_party_domains_error"

# todo: rename from web_privacy_products to the new name
# This is the metric for cookies that have been received without consent. This means the user has
# not clicked on anything on the cookie dialog.
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT = "web_privacy_cookie_products_no_consent"
# neutral will be phased out
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_NEUTRAL = "neutral"
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_OK = "ok"
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_LOW = "low"
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM = "medium"
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_HIGH = "high"
# in case it was not possible to create a scan etc...
WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_ERROR = "scan_error"


# Full Crawl results, uses the same grading as web_privacy_third_party and web_privacy_cookies, as they are
# the same metrics only more complete. They are currently not fast enough to cover all sites and subdomains.
WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_WITH_CONSENT = "web_privacy_third_party_requests_crawled_with_consent"
WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_NO_CONSENT = "web_privacy_third_party_requests_crawled_no_consent"
WEB_PRIVACY_TRACKING_CRAWLED_WITH_CONSENT = "web_privacy_tracking_crawled_with_consent"
WEB_PRIVACY_TRACKING_CRAWLED_NO_CONSENT = "web_privacy_tracking_crawled_no_consent"
WEB_PRIVACY_COOKIES_CRAWLED_WITH_CONSENT = "web_privacy_cookies_crawled_with_consent"
WEB_PRIVACY_COOKIES_CRAWLED_NO_CONSENT = "web_privacy_cookies_crawled_no_consent"
