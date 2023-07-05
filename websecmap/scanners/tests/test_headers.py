from requests.structures import CaseInsensitiveDict

import websecmap
from websecmap.scanners.scanner.security_headers import get_headers, prepare_headers_for_evidence


def test_CaseInsensitiveDict():
    # Headers are case insensitive, the request library has this awesome thing to work with that without altering
    # any checking logic. This verifies that the object does wat it promises.

    z = CaseInsensitiveDict()
    z["TEST"] = 1
    z["second_test"] = 2

    assert z["tesT"] == 1
    assert z["SeCoNd_TeSt"] == 2

    assert "TeSt" in z
    assert "teST" in z.keys()
    assert "nonsense" not in z.keys()
    assert "test2" not in z.keys()
    assert "test2" not in z


def test_get_headers(requests_mock):
    # Should just work with broken headers, but now seeing an MissingHeaderBodySeparatorDefect warning
    # probably the warning is just ignored, It's not trivial to simulate.
    # https://gvo.schiedam.nl
    broken_headers = {"Access-Control-Allow-Origin : https://gvo.schiedam.nl": "", "X-XSS-Protection": "1; mode=block"}
    requests_mock.get("", text="1", headers=broken_headers)

    data = get_headers("https://gvo.schiedam.nl", host="gvo.schiedam.nl")

    assert data == [
        {
            "request": 1,
            "status_code": 200,
            "url": "https://gvo.schiedam.nl/",
            "protocol": "https",
            "content_type": "unknown",
            "headers": {
                "Access-Control-Allow-Origin : https://gvo.schiedam.nl": "",
                "X-XSS-Protection": "1; mode=block",
            },
        }
    ]


def fake_timeout(*args, **kwargs):
    raise TimeoutError("Retrieving header took too long.")


def test_get_headers_slow_download(monkeypatch, caplog):
    # the timeout stuff is tested elsewhere, just raise the timeout and verify that things happen as planned
    monkeypatch.setattr(websecmap.scanners.scanner.security_headers, "get_headers_timed", fake_timeout)

    data = get_headers("https://example.nl", host="")
    assert data is False
    assert "TimeoutError" in caplog.text


