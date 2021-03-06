// Contains fallback messages which will slowly be moved to components. In the end this contains app messages
// and things that are used in many components (which are vulnerabilities etc, which are also in app).

const messages = {
    en: {
        // new translations
        back_to_map: "Back to the map",
        week: "week",
        view_report: "View report",

        // layers
        municipality: 'Municipalities',
        cyber: 'Cyber',
        unknown: 'Unknown',
        water_board: 'Water boards',
        province: 'Provinces',
        country: 'Country',
        region: 'Region',
        county: 'County',
        district: 'District',
        government: 'Government',
        healthcare: 'Healthcare',
        finance: 'Finance',
        state: 'State',
        education: 'Education',

        // german layers... sigh... :)
        bundesland: '',
        regierungsbezirk: '',
        landkreis_kreis_kreisfreie_stadt: '',
        samtgemeinde_verwaltungsgemeinschaft: '',
        stadt_gemeinde: '',
        stadtbezirk_gemeindeteil_mit_selbstverwaltung: '',
        stadtteil_gemeindeteil_ohne_selbstverwaltung: '',

        // categories:
        confidentiality: "Confidentiality",
        integrity: "Integrity",
        website: "Website",


        // issues, are used at various places, the original value comes from the database stored as scan results.

        // DNSSEC
        "DNSSEC": "Domain name security (DNSSEC)",
        "DNSSEC is incorrectly or not configured (errors found).": "DNSSEC is incorrectly or not configured (errors found).",
        "DNSSEC seems to be implemented sufficiently.": "DNSSEC seems to be implemented sufficiently.",


        // FTP
        "ftp": "File transfer (FTP)",
        "FTP": "File transfer (FTP)", // not used?
        "FTP Insecure": "FTP insecure",
        "FTP Server only supports insecure SSL protocol.": "FTP Server only supports insecure SSL protocol.",
        "FTP Server does not configured to show if encryption is available.": "FTP Server is not configured to show if encryption is available.",
        "FTP Server supports TLS encryption protocol.": "FTP Server supports TLS encryption protocol.",
        "FTP Server does not support encrypted transport or has protocol issues.": "FTP Server does not support encrypted transport or has protocol issues.",
        "An FTP connection could not be established properly. Not possible to verify encryption.": "An FTP connection could not be established properly. Not possible to verify encryption.",


        // used at security headers
        "Stats hasn\'t": "Does not have",
        "Stats has": "Does have",


        // http_security_header_strict_transport_security
        "http_security_header_strict_transport_security": "Website: Strict-Transport-Security Header (HSTS)",
        "Strict-Transport-Security": "Strict-Transport-Security", // not used?
        "Strict-Transport-Security header present.": "Strict-Transport-Security header present.",
        "Missing Strict-Transport-Security header.": "Missing Strict-Transport-Security header.",
        "Missing Strict-Transport-Security header. Offers no insecure alternative service.": "Missing Strict-Transport-Security header. Offers no insecure alternative service.",


        // http_security_header_x_frame_options
        "http_security_header_x_frame_options": "Website: X-Frame-Options Header (Clickjacking)",
        "X-Frame-Options": "X-Frame-Options",
        "Missing X-Frame-Options header.": "Missing X-Frame-Options header.",
        "X-Frame-Options header present.": "X-Frame-Options header present.",

        "Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options Header.": "Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options Header.",


        // http_security_header_x_xss_protection
        "http_security_header_x_xss_protection": "Website: X-XSS-Protection Header",
        "X-XSS-Protection": "--test--",
        "X-XSS-Protection header present.": "X-XSS-Protection header present.",
        "Missing X-XSS-Protection header.": "Missing X-XSS-Protection header.",

        "Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.": "Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.",


        // http_security_header_x_content_type_options
        "http_security_header_x_content_type_options": "Website: X-Content-Type-Options Header",
        "X-Content-Type-Options": "X-Content-Type-Options", // not used?
        "X-Content-Type-Options header present.": "X-Content-Type-Options header present.",
        "Missing X-Content-Type-Options header.": "Missing X-Content-Type-Options header.",


        // plain_https
        "plain_https": "Missing transport encryption (HTTP only)",
        "Redirect from unsafe address": "Redirect from unsafe address",
        "Site does not redirect to secure url, and has no secure alternative on a standard port.": "Site does not redirect to secure url, and has no secure alternative on a standard port.",
        "Has a secure equivalent, which wasn't so in the past.": "Has a secure equivalent, which wasn't so in the past.",
        "Redirects to a secure site, while a secure counterpart on the standard port is missing.": "Redirects to a secure site, while a secure counterpart on the standard port is missing.",
        // this is an issue with a spelling error :)
        "Site does not redirect to secure url, and has nosecure alternative on a standard port.": "Site does not redirect to secure url, and has no secure alternative on a standard port.",
        "Not at all": "Not at all",


        // tls_qualys_encryption_quality
        "tls_qualys_encryption_quality": "Encryption Quality (HTTPS)",
        "Broken Transport Security, rated F": "Broken Transport Security, rated F",
        "Certificate not valid for domain name.": "Certificate not valid for domain name.",
        "Less than optimal Transport Security, rated C.": "Less than optimal Transport Security, rated C.",
        "Less than optimal Transport Security, rated B.": "Less than optimal Transport Security, rated B.",
        "Good Transport Security, rated A-.": "Good Transport Security, rated A-.",
        "Good Transport Security, rated A.": "Good Transport Security, rated A.",
        "Perfect Transport Security, rated A+.": "Perfect Transport Security, rated A+.",
        "TLS rated C": "TLS rated C",
        "TLS rated B": "TLS rated B",
        "TLS rated A": "TLS rated A",
        "TLS rated A-": "TLS rated A-",
        "TLS rated A+": "TLS rated A+",
        "Broken": "Broken (completely insecure)",


        // tls_qualys_certificate_trusted
        "tls_qualys_certificate_trusted": "Trust in certificate (HTTPS)",
        "not trusted": "Not trusted",
        "trusted": "Trusted",
        "Certificate is not trusted.": "Certificate is not trusted.",
        "Certificate is trusted.": "Certificate is trusted.",

        // Mail
        "dns_mx_no_cname": "E-Mail Server",

        // internet_nl_mail_starttls_tls_available
        "internet_nl_mail_starttls_tls_available": "E-Mail: Encrypted transport (STARTTLS)",
        "STARTTLS Available": "STARTTLS Available",
        "STARTTLS Missing": "STARTTLS Missing",


        // internet_nl_mail_auth_spf_exist
        "internet_nl_mail_auth_spf_exist": "E-Mail: Sender Policy Framework (SPF)",
        "SPF Available": "SPF Available",
        "SPF Missing": "SPF Missing",


        // internet_nl_mail_auth_dkim_exist
        "internet_nl_mail_auth_dkim_exist": "E-Mail: DomainKeys Identified Mail (DKIM)",
        "DKIM Available": "DKIM Available",
        "DKIM Missing": "DKIM Missing",


        // internet_nl_mail_auth_dmarc_exist
        "internet_nl_mail_auth_dmarc_exist": "E-Mail: Domain-based Message Auth (DMARC)",
        "DMARC Available": "DMARC Available",
        "DMARC Missing": "DMARC Missing",


        "Test internet_nl_mail_auth_dmarc_exist resultated in failed": "Detection and prevention of spoofing not enabled.",

    },
    nl: {
        back_to_map: "Terug naar de kaart",
        view_report: "Rapport bekijken",

        municipality: 'Gemeenten',
        cyber: 'Cyber',
        unknown: 'Onbekend',
        water_board: 'Waterschappen',
        province: 'Provincies',
        country: 'Land',
        region: 'Gebied',
        county: 'County',
        district: 'District',
        government: 'Overheid',
        healthcare: 'Gezondheidszorg',
        finance: 'Financiën',
        state: 'Staat',
        education: 'Scholen',


        // categories:
        confidentiality: "Vertrouwelijkheid",
        integrity: "Integriteit",
        website: "Website",


        // issues, are used at various places, the original value comes from the database stored as scan results.

        // DNSSEC
        "DNSSEC": "Domeinnaam beveiliging (DNSSEC)",
        "DNSSEC is incorrectly or not configured (errors found).": "DNSSEC is niet of niet juist geconfigureerd.",
        "DNSSEC seems to be implemented sufficiently.": "DNSSEC lijkt juist geconfigureerd.",


        // FTP
        "ftp": "Bestandsoverdracht (FTP)",
        "FTP": "Bestandsoverdracht (FTP)", // not used?
        "FTP Insecure": "FTP niet veilig",
        "FTP Server only supports insecure SSL protocol.": "De FTP server ondersteunt alleen het verouderde SSL protocol, gegevens kunnen niet voldoende worden versleuteld.",
        "FTP Server does not configured to show if encryption is available.": "De FTP server is niet ingesteld om aan te tonen of versleuteling beschikbaar is.",
        "FTP Server supports TLS encryption protocol.": "De FTP server ondersteunt TLS versleuteling.",
        "FTP Server does not support encrypted transport or has protocol issues.": "De FTP server ondersteunt geen versleuteling of heeft fouten in het protocol.",
        "An FTP connection could not be established properly. Not possible to verify encryption.": "Er kon geen verbinding worden gemaakt met deze FTP server, het is niet mogelijk om de veiligheid hiervan te controleren.",


        // used at security headers
        "Stats hasn\'t": "Heeft geen",
        "Stats has": "Heeft",


        // http_security_header_strict_transport_security
        "http_security_header_strict_transport_security": "Website: Strict-Transport-Security Header (HSTS)",
        "Strict-Transport-Security": "Strict-Transport-Security", // not used?
        "Strict-Transport-Security header present.": "Strict-Transport-Security header is aanwezig.",
        "Missing Strict-Transport-Security header.": "Mist de Strict-Transport-Security header. Bezoekers worden hierdoor niet verplicht om gebruik te maken van de versleutelde site.",
        "Missing Strict-Transport-Security header. Offers no insecure alternative service.": "De webserver mist de Strict-Transport-Security header. Er wordt geen beveiligd alternatief geboden.",


        // http_security_header_x_frame_options
        "http_security_header_x_frame_options": "Website: X-Frame-Options Header (Clickjacking)",
        "X-Frame-Options": "X-Frame-Options",
        "Missing X-Frame-Options header.": "Missing X-Frame-Options header.",
        "X-Frame-Options header present.": "X-Frame-Options header present.",

        "Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options Header.": "Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options Header.",


        // http_security_header_x_xss_protection
        "http_security_header_x_xss_protection": "Website: X-XSS-Protection Header",
        "X-XSS-Protection": "--test--",
        "X-XSS-Protection header present.": "X-XSS-Protection header present.",
        "Missing X-XSS-Protection header.": "Missing X-XSS-Protection header.",

        "Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.": "Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.",


        // http_security_header_x_content_type_options
        "http_security_header_x_content_type_options": "Website: X-Content-Type-Options Header",
        "X-Content-Type-Options": "X-Content-Type-Options", // not used?
        "X-Content-Type-Options header present.": "X-Content-Type-Options header present.",
        "Missing X-Content-Type-Options header.": "Missing X-Content-Type-Options header.",


        // plain_https
        "plain_https": "Ontbrekende versleuteling (HTTP only)",
        "Redirect from unsafe address": "Redirect from unsafe address",
        "Site does not redirect to secure url, and has no secure alternative on a standard port.": "Site does not redirect to secure url, and has no secure alternative on a standard port.",
        "Has a secure equivalent, which wasn't so in the past.": "Has a secure equivalent, which wasn't so in the past.",
        "Redirects to a secure site, while a secure counterpart on the standard port is missing.": "Redirects to a secure site, while a secure counterpart on the standard port is missing.",
        // this is an issue with a spelling error :)
        "Site does not redirect to secure url, and has nosecure alternative on a standard port.": "Site does not redirect to secure url, and has no secure alternative on a standard port.",
        "Not at all": "Not at all",


        // tls_qualys_encryption_quality
        "tls_qualys_encryption_quality": "Kwaliteit van de versleuteling (HTTPS)",
        "Broken Transport Security, rated F": "Broken Transport Security, rated F",
        "Certificate not valid for domain name.": "Certificate not valid for domain name.",
        "Less than optimal Transport Security, rated C.": "Less than optimal Transport Security, rated C.",
        "Less than optimal Transport Security, rated B.": "Less than optimal Transport Security, rated B.",
        "Good Transport Security, rated A-.": "Good Transport Security, rated A-.",
        "Good Transport Security, rated A.": "Good Transport Security, rated A.",
        "Perfect Transport Security, rated A+.": "Perfect Transport Security, rated A+.",
        "TLS rated C": "TLS rated C",
        "TLS rated B": "TLS rated B",
        "TLS rated A": "TLS rated A",
        "TLS rated A-": "TLS rated A-",
        "TLS rated A+": "TLS rated A+",
        "Broken": "Broken (completely insecure)",


        // tls_qualys_certificate_trusted
        "tls_qualys_certificate_trusted": "Vertrouwen in het certificaat (HTTPS)",
        "not trusted": "Niet vertrouwd",
        "trusted": "Vertrouwd",
        "Certificate is not trusted.": "Het certificaat wordt niet vertrouwd.",
        "Certificate is trusted.": "Het certificaat wordt vertrouwd.",

        // email checks:
        "dns_mx_no_cname": "E-Mail Server",

        // internet_nl_mail_starttls_tls_available
        "internet_nl_mail_starttls_tls_available": "E-Mail: Versleuteld transport (STARTTLS)",
        "STARTTLS Available": "STARTTLS Available",
        "STARTTLS Missing": "STARTTLS Missing",


        // internet_nl_mail_auth_spf_exist
        "internet_nl_mail_auth_spf_exist": "E-Mail: Sender Policy Framework (SPF)",
        "SPF Available": "SPF Available",
        "SPF Missing": "SPF Missing",


        // internet_nl_mail_auth_dkim_exist
        "internet_nl_mail_auth_dkim_exist": "E-Mail: DomainKeys Identified Mail (DKIM)",
        "DKIM Available": "DKIM Available",
        "DKIM Missing": "DKIM Missing",


        // internet_nl_mail_auth_dmarc_exist
        "internet_nl_mail_auth_dmarc_exist": "E-Mail: Domain-based Message Auth (DMARC)",
        "DMARC Available": "DMARC Available",
        "DMARC Missing": "DMARC Missing",

        "Test internet_nl_mail_auth_dmarc_exist resultated in failed": "Herkenning en preventie van namaak e-mails niet ingeschakeld.",

    }
};
