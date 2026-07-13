import unittest

import pandas as pd
import polars as pl

from utils.market_view_area import (
    build_area_options_from_frames,
    coerce_selected_area_label,
    filter_market_scope_for_regions,
    normalize_area_postcode,
    normalize_area_suburb_key,
)


class MarketViewAreaSelectionTests(unittest.TestCase):
    def test_macquarie_park_option_is_built_from_dimension(self):
        dim = pl.DataFrame(
            {
                "suburb": ["  Macquarie Park  "],
                "postcode": ["2113"],
            }
        )
        options = build_area_options_from_frames(
            daily_suburb=pl.DataFrame(schema={"region": pl.Utf8}),
            daily_postcode=pl.DataFrame(schema={"region": pl.Utf8}),
            dim_suburb_postcode=dim,
        )

        self.assertIn(("Macquarie Park (2113)", "Macquarie Park"), options)

    def test_selected_area_is_stable_when_option_has_no_visible_rows(self):
        options = ["Airds (2560)", "Macquarie Park (2113)", "Postcode 2113"]

        selected = coerce_selected_area_label("Macquarie Park (2113)", options)

        self.assertEqual(selected, "Macquarie Park (2113)")

    def test_selected_area_matches_existing_option_case_insensitively(self):
        options = ["AARONS PASS", "MACQUARIE PARK (2113)", "Postcode 2113"]

        selected = coerce_selected_area_label("Macquarie Park (2113)", options)

        self.assertEqual(selected, "MACQUARIE PARK (2113)")

    def test_missing_selected_area_falls_back_to_first_available_option(self):
        options = ["Airds (2560)", "Macquarie Park (2113)"]

        selected = coerce_selected_area_label("No Longer Present (9999)", options)

        self.assertEqual(selected, "Airds (2560)")

    def test_filtering_macquarie_park_handles_case_and_whitespace(self):
        df = pd.DataFrame(
            {
                "region": ["MACQUARIE PARK", "North Ryde"],
                "rolling_median": [900_000, 1_200_000],
            }
        )

        filtered = filter_market_scope_for_regions(df, "AREA", [" macquarie park "])

        self.assertEqual(filtered["region"].tolist(), ["MACQUARIE PARK"])

    def test_filtering_macquarie_park_can_return_empty_without_throwing(self):
        df = pd.DataFrame(
            {
                "region": ["North Ryde"],
                "rolling_median": [1_200_000],
            }
        )

        filtered = filter_market_scope_for_regions(df, "AREA", ["Macquarie Park"])

        self.assertTrue(filtered.empty)

    def test_empty_filter_result_does_not_change_selected_area(self):
        options = ["Airds (2560)", "Macquarie Park (2113)"]
        df = pd.DataFrame({"region": ["North Ryde"], "rolling_median": [1_200_000]})

        filtered = filter_market_scope_for_regions(df, "AREA", ["Macquarie Park"])
        selected = coerce_selected_area_label("Macquarie Park (2113)", options)

        self.assertTrue(filtered.empty)
        self.assertEqual(selected, "Macquarie Park (2113)")

    def test_normalisation_handles_case_whitespace_and_postcode_suffixes(self):
        self.assertEqual(
            normalize_area_suburb_key("  MACQUARIE   PARK "),
            normalize_area_suburb_key("Macquarie Park"),
        )
        self.assertEqual(normalize_area_postcode(" 2113.0 "), "2113")
        self.assertEqual(normalize_area_postcode("Postcode 2113"), "2113")


if __name__ == "__main__":
    unittest.main()