def test_prepare_headers_for_evidence():
    example_set_1 = [
        {
            "request": 1,
            "url": "http://nu.nl/",
            "protocol": "http",
            "status_code": 301,
            "content_type": "unknown",
            "headers": CaseInsensitiveDict(
                {
                    "Server": "AkamaiGHost",
                    "Content-Length": "0",
                    "Location": "https://nu.nl/",
                    "Cache-Control": "max-age=0",
                    "Expires": "Wed, 05 Jul 2023 11:15:04 GMT",
                    "Date": "Wed, 05 Jul 2023 11:15:04 GMT",
                    "Connection": "keep-alive",
                }
            ),
        },
        {
            "request": 2,
            "url": "https://nu.nl/",
            "protocol": "https",
            "status_code": 301,
            "content_type": "unknown",
            "headers": CaseInsensitiveDict(
                {
                    "Server": "AkamaiGHost",
                    "Content-Length": "0",
                    "Location": "https://www.nu.nl/",
                    "Cache-Control": "max-age=0",
                    "Expires": "Wed, 05 Jul 2023 11:15:04 GMT",
                    "Date": "Wed, 05 Jul 2023 11:15:04 GMT",
                    "Connection": "keep-alive",
                    "Strict-Transport-Security": "max-age=31536000",
                }
            ),
        },
        {
            "request": 3,
            "url": "https://www.nu.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": CaseInsensitiveDict(
                {
                    "Content-Type": "text/html; charset=utf-8",
                    "Content-Length": "60734",
                    "Accept-CH": "sec-ch-ua-model,sec-ch-ua-platform-version",
                    "Accept-Ranges": "bytes",
                    "Content-Encoding": "gzip",
                    "Content-Security-Policy": "style-src data: 'unsafe-inline' https:; font-src data: https:; img-s"
                    "rc data: https: blob:; script-src data: 'unsafe-inline' 'unsafe-eval"
                    "' https: blob:; object-src https:; connect-src https: wss: blob:; def"
                    "ault-src data: 'unsafe-inline' 'unsafe-eval' https:; form-action http"
                    "s:; upgrade-insecure-requests; media-src data: https: blob:; child-src"
                    " data: https: blob:",
                    "Link": "<https://media.nu.nl>; rel=preconnect, <https://media.nu.nl>; rel=dns-prefetch, <https:"
                    "//myprivacy.dpgmedia.net>; rel=preconnect, <https://myprivacy.dpgmedia.net>; rel=dns-prefetch",
                    "Permissions-Policy": "ch-ua-model=*,ch-ua-platform-version=*",
                    "Server": "Skipper",
                    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "SAMEORIGIN",
                    "X-Xss-Protection": "1; mode=block",
                    "Cache-Control": "max-age=53",
                    "Expires": "Wed, 05 Jul 2023 11:15:57 GMT",
                    "Date": "Wed, 05 Jul 2023 11:15:04 GMT",
                    "Connection": "keep-alive",
                    "Vary": "Accept-Encoding",
                }
            ),
        },
    ]

    prepared = prepare_headers_for_evidence(example_set_1)
    # don't alter the original set!
    assert prepared != example_set_1
    # only headers in the allow-list are fine, everything is converted to lowercase.
    assert prepared == [
        {
            "request": 1,
            "url": "http://nu.nl/",
            "protocol": "http",
            "status_code": 301,
            "content_type": "unknown",
            "headers": {
                "location": "https://nu.nl/",
            },
        },
        {
            "request": 2,
            "url": "https://nu.nl/",
            "protocol": "https",
            "status_code": 301,
            "content_type": "unknown",
            "headers": {"location": "https://www.nu.nl/", "strict-transport-security": "max-age=31536000"},
        },
        {
            "request": 3,
            "url": "https://www.nu.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-type": "text/html; charset=utf-8",
                "content-security-policy": "style-src data: 'unsafe-inline' https:; font-src data: https:; img-src dat"
                "a: https: blob:; script-src data: 'unsafe-inline' 'unsafe-eval' https: blo"
                "b:; object-src https:; connect-src https: wss: blob:; default-src data: '"
                "unsafe-inline' 'unsafe-eval' https:; form-action https:; upgrade-insecure-"
                "requests; media-src data: https: blob:; child-src data: https: blob:",
                "link": "<https://media.nu.nl>; rel=preconnect, <https://media.nu.nl>; rel=dns-prefetch, <https://mypr"
                "ivacy.dpgmedia.net>; rel=preconnect, <https://myprivacy.dpgmedia.net>; rel=dns-prefetch",
                "permissions-policy": "ch-ua-model=*,ch-ua-platform-version=*",
                "strict-transport-security": "max-age=63072000; includesubdomains; preload",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
        },
    ]

    example_set_2 = [
        {
            "request": 1,
            "url": "http://minezk.nl/",
            "protocol": "http",
            "status_code": 302,
            "content_type": "unknown",
            "headers": {"Location": "https://minezk.nl/", "Connection": "Keep-Alive", "Content-Length": "0"},
        },
        {
            "request": 2,
            "url": "https://minezk.nl/",
            "protocol": "https",
            "status_code": 302,
            "content_type": "unknown",
            "headers": {
                "Location": "https://www.rijksoverheid.nl/ministeries/ministerie-van-economische-zaken-en-klimaat",
                "Connection": "Keep-Alive",
                "Content-Length": "0",
            },
        },
        {
            "request": 3,
            "url": "https://www.rijksoverheid.nl/ministeries/ministerie-van-economische-zaken-en-klimaat",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html;charset=utf-8",
            "headers": {
                "Server": "nginx",
                "Date": "Wed, 05 Jul 2023 11:12:31 GMT",
                "Content-Type": "text/html;charset=UTF-8",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
                "Vary": "Accept-Encoding, Origin",
                "content-security-policy": "default-src 'self'; base-uri 'self'; script-src 'self' "
                "'nonce-Mzg5YzE1OGIwYTRhNGJkNjhkZjE0ODA1ZDMxZDkzMzA=' *.platformrijk"
                "soverheid.nl *.rijksoverheid.nl *.contenttoolsrijksoverheid.nl; sty"
                "le-src 'self' 'unsafe-inline' statistiek.rijksoverheid.nl *.content"
                "toolsrijksoverheid.nl *.rijksoverheid.nl; font-src 'self' statistie"
                "k.rijksoverheid.nl; object-src 'none'; connect-src *.platformrijksov"
                "erheid.nl *.rijksoverheid.nl *.contenttoolsrijksoverheid.nl *.rovid."
                "nl *.rijksoverheidsvideo.nl; img-src 'self' data: d3oiud1b8fohdw.clo"
                "udfront.net statistiek.rijksoverheid.nl *.rovid.nl *.rijksoverheids"
                "video.nl *.toegankelijkheidsverklaring.nl; media-src 'self' *.rovid"
                ".nl *.rijksoverheidsvideo.nl; form-action 'self' export.highcharts."
                "com *.contenttoolsrijksoverheid.nl *.rijksoverheid.nl; frame-ancest"
                "ors 'none'; upgrade-insecure-requests",
                "X-Content-Type-Options": "nosniff",
                "X-XSS-Protection": "1; mode=block",
                "X-Frame-Options": "DENY",
                "Strict-Transport-Security": "max-age=31622400; includeSubDomains",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Content-Encoding": "gzip",
                "X-Cache-Status": "EXPIRED:EXPIRED",
                "X-Via": "21:2:8",
            },
        },
    ]
    prepared = prepare_headers_for_evidence(example_set_2)
    assert prepared == [
        {
            "content_type": "unknown",
            "headers": {"location": "https://minezk.nl/"},
            "request": 1,
            "status_code": 302,
            "url": "http://minezk.nl/",
            "protocol": "http",
        },
        {
            "content_type": "unknown",
            "headers": {
                "location": "https://www.rijksoverheid.nl/ministeries/ministerie-van-economische-zaken-en-klimaat"
            },
            "request": 2,
            "status_code": 302,
            "url": "https://minezk.nl/",
            "protocol": "https",
        },
        {
            "content_type": "text/html;charset=utf-8",
            "headers": {
                "content-security-policy": "default-src 'self'; base-uri 'self'; "
                "script-src 'self' "
                "'nonce-mzg5yze1ogiwytrhngjknjhkzje0oda1zdmxzdkzmza=' "
                "*.platformrijksoverheid.nl "
                "*.rijksoverheid.nl "
                "*.contenttoolsrijksoverheid.nl; "
                "style-src 'self' 'unsafe-inline' "
                "statistiek.rijksoverheid.nl "
                "*.contenttoolsrijksoverheid.nl "
                "*.rijksoverheid.nl; font-src 'self' "
                "statistiek.rijksoverheid.nl; "
                "object-src 'none'; connect-src "
                "*.platformrijksoverheid.nl "
                "*.rijksoverheid.nl "
                "*.contenttoolsrijksoverheid.nl "
                "*.rovid.nl *.rijksoverheidsvideo.nl; "
                "img-src 'self' data: "
                "d3oiud1b8fohdw.cloudfront.net "
                "statistiek.rijksoverheid.nl "
                "*.rovid.nl *.rijksoverheidsvideo.nl "
                "*.toegankelijkheidsverklaring.nl; "
                "media-src 'self' *.rovid.nl "
                "*.rijksoverheidsvideo.nl; "
                "form-action 'self' "
                "export.highcharts.com "
                "*.contenttoolsrijksoverheid.nl "
                "*.rijksoverheid.nl; frame-ancestors "
                "'none'; upgrade-insecure-requests",
                "content-type": "text/html;charset=utf-8",
                "referrer-policy": "strict-origin-when-cross-origin",
                "strict-transport-security": "max-age=31622400; " "includesubdomains",
                "x-content-type-options": "nosniff",
                "x-frame-options": "deny",
                "x-xss-protection": "1; mode=block",
            },
            "protocol": "https",
            "request": 3,
            "status_code": 200,
            "url": "https://www.rijksoverheid.nl/ministeries/ministerie-van-economische-zaken-en-klimaat",
        },
    ]

    example_set_3 = [
        {
            "request": 1,
            "url": "http://tweakers.net/",
            "protocol": "http",
            "status_code": 301,
            "content_type": "text/html",
            "headers": {
                "Content-Type": "text/html",
                "Date": "Wed, 05 Jul 2023 11:13:15 GMT",
                "Location": "https://tweakers.net/",
                "Connection": "Keep-Alive",
                "Content-Length": "0",
            },
        },
        {
            "request": 2,
            "url": "https://tweakers.net/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "Server": "Apache",
                "Vary": "Accept-Encoding",
                "Cache-Control": "max-age=0, private",
                "Content-Type": "text/html; charset=UTF-8",
                "X-Tweakers-Server": "twk-eun-web2",
                "Content-Encoding": "gzip",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
                "Content-Security-Policy": "default-src https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
                "form-action https:; frame-ancestors tweakers.net *.tweakers.net",
                "Date": "Wed, 05 Jul 2023 11:13:16 GMT",
                "Keep-Alive": "timeout=10, max=149",
                "Expires": "-1",
                "X-XSS-Protection": "1; mode=block",
                "Transfer-Encoding": "chunked",
                "X-Content-Type-Options": "nosniff",
                "Connection": "Keep-Alive",
                "Set-Cookie": "__Secure-TnetID=.0ZdK0B4QtkP7v2D-eknf8oUGXuZNPToh; expires=Sun, 09-Jul-2023"
                " 11:13:16 GMT; Max-Age=345600; path=/; domain=.tweakers.net; secure; "
                "SameSite=Lax, ssa-did=fceaee99-3afa-494b-968d-026642cb8942; expires=Fri, "
                "05 Jul 2024 11:13:16 GMT; Max-Age=31622400; path=/; domain=.tweakers.net; "
                "secure; httponly; samesite=lax, ssa-sid=75e8614e-3aa4-4556-b6d5-c24f2a07d41a; "
                "expires=Wed, 05 Jul 2023 11:43:16 GMT; Max-Age=1800; path=/; domain=.tweakers.net; "
                "secure; httponly; samesite=lax",
                "X-Clacks-Overhead": "GNU Terry Pratchett, Yoeri Lauwers, Arie Jan Stapel",
            },
        },
    ]
    prepared = prepare_headers_for_evidence(example_set_3)
    assert prepared == [
        {
            "content_type": "text/html",
            "headers": {"content-type": "text/html", "location": "https://tweakers.net/"},
            "protocol": "http",
            "request": 1,
            "status_code": 301,
            "url": "http://tweakers.net/",
        },
        {
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-security-policy": "default-src https: data: blob: "
                "'unsafe-inline' 'unsafe-eval'; "
                "form-action https:; frame-ancestors "
                "tweakers.net *.tweakers.net",
                "content-type": "text/html; charset=utf-8",
                "strict-transport-security": "max-age=31536000; " "includesubdomains; preload",
                "x-clacks-overhead": "gnu terry pratchett, yoeri lauwers, arie " "jan stapel",
                "x-content-type-options": "nosniff",
                "x-xss-protection": "1; mode=block",
            },
            "protocol": "https",
            "request": 2,
            "status_code": 200,
            "url": "https://tweakers.net/",
        },
    ]

    example_set_4 = [
        {
            "request": 1,
            "url": "http://basisbeveiliging.nl/",
            "protocol": "http",
            "status_code": 301,
            "content_type": "text/html",
            "headers": {
                "Server": "nginx",
                "Date": "Wed, 05 Jul 2023 11:14:24 GMT",
                "Content-Type": "text/html",
                "Content-Length": "178",
                "Connection": "keep-alive",
                "Location": "https://basisbeveiliging.nl/",
                "Expires": "Wed, 05 Jul 2023 11:24:23 GMT",
                "Cache-Control": "max-age=599",
                "Strict-Transport-Security": "max-age=31536000; includeSubdomains",
                "X-XSS-Protection": "1; mode=block",
                "X-Frame-Options": "SAMEORIGIN",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "X-Clacks-Overhead": "GNU Terry Pratchett",
            },
        },
        {
            "request": 2,
            "url": "https://basisbeveiliging.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html",
            "headers": {
                "Server": "nginx",
                "Date": "Wed, 05 Jul 2023 11:14:24 GMT",
                "Content-Type": "text/html",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
                "Vary": "Accept-Encoding",
                "Last-Modified": "Mon, 03 Jul 2023 12:15:48 GMT",
                "ETag": 'W/"64a2bbf4-58a"',
                "Expires": "Wed, 05 Jul 2023 11:24:23 GMT",
                "Cache-Control": "max-age=599",
                "Strict-Transport-Security": "max-age=31536000; includeSubdomains",
                "X-XSS-Protection": "1; mode=block",
                "X-Frame-Options": "SAMEORIGIN",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "X-Clacks-Overhead": "GNU Terry Pratchett",
                "Content-Encoding": "gzip",
            },
        },
    ]
    prepared = prepare_headers_for_evidence(example_set_4)
    assert prepared == [
        {
            "content_type": "text/html",
            "headers": {
                "content-type": "text/html",
                "location": "https://basisbeveiliging.nl/",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000; " "includesubdomains",
                "x-clacks-overhead": "gnu terry pratchett",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
            "protocol": "http",
            "request": 1,
            "status_code": 301,
            "url": "http://basisbeveiliging.nl/",
        },
        {
            "content_type": "text/html",
            "headers": {
                "content-type": "text/html",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000; " "includesubdomains",
                "x-clacks-overhead": "gnu terry pratchett",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
            "protocol": "https",
            "request": 2,
            "status_code": 200,
            "url": "https://basisbeveiliging.nl/",
        },
    ]

    # now have no headers:
    example_set_5 = [
        {
            "request": 1,
            "url": "http://basisbeveiliging.nl/",
            "protocol": "http",
            "status_code": 301,
            "content_type": "text/html",
            "headers": {},
        },
    ]
    prepared = prepare_headers_for_evidence(example_set_5)
    assert prepared == [
        {
            "content_type": "text/html",
            "headers": {},
            "protocol": "http",
            "request": 1,
            "status_code": 301,
            "url": "http://basisbeveiliging.nl/",
        },
    ]
