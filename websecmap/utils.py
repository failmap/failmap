"""Utility functions that can work outside of Django"""

import re
import sys

# simple normalizations, a prefix, followed by a unique hash or id, first
# capture group stays, second capture group is replaced
COOKIE_NORMALIZATIONS = [
    # google analytics
    r"(?P<keep>_ga(t)?(_gtag)?(_UA)?_)(?P<replace>.+)",
    # bare hash
    r"(?P<replace>[a-zA-Z0-9]{32})",
    r"(?P<keep>_pk_(id|ses|ref)\.)(?P<replace>.+)",
    r"(?P<keep>\.AspNetCore\.(OpenIdConnect\.Nonce|Correlation|Antiforgery)\.)(?P<replace>.+)",
    r"(?P<keep>Saml2\.)(?P<replace>.+)",
    r"(?P<keep>OpenIdConnect\.nonce\.)(?P<replace>.+)",
    r"(?P<keep>AzureAppProxy[A-Za-z]+_)(?P<replace>.+)",
    r"(?P<keep>nSGt-)(?P<replace>.+)",
    r"(?P<replace>.+)(?P<keep>\.(sid|csrf))",
    r"(?P<keep>ppms_privacy_)(?P<replace>.+)",
    r"(?P<keep>SSESS)(?P<replace>[a-zA-Z0-9]{32})",
    r"(?P<keep>HASH_)(?P<replace>[a-zA-Z0-9]{32})",
    r"(?P<keep>__Host-\.csrf\.)(?P<replace>.+)",
    r"(?P<keep>TS)(?P<replace>[a-zA-Z0-9]{8,11})",
    r"(?P<keep>_sp_id\.)(?P<replace>.+)",
    r"(?P<keep>IPC)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>_gs_id\.)(?P<replace>.+)",
    r"(?P<keep>ASPSESSIONID)(?P<replace>.+)",
    r"(?P<keep>JSESSIONID\.)(?P<replace>.+)",
    r"(?P<replace>.+)(?P<keep>(_chosenView))",
    r"(?P<keep>AMCV(S)?_)(?P<replace>.+)",
    r"(?P<keep>APSWMCOOKIE_)(?P<replace>.+)",
    r"(?P<keep>ASP\.NET_SessionId_ClassPortal_)(?P<replace>.+)",
    r"(?P<keep>CMSSESSID)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>HASH_ROUTEID\.)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>OAMRequestContext_)(?P<replace>[a-zA-Z0-9\._-]+)",
    r"(?P<keep>Kpn\.[a-zA-Z]+\.Correlation\.)(?P<replace>[a-zA-Z0-9_-]+)",
    r"(?P<keep>MSISContext)(?P<replace>[a-zA-Z0-9-]+)",
    r"(?P<keep>Queue-it-)(?P<replace>[a-zA-Z0-9-]+)",
    r"(?P<keep>TempState-)(?P<replace>[a-zA-Z0-9-]+)",
    r"(?P<keep>__Host-\.(AFAS\.STS\.Session|nonce)\.)(?P<replace>[a-zA-Z0-9-]+)",
    r"(?P<keep>_dc_gtm_UA-)(?P<replace>[a-zA-Z0-9-]+)",
    r"(?P<keep>ROUTEID\.)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>__RequestVerificationToken_)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>SSPOperationId_)(?P<replace>[a-zA-Z0-9]+)",
    r"(?P<keep>LFR_SESSION_STATE_)(?P<replace>[0-9]+)",
    r"(?P<keep>(_gs_ses|_sp_ses)\.)(?P<replace>[a-z0-9\.]+)",
    r"(?P<keep>_zammad_session_)(?P<replace>[a-z0-9]+)",
    r"(?P<keep>bolt_session_)(?P<replace>[a-z0-9]+)",
    r"(?P<keep>incap_ses_)(?P<replace>[0-9_]+)",
    r"(?P<keep>prism_)(?P<replace>[0-9]+)",
    r"(?P<keep>visid_incap_)(?P<replace>[0-9]+)",
    r"(?P<keep>mod_auth_openidc_state_(IG_)?)(?P<replace>[A-Za-z0-9]+)",
    r"(?P<keep>ad_session_id_)(?P<replace>[A-Z0-9]+)",
    r"(?P<keep>_oauth2_proxy_csrf_)(?P<replace>[A-Za-z0-9]+)",
    r"(?P<keep>oc)(?P<replace>[a-z0-9]{10})",
    r"(?P<keep>openvpn_sess_)(?P<replace>[a-zA-Z0-9_]+)",
    r"(?P<keep>rvtoken\.)(?P<replace>[a-zA-Z0-9]{32})",
]


def normalize_cookie_name(cookie_name: str) -> str:
    # as long as it's just names...
    new_name = ""

    for regex in COOKIE_NORMALIZATIONS:
        match = re.match(f"^{regex}$", cookie_name)
        if not match:
            continue

        for group, value in match.groupdict().items():
            new_name += value if group == "keep" else "<HASH_OR_ID>"
        break
    else:
        return cookie_name

    return new_name


def normalize_cookies(cookies: list[dict]) -> list[dict]:
    """Remove unique hashes/id's from cookie names to make them easier to dedupe."""

    new_cookies = []
    for cookie in cookies:
        new_cookies.append({**cookie, "name": normalize_cookie_name(cookie["name"])})

    return new_cookies


if __name__ == "__main__":
    if sys.argv[1] == "normalize_cookies":
        # when given a list of cookie names in the cookie_names.txt file
        # show how much is reduced:
        # wc -l cookie_names.txt; sort -u cookie_names.txt | wc -l; sort -u cookie_names.txt | \
        # python3 -m websecmap.utils normalize_cookies | sort -u | wc -l
        # group similar length cookie names together:
        # sort -u cookie_names.txt | awk '{ print length, $0 }' | sort -n -s
        # group by length after being normalized, ignoring normalized names:
        # sort -u cookie_names.txt | python3 -m websecmap.utils normalize_cookies | grep -v HASH_OR_ID | \
        # sort -u | awk '{ print length, $0 }' | sort -n -s

        for n in normalize_cookies([{"name": n.strip()} for n in sys.stdin]):
            print(n["name"])
