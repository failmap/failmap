import json
import os
from typing import Dict, List

from websecmap.reporting import time_cache

PRIVACY_DISCONNECTME_ENTITIES_FILE = f"{os.path.abspath(os.path.dirname(__file__))}/disconnectme/services.json"


def get_known_trackers_from_urls(urls: List[str]):
    all_urls = []
    # disconnectme doesn't always have the www domain listed in their sources:
    for url in urls:
        all_urls.append(url)
        if url.startswith("www."):
            all_urls.append(url.replace("www.", ""))

    urls = all_urls

    # Now lets look what trackers exist
    known_trackers = []
    for url in urls:
        if info := get_tracker_info_from_disconnectme(url):
            known_trackers.append(info)

        # currently no known trackers
        # if not info:
        #     if info := get_tracker_info_from_websecmap(url):
        #         known_trackers.append(info)

    return known_trackers


def get_tracker_info_from_disconnectme(url: str) -> Dict[str, str]:
    # Checks url against services from disconnect me. If there's a match some company data will be returned
    data = convert_disconnectme_to_tracker_info()
    return data.get(url, {})


def convert_disconnectme_to_tracker_info():
    if cached := time_cache.cache_get("disconnectme"):
        return cached

    # Make On operation an O1 operation:
    with open(PRIVACY_DISCONNECTME_ENTITIES_FILE, encoding="UTF-8") as f:
        data = json.load(f)

    structured_data: Dict[str, Dict[str, str]] = {}

    for category, companies in data["categories"].items():
        for company_data in companies:
            for company_name, platform_data in company_data.items():
                for platform_url, tracking_domains in platform_data.items():
                    for url in tracking_domains:
                        structured_data[url] = {
                            "Category": category,
                            "Company": company_name,
                            "Platform": platform_url,
                            "Tracking Url": url,
                        }

    if structured_data:
        time_cache.cache_set("disconnectme", structured_data)

    return structured_data


def get_tracker_info_from_websecmap(url: str) -> Dict[str, str]:
    trackers = {
        # We may combine this information from your browser or your mobile device with other information that we or
        # our partners collect about you, including across devices.
        # Note that we principally rely on consent (i) to send marketing messages, (ii) for third-party data sharing
        # related to advertising, and, to the extent applicable, (iii) for the use of location data for advertising
        # Seen a contract, seems to be a legit eu business. Don't know yet how to place this.
        # "tracking.monsido.com": {
        #     "Category": "Analytics",
        #     "Company": "Monsido",
        #     "Platform": "https://monsido.com",
        #     "Tracking Url": "tracking.monsido.com",
        # },
        # missing in the disconnectme set
        # Adobe says to not track using this domain.
        # "use.typekit.net": {
        #     "Category": "Content",
        #     "Company": "Adobe",
        #     "Platform": "https://typekit.com",
        #     "Tracking Url": "use.typekit.net",
        # },
        # https://www.jsdelivr.com/terms/privacy-policy-jsdelivr-net
        # We do not use cookies or similar tracking technologies to track your activity on our Service.
        # We never associate any gathered data with specific users or try to track their usage at any point and ...
        # These third parties have access to your Personal Data only to perform these tasks on our behalf and are
        # obligated not to disclose or use it for any other purpose.
        # 'jsdelivr.net': {
        #     'Category': 'Content',
        #     'Company': 'jsdelivr.com',
        #     'Platform': 'https://www.jsdelivr.com',
        #     'Tracking Url': 'jsdelivr.net'
        # }
        # Font Awesome does not sell or give information about you to other companies or services.
    }

    return trackers.get(url, {})
