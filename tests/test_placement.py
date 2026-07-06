from aerosend_utils.placement_test import SeedResult, placement_rate


def test_placement_rate():
    results = [SeedResult(1, "gmail", "inbox"), SeedResult(1, "outlook", "spam"),
               SeedResult(1, "yahoo", "inbox"), SeedResult(1, "other", "missing")]
    assert placement_rate(results) == 0.5
