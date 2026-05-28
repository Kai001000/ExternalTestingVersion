"""Shared Market Region segment overlays.

Base `dim_region16_mapping.csv` defines the base Market Region rows such as
`Lower North Shore`. Core / Extended names are derived segment overlays that
are postcode-expanded at build time and runtime for compatible REGION16 paths.
"""

# Legacy internal token = REGION16.
# Canonical product-facing name = Market Region.
REGION16_SEGMENT_DEFINITIONS = (
    {
        "base_region": "Lower North Shore",
        "segment_region": "Lower North Shore \u2014 Core",
        "postcodes": ("2060", "2061", "2088", "2089", "2090"),
    },
    {
        "base_region": "Lower North Shore",
        "segment_region": "Lower North Shore \u2014 Extended",
        "postcodes": ("2067",),
    },
    {
        "base_region": "Upper North Shore",
        "segment_region": "Upper North Shore \u2014 Core",
        "postcodes": ("2070", "2071", "2072", "2074"),
    },
    {
        "base_region": "Upper North Shore",
        "segment_region": "Upper North Shore \u2014 Extended",
        "postcodes": ("2077",),
    },
)
