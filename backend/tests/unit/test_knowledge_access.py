from onefde.modules.knowledge import access, catalog


def test_restricted_never_listed_or_fetched():
    catalog.clear_cache()
    restricted = next(
        a
        for a in catalog.load_manifests()
        if a["id"] == "fixture-restricted-supplier-notes"
    )
    assert access.can_list(restricted, purpose="delivery") is False
    assert access.project_for_get(restricted, purpose="delivery") is None
    assert access.project_for_get(restricted, purpose="public_marketing") is None


def test_public_marketing_strips_implementation():
    catalog.clear_cache()
    asset = next(
        a for a in catalog.load_manifests() if a["id"] == "fresh-quote-compare-csv"
    )
    projected = access.project_for_list(asset, purpose="public_marketing")
    assert projected["public_summary"]
    assert "implementation_ref" not in projected
    assert "evidence" not in projected
    full = access.project_for_get(asset, purpose="delivery")
    assert full["implementation_ref"].startswith("products/")
