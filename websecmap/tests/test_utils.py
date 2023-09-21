import pytest
from websecmap.utils import normalize_cookies


@pytest.mark.parametrize(
    ["cookie_name", "normalized_name"],
    [
        ("_ga_DDX3XHWBGV", "_ga_<HASH_OR_ID>"),
        ("_gat_DDX3XHWBGV", "_gat_<HASH_OR_ID>"),
        ("_gat_gtag_DDX3XHWBGV", "_gat_gtag_<HASH_OR_ID>"),
        ("e293e37a8657a5203fd8d2383bbce5fc", "<HASH_OR_ID>"),
        ("_pk_id.1653.11aa", "_pk_id.<HASH_OR_ID>"),
        ("_pk_ses.1653.11aa", "_pk_ses.<HASH_OR_ID>"),
        ("_gat_gtag_UA_10299829_1", "_gat_gtag_UA_<HASH_OR_ID>"),
        (".AspNetCore.Correlation.nmLTIv-UuaX5rPA3BnBc64Qitn0HR5mGqcd_muk0sF4", ".AspNetCore.Correlation.<HASH_OR_ID>"),
        (
            (
                ".AspNetCore.OpenIdConnect.Nonce.x8rSTW4fqQc3agfqKgGeyDOmCq09Yz3M4UgqxPY5gAzNDnHMOL2KEbdmMiFO7rRzI8HVT"
                "uzbLR3-aqSi8dWMkhMYUlMf_auLJhbWRoQ2hHyLZCPtYRPINcni5Lhp0DyW4vli7jzc4NJ5n0M2IUd2OAo-21faDxRvsc4QUBPYka"
                "il3OGNxkaxoDrnWtmwjTswJErCfVFcWzqhBuYWmtL-8YG2F9jssTzjlVMbM1WMDqxUwQiUK-NxP_h-PumQkEGv"
            ),
            ".AspNetCore.OpenIdConnect.Nonce.<HASH_OR_ID>",
        ),
        (
            "AzureAppProxyAnalyticCookie_4c561a1f-bdad-4fe6-ba33-3949517ca555_https_1.3",
            "AzureAppProxyAnalyticCookie_<HASH_OR_ID>",
        ),
        (
            (
                "AzureAppProxyPreauthSessionCookie_4c561a1f-bdad-4fe6-ba33-3949517ca555_294ce288-78e6-4bfa-b736-8fadff9"
                "ed971_1.4"
            ),
            "AzureAppProxyPreauthSessionCookie_<HASH_OR_ID>",
        ),
        ("Saml2.goVTkXJvVhI0lNwJgngKcRwm", "Saml2.<HASH_OR_ID>"),
        (
            "OpenIdConnect.nonce.kzDEHaz4AKbDiZ%2BDdw2%2BXViHODmXi3ldmxClXw%2F89Us%3D",
            "OpenIdConnect.nonce.<HASH_OR_ID>",
        ),
        ("nSGt-134EAA4C0BD1583575759B239DEEE99141B19B9B10C4C201", "nSGt-<HASH_OR_ID>"),
        ("1658303577httpsomgevingsvisiev3openstaddenhaagnl.sid", "<HASH_OR_ID>.sid"),
        ("1660636313alleplannenlaakhavensbepaaltdenhaagnl.csrf", "<HASH_OR_ID>.csrf"),
        ("ppms_privacy_1a1ec43b-059b-4a78-ba48-8f833800b51a", "ppms_privacy_<HASH_OR_ID>"),
        ("SSESSc5b70dc2725dd7d74b51241a8e9101ca", "SSESS<HASH_OR_ID>"),
        ("HASH_f22ec9e4d7950995481154d42eb2d9d6", "HASH_<HASH_OR_ID>"),
        (".AspNetCore.Antiforgery.UviOjTP2a_A", ".AspNetCore.Antiforgery.<HASH_OR_ID>"),
        ("__Host-.csrf.15hl-806r7fnj", "__Host-.csrf.<HASH_OR_ID>"),
        # this name should not be affected by the normalization
        ("_ga_", "_ga_"),
    ],
)
def test_normalize_cookies(cookie_name, normalized_name):
    """Expect cookie_name to result into exactly normalized_name."""
    assert normalize_cookies([{"name": cookie_name}])[0]["name"] == normalized_name


