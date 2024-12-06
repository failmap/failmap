import os
from typing import List

from websecmap.map.models import MapDataCache


def get_all_files_on_disk(some_path: str = "/source/websecmap/uploads/map_data_cache/"):
    """
    Results in:
    [
        '/source/websecmap/uploads/map_data_cache/2024/03/31/data.json_47aD6hQ.zip',
        '/source/websecmap/uploads/map_data_cache/2024/03/31/data.json_Tna4kRi.zip',
        ...
    ]
    """
    # get all files on disk recursively for a certain directory, returning a list of full paths
    files = []
    for root, _, filenames in os.walk(some_path):
        files.extend(os.path.join(root, filename) for filename in filenames)
    return files


def get_all_files_in_db_map_data_cache():
    """
    Results in:
    [
        'map_data_cache/2024/02/20/data.json_05LcjFW.zip', 'map_data_cache/2024/02/20/data.json_1MGfx0h.zip',
        'map_data_cache/2024/02/20/data.json_sj0r5RK.zip', 'map_data_cache/2024/02/20/data.json_0rNLghs.zip',
        ...
    ]
    """
    return MapDataCache.objects.all().values_list("dataset_file", flat=True)


def remove_unwired_map_data_cache():
    # The problem seems that the map data cache is built _twice_ every day, and things for a certain
    # date are just overwritten. The previous files are not removed on disk because file storage does not remove
    # stuff when the record is removed. Which means 1300 files are create every night and then a new set
    # gets created. So figure out what where this cache is run twice. And remove all the useless files.
    # map data cache is 25 gigabyte. It has 440737 files and it seems it always has run twice a day :)
    # there are 279590 files to unwire. Of 700000 which is about right... Saves about 10 gigabytes.

    # remove part of the file path which mirrors the input. Only get the part that the database knows.
    files_on_disk = get_all_files_on_disk("/source/websecmap/uploads/map_data_cache/")
    files_on_disk = [file.replace("/source/websecmap/uploads/", "") for file in files_on_disk]
    to_remove = what_to_remove(get_all_files_in_db_map_data_cache(), files_on_disk)
    # complete path:
    remove_unwired([f"/source/websecmap/uploads/{x}" for x in to_remove])


def what_to_remove(file_paths_in_db: List[str], file_paths_on_disk: List[str]):
    if not file_paths_in_db or not file_paths_on_disk:
        print("No files to remove. Or it would remove everything, which is not what you want.")
        return []
    not_in_db = list(sorted(list(set(file_paths_on_disk) - set(file_paths_in_db))))
    print("Want to remove {len(not_in_db} files from disk:")
    for file in not_in_db:
        print(f"Unwired file found: {file}")
    return not_in_db


def remove_unwired(files: List[str]) -> None:
    # print(files)
    for file in files:
        print(f"Deleting: {file}")
        os.unlink(file)
