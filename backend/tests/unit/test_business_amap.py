import json

import pytest

from onefde.core.errors import ApiException
from onefde.modules.business import amap


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, _):
        return json.dumps(self.payload).encode()


def test_poi_pages_are_bounded_filtered_and_deduplicated(monkeypatch):
    urls = []

    def fake(url, *, timeout):
        urls.append(url)
        assert timeout == 5
        first = len(urls) == 1
        ids = range(10) if first else range(8, 18)
        return Response(
            {
                "status": "1",
                "infocode": "10000",
                "pois": [
                    {
                        "id": str(i),
                        "name": f"水果店{i}",
                        "address": f"某路{i}号",
                        "adcode": "440106" if i != 2 else "440104",
                    }
                    for i in ids
                ],
            }
        )

    monkeypatch.setattr(amap, "urlopen", fake)
    results = amap.search("fake", "440106")
    assert len(results) == 15
    assert "2" not in {item["poi_id"] for item in results}
    assert len(urls) == 2
    assert all(
        "region=440106" in url and "city_limit=true" in url and "page_size=10" in url
        for url in urls
    )
    assert ["page_num=1" in urls[0], "page_num=2" in urls[1]] == [True, True]


def test_provider_rejection_does_not_echo_provider_error_or_key(monkeypatch):
    monkeypatch.setattr(
        amap,
        "urlopen",
        lambda *a, **k: Response(
            {"status": "0", "infocode": "10003", "info": "provider secret diagnostic"}
        ),
    )
    with pytest.raises(ApiException) as rejected:
        amap.search("fake", "440106")
    assert rejected.value.code == "AMAP_REJECTED"