@pytest.mark.parametrize(
    "cookie_names",
    [
        ("_gs_id.1330.8585", "_gs_id.1330.0ffc"),
        ("IPCZQX035ce08336", "IPCZQX0308803348"),
        ("_sp_id.82d8", "_sp_id.e415"),
        ("TS01bb53a3", "TS01007049", "TS01b3aefd001"),
        ("ASPSESSIONIDAERDBRSB", "ASPSESSIONIDAERDBRSA"),
        ("JSESSIONID.a2cbf836", "JSESSIONID.a2cbf83a"),
        ("visid_incap_1579411", "visid_incap_793284"),
        ("rvtoken.556fe961fa1944ad96d4ea9db1753e81", "rvtoken.556fe961fa1944ad96d4ea9db1753e82"),
        ("prism_610139906", "prism_66764472"),
        (
            "openvpn_sess_9fb5e59f35af6a2d7bbf037853232cda",
            "openvpn_sess_Qex89jTKoM4BYbyWMF1ad2oHsjOf_3XOPKOzcuTbt0aoDrRhdClAobQ9k6PCkGaNkOhQd1qXL5BqBCWWiQL42g",
        ),
        ("oclqv4lv0d1x", "ocmmgx37c199"),
        ("mod_auth_openidc_state_IG_4u5yFpnEeDSqEwR4opQtg9MA", "mod_auth_openidc_state_IG_4u5yFpnEeDSqEwR4opQtg9Mb"),
        ("mod_auth_openidc_state_e2LGB0zD6IxkGs0kxCKZQaB2mha", "mod_auth_openidc_state_e2LGB0zD6IxkGs0kxCKZQaB2mhY"),
        ("incap_ses_763_1579411", "incap_ses_765_793284"),
        ("bolt_session_b12cbddd67c415a20118618e4c211c98", "bolt_session_bc0f4f8864b382644f587729d5353d40"),
        ("ad_session_id_ZMWFORMS8883", "ad_session_id_ZMWPROD8995"),
        ("_zammad_session_82ba4702560", "_zammad_session_a138cfd0f37"),
        ("_sp_ses.82d8", "_sp_ses.901f"),
        ("_oauth2_proxy_csrf_njxiQdaN", "_oauth2_proxy_csrf_or8xysux"),
        ("_gs_ses.1330.8585", "_gs_ses.1330.ba76"),
        ("_dc_gtm_UA-5620843-32", "_dc_gtm_UA-6107853-29"),
        (
            "__RequestVerificationToken_L0xpdmUvV2ViQWRtaW41",
            "__RequestVerificationToken_L0xvZ2lu0",
            "__RequestVerificationToken_L1BvcnRhbA2",
        ),
        ("__Host-.nonce.h012wgx1dbl45dgmzw305mx-tn", "__Host-.nonce.sxq2jtbqpj64c2y57znpxh8vfs"),
        ("__Host-.AFAS.STS.Session.FHD64C1GBQ-L7GJSP-C6HP23P4", "__Host-.AFAS.STS.Session.H5JD5XT8RR3339716-0GDNXP88"),
        ("TempState-1e8e6199-7d34-40c4-95a9-63418b799618", "TempState-4cd069e4-4fac-4aba-b2c5-f91adb4092b7"),
        ("SSPOperationId_5c4d52ec", "SSPOperationId_5f7a31ea"),
        ("ROUTEID.0e9f56dedc1c6a43ee0c263a6d1b336b", "ROUTEID.395ae16da82d466e7ab5b8ade0a0c3ad"),
        ("Queue-it-57add9eb-7fdf-46d1-806f-a13994350445", "Queue-it-e3e6e7fa-7f87-4756-a82a-7ab7486a7aad"),
        (
            "OAMRequestContext_auth.dictu.nl_443_4a6456",
            "OAMRequestContext_auth20.dictu.nl_443_4c7466",
            "OAMRequestContext_tba.werk.nl_443_667a57",
        ),
        ("MSISContext632541db-a3d8-4751-8fea-130e3010fe19", "MSISContext7aa9ad6e-5f2e-4019-a892-7051fc4f3fcd"),
        ("LFR_SESSION_STATE_20105", "LFR_SESSION_STATE_20119"),
        (
            "Kpn.Malware.Correlation._M10nKOt19IbwqfbST7VR44RJw_s9lhWpTadHey2y1c",
            "Kpn.Malware.Correlation.dDl36ZoNvlA-J25oLtnNgi1vOejIpvJobfdweOUa6zQ",
        ),
        (
            "Kpn.Netflix.Correlation.uy5v_woyixoOkj1jHsjPbH-XZGQ5hoJDogUoXbjkxjk",
            "Kpn.Netflix.Correlation.uy5v_woyixoOkj1jHsjPbH-XZGQ5hoJDogUoXbjkxja",
        ),
        ("HASH_ROUTEID.0e9f56dedc1c6a43ee0c263a6d1b336b", "HASH_ROUTEID.0e9f56dedc1c6a43ee0c263a6d1b336a"),
        ("CMSSESSIDb73de2635935", "CMSSESSIDca80f1f1446d", "CMSSESSIDd01f64ae"),
        ("ASP.NET_SessionId_ClassPortal_MinVenJ.Production", "ASP.NET_SessionId_ClassPortal_NIFP.Production"),
        ("APSWMCOOKIE_ac0a6cb252291b4b92831680be29c852", "APSWMCOOKIE_c9ae690e97763fcff94c04bf7e9335b2"),
        ("AMCVS_ED8D65E655FAC7797F000101%40AdobeOrg", "AMCVS_6B4320E8637BE4D40A495FD6%40AdobeOrg"),
        ("AMCV_6B4320E8637BE4D40A495FD6%40AdobeOrg", "AMCV_6B4320E8637BE4D40A495FD6%40AdobeOrg"),
        ("211505_chosenView", "216256_chosenView"),
    ],
)
def test_normalize_cookies_dedup(cookie_names):
    """Easier way to specify cookie names than `test_normalize_cookies`, just
    provide a set of 2 or more names that should deduplicate to one name."""
    cookies = [{"name": n} for n in cookie_names]
    names = {c["name"] for c in normalize_cookies(cookies)}
    assert len(names) == 1


@pytest.mark.parametrize(
    "cookie_names",
    [
        ("AMCVS_ED8D65E655FAC7797F000101%40AdobeOrg", "AMCV_6B4320E8637BE4D40A495FD6%40AdobeOrg"),
    ],
)
def test_normalize_cookies_no_dedup(cookie_names):
    """Easier way to specify cookie names than `test_normalize_cookies`, just
    provide a set of 2 or more names that should _not_ deduplicate to one name."""
    cookies = [{"name": n} for n in cookie_names]
    names = {c["name"] for c in normalize_cookies(cookies)}
    assert len(names) == len(cookie_names)
