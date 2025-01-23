import itertools
import logging
from datetime import date, datetime
from tempfile import NamedTemporaryFile
from typing import Union, Dict, List

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Font

from django.utils.text import slugify

from websecmap.map.logic.map_defaults import (
    DEFAULT_COUNTRY,
    DEFAULT_LAYER,
    determine_when,
    get_country,
    get_organization_type,
)
from websecmap.organizations.models import Organization, OrganizationType
from websecmap.reporting.diskreport import retrieve_report
import json

log = logging.getLogger(__package__)


def get_organization_report_by_name(
    country: str = DEFAULT_COUNTRY,
    organization_type=DEFAULT_LAYER,
    organization_name=None,
    days_back=0,
    at_date: date = None,
):
    organization = Organization.objects.filter(
        computed_name_slug=slugify(organization_name),
        country=get_country(country),
        layers=get_organization_type(organization_type),
        is_dead=False,
    ).first()

    log.debug("- %s %s %s ", organization_name, get_country(country), get_organization_type(organization_type))
    log.debug(organization)

    if not organization:
        return {}

    return get_organization_report_by_id(organization.pk, days_back, at_date)


def get_organization_report_by_id(
    organization_id: int, organization_type: str = None, country: str = None, days_back: int = 0, at_date: date = None
):
    # todo: check if the organization / layer is displayed on the map.

    when = determine_when(days_back, at_date)

    if not organization_type or not country:
        organization = Organization.objects.all().filter(pk=organization_id)
    else:
        organization = Organization.objects.all().filter(
            pk=organization_id, layers__name=organization_type, country=country
        )
    if not organization:
        return {}

    ratings = organization.filter(organizationreport__at_when__lte=when)

    try:
        values = ratings.values(
            "organizationreport__at_when",
            "name",
            "pk",
            "twitter_handle",
            "city",
            "organizationreport__id",
            "organizationreport__high",
            "organizationreport__medium",
            "organizationreport__low",
            "organizationreport__ok",
        ).latest("organizationreport__at_when")
    except Organization.DoesNotExist:
        return {}

    report_data = retrieve_report(values["organizationreport__id"], "OrganizationReport")

    return {
        "name": values["name"],
        "slug": slugify(values["name"]),
        "id": values["pk"],
        "country": organization.first().country.code,
        "layer": organization.first().layers.first().name,
        "twitter_handle": values["twitter_handle"],
        "city": values["city"],
        "when": values["organizationreport__at_when"].isoformat(),
        # fixing json being presented and escaped as a string, this makes it a lot slowr
        # had to do this cause we use jsonfield, not django_jsonfield, due to rendering map widgets in admin
        "calculation": report_data,
        "promise": "",
        "high": values["organizationreport__high"],
        "medium": values["organizationreport__medium"],
        "low": values["organizationreport__low"],
        "ok": values["organizationreport__ok"],
    }


