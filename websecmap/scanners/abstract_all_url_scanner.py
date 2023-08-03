# from typing import List
#
# import importlib
#
# from celery import group
#
# from websecmap.celery import app
# from websecmap.organizations.models import Url
# from websecmap.scanners import init_dict, plannedscan
# from websecmap.scanners.scanner.filter import filter_endpoints_only, generic_plan_scan
#
# SCANNER_NAME = "undefined"
#
# # this scanner is run on all urls, not just a filtered selection (yet).
# # This hopefully saves on duplicated methods every scanner...
#
#
# @app.task(queue="kickoff", ignore_result=True)
# def plan_scan(**kwargs) -> None:
#     scanner_name = kwargs.get("scanner", {}).get("name", SCANNER_NAME)
#     generic_plan_scan(scanner_name, "scan", **kwargs)
#
#
# @app.task(queue="kickoff")
# def compose_planned_scan_task(**kwargs) -> group:
#     scanner_name = kwargs.get("scanner", {}).get("name", SCANNER_NAME)
#     urls = plannedscan.pickup(activity="scan", scanner=scanner_name, amount=kwargs.get("amount", 25))
#     return compose_scan_task(urls, load_scanner_module(scanner_name))
#
#
# def compose_manual_scan_task(
#     organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
# ) -> group:
#     organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter,
#     endpoints_filter)
#     urls = filter_endpoints_only(organizations_filter, urls_filter, **kwargs)
#     scanner_name = kwargs.get("scanner", {}).get("name", SCANNER_NAME)
#     return compose_scan_task(urls, load_scanner_module(scanner_name))
#
#
# def compose_scan_task(urls: List[Url], scanner_module) -> group:
#     tasks = []
#     tasks.extend(
#         group(
#             scanner_module.scan.si(url.url, url.id)
#             | scanner_module.store_scan.s(url.url, url.id)
#             | plannedscan.finish.si("scan", SCANNER_NAME, url.id)
#         )
#         for url in urls
#     )
#     return group(tasks)
#
#
# def load_scanner_module(scanner_name):
#     return importlib.import_module(scanner_name)
#
