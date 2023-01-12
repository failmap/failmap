import json
from datetime import datetime
from typing import Any, Dict

import pytz
import requests
from requests import RequestException

from websecmap.app import log
from websecmap.organizations.models import GenericFileDataset

from django.core.files.uploadedfile import SimpleUploadedFile


def download_dataset_file(
    download_link: str,
    file_format="register_overheidsorganisaties",
    filename="websiteregister_rijksoverheid_%s.ods",
    layer: str = "",
    origin: str = "",
) -> GenericFileDataset:
    log.debug(f"Downloading dataset {download_link} into {layer}")

    # if already downloaded and not imported, retry the import:
    if (
        downloaded := GenericFileDataset.objects.all()
        .filter(file_format=file_format, is_imported=False, origin=origin, state="uploaded")
        .last()
    ):
        return downloaded.id

    try:
        response = requests.get(download_link)
        response.raise_for_status()
        return save_succesful_download(
            file_format=file_format, filename=filename, layer=layer, origin=origin, data=response.content
        )
    except RequestException as exc:
        return save_failed_download(layer=layer, origin=origin, error=str(exc))


def save_failed_download(
    file_format="register_overheidsorganisaties", layer: str = "", origin: str = "", error: str = ""
):
    idataset = create_dataset(file_format, origin)
    now = datetime.now(pytz.utc).isoformat()
    idataset.state = "failed_file_download"
    idataset.parser_info = json.dumps(
        {"origin": origin, "state": "failed_file_download", "exception": error, "layer": layer, "at_when": now}
    )
    idataset.save()
    return idataset


def save_succesful_download(
    file_format="register_overheidsorganisaties",
    filename="websiteregister_rijksoverheid_%s.ods",
    layer: str = "",
    origin: str = "",
    data: Any = "",
):
    idataset = create_dataset(file_format, origin)
    now = datetime.now(pytz.utc).isoformat()
    idataset.file = SimpleUploadedFile(filename.format(now), data)
    idataset.state = "uploaded"
    idataset.parser_info = json.dumps({"origin": origin, "state": "uploaded", "layer": layer, "at_when": now})
    idataset.save()
    return idataset


def create_dataset(file_format: str, origin: str):
    idataset = GenericFileDataset()
    idataset.file_format = file_format
    idataset.is_imported = False
    idataset.origin = origin
    return idataset


def finish_import(dataset: GenericFileDataset):
    dataset.is_imported = True
    dataset.imported_on = datetime.now(pytz.utc)
    dataset.save()


def load_parser_info(dataset: GenericFileDataset) -> Dict[str, Any]:
    if not dataset.parser_info:
        log.warning("No parser information found for dataset %s", dataset)
        return {}

    try:
        return json.loads(dataset.parser_info)
    except json.JSONDecodeError:
        log.warning(f"Could not parse data from generic file dataset: {dataset}")
        return {}
