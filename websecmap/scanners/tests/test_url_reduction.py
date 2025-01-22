from websecmap.scanners.url_reduction import remove_randomization_from_url


def test_remove_randomization_from_url(db, urlreduction_sample_data):
    # removal of guids and timestamps is tested elsewhere. This test only checks if the UrlReduction stuff works
    # note this function is time cached, this will not work properly in tests and that's just fine for how complex it is

    # end replacement
    data = remove_randomization_from_url("https://svc.dynamics.com/t/c/2qehio/ad&formPageIds&id&rf&trackwebsitevisited")
    assert data == "https://TOKEN.svc.dynamics.com/t/c/TOKEN"

    # center replacement
    data = remove_randomization_from_url("https://v45.tiktokcdn-eu.com/4f0f2713305daa85fb8953dc9ab6019d/67640098/video")
    assert data == "https://TOKEN.tiktokcdn-eu.com/TOKEN"

    # start replacement
    data = remove_randomization_from_url("https://li-replay.s3-accelerate.amazonaws.com/4q3r3232234")
    assert data == "https://li-replay.s3-accelerate.amazonaws.com/TOKEN"

    # no replacement
    data = remove_randomization_from_url("https://example.nl")
    assert data == "https://example.nl"
