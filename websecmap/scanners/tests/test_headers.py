from requests.structures import CaseInsensitiveDict

from websecmap.scanners.scanner.security_headers import get_headers, prepare_headers_for_evidence, reduce_url


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
                "strict-transport-security": "max-age=63072000; includesubdomains; preload",
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
                "strict-transport-security": "max-age=31622400; " "includesubdomains",
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
            "headers": {"location": "https://tweakers.net/"},
            "protocol": "http",
            "request": 1,
            "status_code": 301,
            "url": "http://tweakers.net/",
        },
        {
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "strict-transport-security": "max-age=31536000; " "includesubdomains; preload",
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
                "Location": "https://basisbeveiliging.nl/longtest/longtest/longtest/longtest/longtest/longtest/longte"
                "st/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longt"
                "est/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longte"
                "st/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/"
                "longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/",
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

    # long paths will be truncated to 255 characters
    prepared = prepare_headers_for_evidence(example_set_4)
    assert prepared == [
        {
            "content_type": "text/html",
            "headers": {
                "location": "https://basisbeveiliging.nl/longtest/longtest/longtest/longtest/longtest/longtest/longte"
                "st/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/long"
                "test/longtest/longtest/longtest/longtest/longtest/longtest/longtest/longtest/lo",
                "strict-transport-security": "max-age=31536000; " "includesubdomains",
            },
            "protocol": "http",
            "request": 1,
            "status_code": 301,
            "url": "http://basisbeveiliging.nl/",
        },
        {
            "content_type": "text/html",
            "headers": {
                "strict-transport-security": "max-age=31536000; " "includesubdomains",
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


def test_reduce_url():
    # there are urls like this, which add random data and no value to the measurements. Remove the junk data
    # from the current url and the location header. This costs gigabytes of data.

    data = reduce_url(
        "https://adfs.avres.nl/adfs/ls/?samlrequest=lzfbtwixeix%2fyqz36lawdlcbeiiesnadiacvpptzshg3xtuzrp"
        "31llujxkw8nom86fvmttpf09stxnr0cht46qapew1qh7pvzfgxnpygk9tonicarn4u7tzadlpdbk%2fe%2bppdwf52geqiv"
        "hnhkj0ejjczizpllnfw5qz1yomorc25ozy4nocaohr1x%2feaousw35qb77brigwhncsld5v1j%2fndmgd8qwjojlxquotd"
        "fs1uzc%2bbuf2cdfqpxjlvcsbub3exypljpkuo6ihldobcqbrqpcieukuzjzvhnrzg7wgk5fhmwtmaqfwaou5lkzwlzvxei"
        "xawckjgudw1laobsadyshnsi0wl8cjm00so3b8m8%2f%2fmn%2fjr92f1%2b0pnhw%3d%3d&relaystate=a676435c468c"
        "3b44144481100827c66b149092505e75d3cb1b7dea6e969109c6&sigalg=http%3a%2f%2fwww.w3.org%2f2001%2f04"
        "%2fxmldsig-more%23rsa-sha256&signature=golunuba6latkujvx8pfo701aiuzgc39lz%2bvwo%2faj9zkwpllvchn"
        "5udpl%2f6wiucjwsg%2bfdftosgr%2f50l5knje2uaatbusyq%2ftisqulu2xvutwktlbzzhtyjlt11cbfrc8p0gztt%2f1"
        "3%2bqxwgv%2fim7d%2f%2bpdyvhz5joolysa6stvb6r4s%2bg02dpfrm18q5%2fuimc3sp2ng2e5qe2licbhkx7jchhxq%2"
        "bh8angpnb70yvjiwtwv5fexpj5g2kq5jcfjlwwmn38gw5kujmkpraxhysk0cqzfqdahenm%2f%2b2atmjtoukownu9%2bjy"
        "1pbd7nuasi7pjdrzbk8fp14kapuhbvjgxquwslsnabv49w%2f%2fsti3kackhb5cnlclui%2f9p5et%2frtx5q6vqpbkt56"
        "oqln2hdeafjhyx4ywvipg735g84tmhdvq7uupmnwcuv6yrywfjw%2bfka72o7lgjam8201akm8wvjegzsyscvstrppv53r2"
        "wzw10o8iegycf718lf0jybe6zeafjyb8xxaecbqr5ptcnxgsoze1pzgebm%2bgpjrmdq9poxactke4t4en1zblpwdbnru05"
        "ucczwtmgtttgumdl5mddwo%2bufpvbpu1fq2pzsxvy1dbuc3xphjnfxrkc0mje5ireucmqh4fuhqpqpprfnogpjhavpbasz"
        "x09ccngdjy%3d"
    )

    assert data == "https://adfs.avres.nl/adfs/ls/"

    data = reduce_url(
        "https://login.cbs.nl/realms/advuploadchannel-realm/protocol/openid-connect/auth?client_id=advanceduploadc"
        "hannel.ui&redirect_uri=https%3a%2f%2fdatabestanden.cbs.nl%2fsignin-oidc&response_type=code&scope=openid%20p"
        "rofile%20offline_access%20roles%20audc_api%3auser&code_challenge=r8anntcsv5rmkfeky0ehudkh80p8purptmyy9ta5jv"
        "w&code_challenge_method=s256&response_mode=form_post&nonce=638338305087075569.nzfizgiwogityjrjmy00zje3lthjmjk"
        "tzwrkmzk0njdinjuwyte2zmvlm2qtnwjhmc00mzuylwiyngutnmvjyzc3yzhjownl&state=cfdj8kyx_cdjihlaqwyxx6qj7yypedtz72da1"
        "rszwtbrlrypxicelousasqkaokevmef1r1jylzuwkrhhzlkkgowiakhgx49b1vdmy4yluhfmq3yw4v5hcyxunqdffludu0aowg9kn5g1kd-iu"
        "2fb7403ks_sflsgjo08idohgw4q3iallzvrppj5zkc_43d0xhl7v3zixqjtcas0aekqt_z2evur4v6reaaqkp2sf1_jl5kmdd805mjoopyxyxu"
        "6xcunvgk2dnx2sflcteavdgxi5g-s9cdmmws5kdbqlqkqgaifj5e59rweb9k-luqh6hhqex_zqnfmlol6x3sbl-0zdcglu2pipzijdb1t7v9s6"
        "8ifnoskespyif31wsosr2zkmqzejnrfiarnixotymcgyy&x-client-sku=id_netstandard2_0&x-client-ver=6.7.1.0"
    )

    assert data == "https://login.cbs.nl/realms/advuploadchannel-realm/protocol/openid-connect/auth"

    data = reduce_url(
        "https://gwz.helloid.com/relayservice/redirect/4f41b800-5424-4b7d-902f-2ed6ab3bb779?samlrequest"
        "=rvjlj9mwel7vr0c5"
        "o47thhsttljh0vkptnw2coccjva0tujs4hewll%2bpm5tnyu%2f4np7vmfpzm4k26esyd2f7gf96phdzip5vbwnjds150nsrhzahaaffkkhj%2"
        "f"
        "fldwuzpjjvvglousf6hpc8civtbodvsvnfzzlt5s97erzafkht6wjyolbdltk6wafclbkssp9mqyyo9uuevj9qp6cnqzjmoo97svhs0gv0mus6"
        "t"
        "e9druloq9biyfmcgim%2fycrmzy8udehjssie%2bjri7gikxeabzcwgdsc5px7%2bnz2waz3sqxms9nvaul3g0cmohjucvehesrd3nmlywecgk"
        "u"
        "tlsnsuplef9eupjxvfv7a8ph9xegaunpt0fvz2csl49hhzst90frphlzxhfo0t9i34%2fdvt%2byf17cmodb4shpv2isg3do1cf4ytejtfel6%"
        "2"
        "ffrpuw7hoer6s7f6neqvhanbtkmvjolna5rokx%2f8uixqaaalx8zvxph5ux%2fpuhln4a&relaystate=https%3a%2f%2fintranet.gouda"
        "."
        "nl%2f&sigalg=http%3a%2f%2fwww.w3.org%2f2001%2f04%2fxmldsig-more%23rsa-sha256&signature=guusgq%2fc769uyxeeoa%2b"
        "u"
        "ckue%2bedhmmlrp31sdf6fvmkciulzzg6zffu9kcrs4t7ntqpm0buf1jo2v%2faazuuvefz5kxqrhd7aw3aq8erjl2lsyqutn3nqbhaljaxgny"
        "u"
        "73i6e27y8zrmcarwozv6qy2wan4fxc%2fyvabhfouj%2b4kz0odro2nqp5bg%2bumipckvn3trsvybcbizdc43kutufv%2fgzl3dzro8wnroan"
        "5"
        "jhkvllyi5aksabucmpra1%2fxkffxeaawfj3v8%2fdxxwo8%2fvsotu%2ffvs1kyyiyn9wmnzgymhe79w0x7yh0k7sink9fyloyywihevcx%2f"
        "u"
        "wziffygddxr8hnfnlp7%2balmref8%2fsphmy7po1hwkrtre4x6ssqxavwfx0cbany9m%2fgtww%2b3tobqslht%2b3dvlxuagbc2vyptnpbao"
        "d"
        "15l5he9ajrjjfhegr2lx7h%2befhjuq70mybdzy84bfaz3wdqvegp5g8twaw4dzs3vngaga%2boevigmouikryhkljd%2b4f%2bqa9p83mr%2f"
        "o"
        "%2bwdq1lxjx0dudo9b3muubzuozcvsjljbaevtmndwdvnxf6tvmol1cwetsyhh0nznaz8gb5hcwcsdiy3arip4%2fxjkmhdootcklcbmldbpcw"
        "r"
        "apzf%2fzd90eb%2bnjrg%2bgd4ssvehswgmiswi9zhkj28dp4%3d"
    )

    assert data == "https://gwz.helloid.com/relayservice/redirect/<GUID>"

    # and error situations
    assert reduce_url("https://") == "https://"
    assert reduce_url("nonsense") == ""
    assert reduce_url("") == ""