def convert_report_to_excel(
    organization_id: int, organization_type: str = None, country: str = None, days_back: int = 0, at_date: date = None
):
    # PyExcel allows for richer exports with formatting. Which is nice. Other spreadsheet programs can all read excel.
    # Todo: find a way to convert excel to other formats, instead of dealing with all formats.
    log.debug("Input validation")
    organization = Organization.objects.filter(pk=organization_id).first()
    if not organization:
        return []

    # some validation on country and ot
    my_ot = get_organization_type(organization_type)
    organization_type = OrganizationType.objects.get(pk=my_ot).name
    country = get_country(country)

    log.debug("Data retrieval")
    report_data = get_organization_report_by_id(organization_id, organization_type, country, days_back, at_date)
    if not report_data:
        return []

    # todo: add dynamic header with highs and mediums...
    # dynamic_header = create_dynamic_excel_header(report_data)

    link_data = f"https://basisbeveiliging.nl/report/{country}/{organization_type}/{organization.id}"
    # placeholders are filled in during report generation
    link_data += "?tab=report_detail&filter_test={test}&filter_url={url}"

    rows = report_to_excel_rows(report_data, link_data)
    if not rows:
        return []

    # build the report
    wb = Workbook()
    # Make sure the date columns are rendered as such, which does not allow tzinfo
    # https://openpyxl.readthedocs.io/en/stable/datetime.html
    wb.iso_dates = True

    ws = wb.active
    dt = datetime.fromisoformat(report_data["when"])
    normalized_organization_name: str = organization.name[:30].replace("/", " ")
    ws.title = f"Basisbeveiliging Metingen {normalized_organization_name} {slugify(dt.strftime('%Y%m%d%H%M%S'))}"

    log.debug("Adding report header")
    static_header = create_static_excel_header(report_data, organization)
    for row in static_header:
        ws.append(list(row))

    ws["B2"].style = "Hyperlink"
    ws["B2"].hyperlink = f"https://basisbeveiliging.nl/report/{country}/{organization_type}/{organization.id}/"

    headers = rows[0].keys()
    ws.append(list(headers))

    log.debug("Adding data to workbook")
    for row in rows:
        ws.append(list(row.values()))

    # This is making saving intensely slower, so only add links to high, medium and low.
    # As the range documentation is lacking, just use a savage
    # 90's era counter and break the loop after the amount of highs+mediums+lows have been reached :)
    limit = report_data["high"] + report_data["medium"] + report_data["low"] + len(static_header)
    i = 0
    for cell in ws["G"]:
        i += 1

        if i > len(static_header) + 1:
            cell.style = "Hyperlink"
            cell.hyperlink = cell.value
            cell.value = "view report"

        if i > limit:
            break

    log.debug("Creating a table")
    # add a table around the metrics, so they have a striped layout
    tab = Table(displayName="BasisbeveiligingMetrics", ref=f"A{len(static_header)+1}:N{len(rows)+len(static_header)+1}")

    style = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=True,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    tab.tableStyleInfo = style
    ws.add_table(tab)

    # add some filtering on certain columns, so interesting values can be easily spotted
    # https://openpyxl.readthedocs.io/en/stable/filters.html
    # not supported in numbers it seems.
    # filters = ws.auto_filter
    # filters.ref = "A1:B15"
    # col = FilterColumn(colId=0)  # for column A
    # col.filters = Filters(filter=["Kiwi", "Apple", "Mango"])  # add selected values
    # filters.filterColumn.append(col)  # add filter to the worksheet
    # ws.auto_filter.add_sort_condition("B2:B15")

    # for awesomeness, add some charts... but no need to rebuild the web interface really.
    # https://openpyxl.readthedocs.io/en/stable/usage.html
    # https://openpyxl.readthedocs.io/en/stable/charts/introduction.html
    # https://openpyxl.readthedocs.io/en/stable/charts/bar.html

    # set for convenient printing, add some headers & footers :)
    # https://openpyxl.readthedocs.io/en/stable/print_settings.html

    # Set a column lock. when the table is in the right place...
    # Calculate the freeze pane. Is this not supported in numbers with the import.
    log.debug("Freezing pane")
    ws.freeze_panes = ws[f"B{len(static_header)+2}"]

    # custom props are not supported, or the documentation is outdated.
    # all security features against unwanted editing are implemented terribly with modals etc, so don't do that.

    # todo: add a logo
    # https://openpyxl.readthedocs.io/en/stable/images.html

    # todo: autofit scan type width, but not all other columns.
    # Or make an educated guess at the width.
    log.debug("Resizing columns")
    ws.column_dimensions["A"].width = "40"
    ws.column_dimensions["F"].width = "4"
    ws.column_dimensions["G"].width = "10"
    ws.column_dimensions["H"].width = "40"
    ws.column_dimensions["I"].width = "10"
    ws.column_dimensions["J"].width = "10"
    ws.column_dimensions["K"].width = "40"
    ws.column_dimensions["L"].width = "40"

    # todo: add second level domain -> ondern welke root wordt dat uitgegeven.

    # todo: match column designs to field names, so if the order changes or etc the design stays the same.
    # Currently it's a mess with every change...

    # add links:

    # hide the columns that show high, medium, low etc as the impact would be enough:
    # these can be completely removed, it doubles the data and the impact already summarizes this perfectly.
    # log.debug("Reticulating splines")
    # for col in ["N", "O", "P", "Q", "R", "S", "T", "U"]:
    #     ws.column_dimensions[col].hidden = True

    # add some hyperlinks:
    ws["B7"].style = "Hyperlink"
    ws["B7"].hyperlink = "https://internetcleanup.foundation/deelnemerschap/"

    # create some sort of header
    ws["A1"].font = Font(bold=True)

    # offer it as a django download
    log.debug("Offering download")
    with NamedTemporaryFile() as tmp:
        log.debug("Writing file")
        wb.save(tmp.name)
        tmp.seek(0)
        log.debug("Creating http response")
        response = HttpResponse(tmp.read())
        response["Content-Disposition"] = f"attachment; filename={slugify(ws.title)}.xlsx"
        response["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response


def create_static_excel_header(report_data, organization: Organization):
    # todo: how does this work with markup? Perhaps this has to be done inline.
    return [
        [f"Security Metrics Report for {organization.name}", ""],
        ["Downloaded from:", f"https://basisbeveiliging.nl/report/{organization.id}/"],
        ["Generated by:", "Basisbeveiliging.nl / Internet Cleanup Foundation"],
        ["Generated on:", report_data["when"]],
        ["", ""],
        ["This Excel export was made possible with funding from participants of the Internet Cleanup Foundation", ""],
        ["Read here why your organization should participate:", "https://internetcleanup.foundation/deelnemerschap/"],
        ["", ""],
    ]


def report_to_excel_rows(report_data, link_data) -> List[Dict[str, Union[str, int]]]:
    ld = link_data
    rows = []

    for url in report_data["calculation"]["organization"]["urls"]:
        url_data = {"url": url["url"]}
        # some placeholder data so all rows have the same columns
        # 'endpoint': '-',
        placeholder_ep_data = {"ip_version": "", "port": "", "protocol": ""}
        rows.extend(url_data | placeholder_ep_data | rating_data(url_rating, url, ld) for url_rating in url["ratings"])

        for ep in url["endpoints"]:
            # 'endpoint': ep['id'],
            epd = {"ip_version": ep["ip_version"], "port": ep["port"], "protocol": ep["protocol"]}
            # internet.nl metrics do not show on an endpoint.
            if ep["protocol"] in ["dns_a_aaaa", "dns_mx_no_cname", "dns_soa"]:
                epd = {"ip_version": "", "port": "", "protocol": ""}

            rows.extend(url_data | epd | rating_data(endpoint_rating, url, ld) for endpoint_rating in ep["ratings"])

    # some enrichment steps here. Make sure the impact is summarized in 1 word and an emoji.

    # sort the rows by issue severity, issue name.
    rows.sort(
        key=lambda x: (
            -x["is_explained"],
            x["high"],
            x["medium"],
            x["low"],
            x["ok"],
            x["not_testable"],
            x["not_applicable"],
            x["error_in_test"],
            x["url"],
            x["test"],
        )
    )

    # remove the high, medium, low, ok, not_testable, error_in_test, not_applicable and is_explained fields to
    # speed up the export even more...
    # these fields are not used in the export, so they don't need to be included in the final output.
    remove = ["high", "medium", "low", "ok", "not_testable", "error_in_test", "not_applicable", "is_explained"]
    for row, rem in itertools.product(rows, remove):
        del row[rem]

    # Removing lines changes the file from a compliance report to a to do list. This is not a great reduction.
    # todo: find other ways to speed up spreadsheet report generation.
    # # remove the rows where there is just a normal OK rating. Only for really large data sets...
    # if len(rows) > 2000:
    #     filtered_rows = [row for row in rows if not row["ok"]]
    #     removed_records = len(rows) - len(filtered_rows)
    # else:
    #     filtered_rows = rows
    #     removed_records = 0

    return list(reversed(rows))


def rating_data(rating, url, link_data) -> Dict[str, Union[str, int]]:
    impact = (
        "explained"
        if rating["is_explained"]
        else (
            "not_tested"
            if rating["not_testable"] or rating["not_applicable"]
            else (
                "error"
                if rating["error_in_test"]
                else "high" if rating["high"] else "medium" if rating["medium"] else "low" if rating["low"] else "ok"
            )
        )
    )
    empoji = {
        "explained": "💬",
        "high": "❌",
        "medium": "⚠️",
        "low": "🟩",
        "ok": "✅",
        "error": "⚡️",
        "not_tested": "〰️",
    }

    # Excel does not support timezones in datetimes. The tzinfo in the datetime/time object must be set to None.
    last_scan = datetime.fromisoformat(rating.get("last_scan", ""))
    last_scan = last_scan.replace(tzinfo=None).date()

    since = datetime.fromisoformat(rating.get("since", ""))
    since = since.replace(tzinfo=None).date()

    meaning = json.dumps(rating.get("meaning", {}))
    if meaning in ["{}", "[]", "-"]:
        meaning = ""

    evidence = rating.get("evidence", "{}")
    if evidence in ["{}", "[]", "-"]:
        evidence = ""

    return {
        "impact": impact,
        "emoji": empoji.get(impact, ""),
        "documentation": link_data.format(test=rating["type"], url=url["url"]),
        "test": rating["type"],
        "last_scan": last_scan,
        "since": since,
        "evidence": evidence,
        # don't show {} noise
        "meaning": meaning,
        "scan_id": rating.get("scan", ""),
        "high": rating["high"],
        "medium": rating["medium"],
        "low": rating["low"],
        "ok": rating["ok"],
        "not_testable": rating["not_testable"],
        "error_in_test": rating["error_in_test"],
        "not_applicable": rating["not_applicable"],
        "is_explained": rating["is_explained"],
    }
