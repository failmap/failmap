from typing import Any
import json
import zipfile
import io

from django.core.files.base import ContentFile


def json_to_zip(data: Any):
    # using gzip as that might also be served by the webserver directly.

    # https://stackoverflow.com/questions/2463770/python-in-memory-zip-library
    dumped = json.dumps(data)
    zip_buffer = io.BytesIO()

    # 4kb to 160 bytes, seems to compress things...
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr("data.json", dumped)

    return zip_buffer.getvalue()


def zip_to_json(file_pointer: Any):
    input_zip = zipfile.ZipFile(file_pointer)
    things = {name: input_zip.read(name) for name in input_zip.namelist()}
    return json.loads(things["data.json"])


def transparent_json_to_zip_storage(data: Any):
    # data needs to be a json serializable python data structure (like a dict)
    return ContentFile(json_to_zip(data), "data.json.zip")
