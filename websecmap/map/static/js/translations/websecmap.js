// Contains fallback messages which will slowly be moved to components. In the end this contains app messages
// and things that are used in many components (which are vulnerabilities etc, which are also in app).

const messages = {
    en: {
        // new translations
        back_to_map: "Back to the map",

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
        "DNSSEC is incorrectly or not configured (errors found).": "--test--",
        "DNSSEC seems to be implemented sufficiently.": "--test--",


        // FTP
        "ftp": "File transfer (FTP)",
        "FTP": "--test--", // not used?
        "FTP Insecure": "--test--",
        "FTP Server only supports insecure SSL protocol.": "--test--",
        "FTP Server does not configured to show if encryption is available.": "--test--",
        "FTP Server supports TLS encryption protocol.": "--test--",
        "FTP Server does not support encrypted transport or has protocol issues.": "--test--",
        "An FTP connection could not be established properly. Not possible to verify encryption.": "--test--",


        // used at security headers
        "Stats hasn\'t": "Does not have",
        "Stats has": "Does have",


        // http_security_header_strict_transport_security
        "http_security_header_strict_transport_security": "Website: Strict-Transport-Security Header (HSTS)",
        "Strict-Transport-Security": "--test--", // not used?
        "Strict-Transport-Security header present.": "--test--",
        "Missing Strict-Transport-Security header.": "--test--",
        "Missing Strict-Transport-Security header. Offers no insecure alternative service.": "--test--",


        // http_security_header_x_frame_options
        "http_security_header_x_frame_options": "Website: X-Frame-Options Header (Clickjacking)",
        "X-Frame-Options": "--test--",
        "Missing X-Frame-Options header.": "--test--",
        "X-Frame-Options header present.": "--test--",

        "Content-Security-Policy header found, which covers the security aspect of the X-Frame-Options Header.": "--test--",


        // http_security_header_x_xss_protection
        "http_security_header_x_xss_protection": "Website: X-XSS-Protection Header",
        "X-XSS-Protection": "--test--",
        "X-XSS-Protection header present.": "--test--",
        "Missing X-XSS-Protection header.": "--test--",

        "Content-Security-Policy header found, which covers the security aspect of the X-XSS-Protection header.": "--test--",


        // http_security_header_x_content_type_options
        "http_security_header_x_content_type_options": "Website: X-Content-Type-Options Header",
        "X-Content-Type-Options": "--test--", // not used?
        "X-Content-Type-Options header present.": "--test--",
        "Missing X-Content-Type-Options header.": "--test--",


        // plain_https
        "plain_https": "Missing transport encryption (HTTP only)",
        "Redirect from unsafe address": "--test--",
        "Site does not redirect to secure url, and has no secure alternative on a standard port.": "--test--",
        "Has a secure equivalent, which wasn't so in the past.": "--test--",
        "Redirects to a secure site, while a secure counterpart on the standard port is missing.": "--test--",
        // this is an issue with a spelling error :)
        "Site does not redirect to secure url, and has nosecure alternative on a standard port.": "--test--",
        "Not at all": "--test--",


        // tls_qualys_encryption_quality
        "tls_qualys_encryption_quality": "Encryption Quality (HTTPS)",
        "Broken Transport Security, rated F": "--test--",
        "Certificate not valid for domain name.": "--test--",
        "Less than optimal Transport Security, rated C.": "--test--",
        "Less than optimal Transport Security, rated B.": "--test--",
        "Good Transport Security, rated A-.": "--test--",
        "Good Transport Security, rated A.": "--test--",
        "Perfect Transport Security, rated A+.": "--test--",
        "TLS rated C": "--test--",
        "TLS rated B": "--test--",
        "TLS rated A": "--test--",
        "TLS rated A-": "--test--",
        "TLS rated A+": "--test--",
        "Broken": "--test--",


        // tls_qualys_certificate_trusted
        "tls_qualys_certificate_trusted": "Trust in certificate (HTTPS)",
        "not trusted": "--test--",
        "trusted": "--test--",
        "Certificate is not trusted.": "--test--",
        "Certificate is trusted.": "--test--",


        // internet_nl_mail_starttls_tls_available
        "internet_nl_mail_starttls_tls_available": "E-Mail: Encrypted transport (STARTTLS)",
        "STARTTLS Available": "--test--",
        "STARTTLS Missing": "--test--",


        // internet_nl_mail_auth_spf_exist
        "internet_nl_mail_auth_spf_exist": "E-Mail: Sender Policy Framework (SPF)",
        "SPF Available": "--test--",
        "SPF Missing": "--test--",


        // internet_nl_mail_auth_dkim_exist
        "internet_nl_mail_auth_dkim_exist": "E-Mail: DomainKeys Identified Mail (DKIM)",
        "DKIM Available": "--test--",
        "DKIM Missing": "--test--",


        // internet_nl_mail_auth_dmarc_exist
        "internet_nl_mail_auth_dmarc_exist": "E-Mail: Domain-based Message Auth (DMAR",
        "DMARC Available": "--test--",
        "DMARC Missing": "--test--",
    },
    nl: {


    }
};
