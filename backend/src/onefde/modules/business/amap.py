"""Bounded Amap POI 2.0 adapter. Candidates are observations only."""

import json
import unicodedata
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from onefde.core.errors import ApiException

URL = "https://restapi.amap.com/v5/place/text"
PAGE_SIZE = 10
MAX_RESULTS = 15
MAX_PAGES = 2


def fetch_page(key, adcode, page):
    params = {
        "key": key,
        "keywords": "水果店",
        "region": adcode,
        "city_limit": "true",
        "page_size": PAGE_SIZE,
        "page_num": page,
    }
    try:
        with urlopen(URL + "?" + urlencode(params), timeout=5) as response:
            result = json.loads(response.read(512_001))
    except (URLError, OSError, ValueError):
        raise ApiException(503, "AMAP_UNAVAILABLE", "高德地点查询暂不可用") from None
    if (
        not isinstance(result, dict)
        or result.get("status") != "1"
        or result.get("infocode") != "10000"
    ):
        raise ApiException(
            503, "AMAP_REJECTED", "高德拒绝地点查询，请核对授权、额度或区划"
        )
    if not isinstance(result.get("pois"), list):
        raise ApiException(503, "AMAP_BAD_RESPONSE", "高德返回的候选格式不符")
    return result["pois"]


def normal(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def search(key, adcode, *, sample=False):
    if adcode.endswith("00"):
        raise ApiException(422, "DISTRICT_REQUIRED", "请输入区县级六位行政区划代码")
    if not key and not sample:
        raise ApiException(
            503, "AMAP_UNCONFIGURED", "本地未配置获准使用的高德密钥，可选择模拟样例"
        )
    results, ids, addresses = [], set(), set()
    for page in range(1, MAX_PAGES + 1):
        rows = sample_page(adcode) if sample else fetch_page(key, adcode, page)
        for row in rows:
            if not isinstance(row, dict) or row.get("adcode") != adcode:
                continue
            poi_id, name, address = (
                row.get(field) for field in ("id", "name", "address")
            )
            if not all(
                isinstance(value, str) and value.strip()
                for value in (poi_id, name, address)
            ):
                continue
            identity = (normal(name), normal(address))
            if poi_id in ids or identity in addresses:
                continue
            ids.add(poi_id)
            addresses.add(identity)
            results.append(
                {
                    "source": "sample" if sample else "amap",
                    "adcode": adcode,
                    "poi_id": poi_id[:128],
                    "name": name,
                    "address": address,
                    "reason": "区县一致，命中水果店关键词且有可核对的地址",
                }
            )
            if len(results) == MAX_RESULTS:
                return results
        if sample or len(rows) < PAGE_SIZE:
            break
    return results


def sample_page(adcode):
    return [
        {
            "id": "sample-01",
            "name": "样例水果店",
            "address": "模拟路 10 号",
            "adcode": adcode,
        },
        {
            "id": "sample-02",
            "name": "样例水果店",
            "address": "模拟路 １０ 号",
            "adcode": adcode,
        },
        {
            "id": "sample-03",
            "name": "样例鲜果铺",
            "address": "模拟路 12 号",
            "adcode": adcode,
        },
        {"id": "sample-outside", "name": "区外样例", "address": "区外路", "adcode": ""},
    ]
