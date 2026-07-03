#!/usr/bin/env python3
"""
Build Nairobi-only ward and sub-county GeoJSON files from trusted HDX shapefile zips.

Outputs:
  data/boundaries/nairobi_wards.geojson
  data/boundaries/nairobi_subcounties.geojson
  data/boundaries/nairobi_boundary_build_report.json

Usage:
  python build_nairobi_boundary_geojsons.py
"""

from __future__ import annotations

import csv
import json
import math
import zipfile
from pathlib import Path

import shapefile


COUNTY_CODE_NAIROBI = 47
WARD_SOURCE_ZIP = "ward.results.zip"
SUBCOUNTY_SOURCE_ZIP = "constituencies.zip"

# The upstream ward shapefile has a few constituency assignment mistakes for Nairobi.
WARD_PAIR_OVERRIDES = {
    ("DAGORETTI SOUTH", "KABIRO"): ("DAGORETTI NORTH", "KABIRO"),
    ("DAGORETTI SOUTH", "KAWANGWARE"): ("DAGORETTI NORTH", "KAWANGWARE"),
    ("KIBRA", "NYAYO HIGHRISE"): ("LANGATA", "NYAYO HIGHRISE"),
}


def workspace_paths():
    script_dir = Path(__file__).resolve().parent
    boundary_dir = script_dir / "data" / "boundaries"
    source_dir = boundary_dir / "source"
    pack_dir = script_dir.parent / "nairobi_boundaries_source_pack"
    return script_dir, boundary_dir, source_dir, pack_dir


def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon = (x / 20037508.34) * 180.0
    lat = (y / 20037508.34) * 180.0
    lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
    return lon, lat


def transform_coords(coords, reprojection: str):
    if not coords:
        return coords

    if isinstance(coords[0], (int, float)):
        x, y = coords[0], coords[1]
        if reprojection == "3857_to_4326":
            lon, lat = web_mercator_to_wgs84(float(x), float(y))
            return [lon, lat]
        return [float(x), float(y)]

    return [transform_coords(part, reprojection) for part in coords]


def extract_zip_if_needed(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    shp_files = list(extract_dir.glob("*.shp"))
    if shp_files:
        return
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)


def read_expected_wards(path: Path):
    expected_pairs: dict[tuple[str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            subcounty = row["subcounty_name"].strip()
            ward = row["ward_name"].strip()
            expected_pairs[(subcounty.upper(), ward.upper())] = {
                "subcounty_name": subcounty,
                "ward_name": ward,
                "ward_code": row["ward_code"].strip(),
            }
    return expected_pairs


def read_expected_subcounties(path: Path):
    expected: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = row["subcounty_name"].strip()
            expected[name.upper()] = {
                "subcounty_name": name,
                "ward_count": row["ward_count"].strip(),
            }
    return expected


def load_reader_fields(reader: shapefile.Reader):
    return [field[0] for field in reader.fields[1:]]


def make_feature(geometry: dict, properties: dict) -> dict:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }


def build_ward_features(reader: shapefile.Reader, expected_pairs: dict[tuple[str, str], dict[str, str]]):
    fields = load_reader_fields(reader)
    county_idx = fields.index("COUNTY_COD")
    subcounty_idx = fields.index("CONSTITUEN")
    ward_idx = fields.index("NAME")

    features = []
    unmatched_pairs = []

    for sr in reader.iterShapeRecords():
        record = sr.record
        if int(float(record[county_idx])) != COUNTY_CODE_NAIROBI:
            continue

        raw_subcounty = str(record[subcounty_idx]).strip().upper()
        raw_ward = str(record[ward_idx]).strip().upper()
        pair = WARD_PAIR_OVERRIDES.get((raw_subcounty, raw_ward), (raw_subcounty, raw_ward))
        expected = expected_pairs.get(pair)
        if not expected:
            unmatched_pairs.append({"subcounty_name": pair[0], "ward_name": pair[1]})
            continue

        geometry = sr.shape.__geo_interface__
        features.append(
            make_feature(
                {
                    "type": geometry["type"],
                    "coordinates": transform_coords(geometry["coordinates"], "3857_to_4326"),
                },
                {
                    "county_code": COUNTY_CODE_NAIROBI,
                    "county_name": "Nairobi",
                    "subcounty_name": expected["subcounty_name"],
                    "ward_name": expected["ward_name"],
                    "ward_code": expected["ward_code"],
                    "source_constituency_name": raw_subcounty,
                    "source_ward_name": raw_ward,
                    "source_dataset": "HDX Kenya Elections ward.results.zip",
                    "source_crs": "EPSG:3857",
                    "output_crs": "EPSG:4326",
                },
            )
        )

    seen_pairs = {
        (feature["properties"]["subcounty_name"].upper(), feature["properties"]["ward_name"].upper())
        for feature in features
    }
    missing_expected = []
    for pair, expected in expected_pairs.items():
        if pair not in seen_pairs:
            missing_expected.append(expected)

    features.sort(key=lambda f: (f["properties"]["subcounty_name"], f["properties"]["ward_name"]))
    return features, unmatched_pairs, missing_expected


def build_subcounty_features(reader: shapefile.Reader, expected_subcounties: dict[str, dict[str, str]]):
    fields = load_reader_fields(reader)
    county_idx = fields.index("COUNTY_COD")
    subcounty_idx = fields.index("CONSTITUEN")

    features = []
    missing_expected = []

    for sr in reader.iterShapeRecords():
        record = sr.record
        if int(float(record[county_idx])) != COUNTY_CODE_NAIROBI:
            continue

        raw_subcounty = str(record[subcounty_idx]).strip().upper()
        expected = expected_subcounties.get(raw_subcounty)
        if not expected:
            continue

        geometry = sr.shape.__geo_interface__
        features.append(
            make_feature(
                geometry,
                {
                    "county_code": COUNTY_CODE_NAIROBI,
                    "county_name": "Nairobi",
                    "subcounty_name": expected["subcounty_name"],
                    "expected_ward_count": int(expected["ward_count"]),
                    "source_subcounty_name": raw_subcounty,
                    "source_dataset": "HDX Kenya Elections constituencies.zip",
                    "source_crs": "EPSG:4326",
                    "output_crs": "EPSG:4326",
                },
            )
        )

    seen = {feature["properties"]["subcounty_name"].upper() for feature in features}
    for key, expected in expected_subcounties.items():
        if key not in seen:
            missing_expected.append(expected)

    features.sort(key=lambda f: f["properties"]["subcounty_name"])
    return features, missing_expected


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main() -> None:
    _script_dir, boundary_dir, source_dir, pack_dir = workspace_paths()
    wards_zip = source_dir / WARD_SOURCE_ZIP
    subcounties_zip = source_dir / SUBCOUNTY_SOURCE_ZIP
    wards_extract = source_dir / "inspect_wards"
    subcounties_extract = source_dir / "inspect_constituencies"

    if not wards_zip.exists():
        raise FileNotFoundError(f"Missing source zip: {wards_zip}")
    if not subcounties_zip.exists():
        raise FileNotFoundError(f"Missing source zip: {subcounties_zip}")

    extract_zip_if_needed(wards_zip, wards_extract)
    extract_zip_if_needed(subcounties_zip, subcounties_extract)

    expected_wards = read_expected_wards(pack_dir / "nairobi_wards_expected.csv")
    expected_subcounties = read_expected_subcounties(pack_dir / "nairobi_subcounties_expected.csv")

    wards_reader = shapefile.Reader(str(next(wards_extract.glob("*.shp"))))
    subcounties_reader = shapefile.Reader(str(next(subcounties_extract.glob("*.shp"))))

    ward_features, ward_unmatched_pairs, missing_ward_features = build_ward_features(wards_reader, expected_wards)
    subcounty_features, missing_subcounty_features = build_subcounty_features(subcounties_reader, expected_subcounties)

    wards_fc = {
        "type": "FeatureCollection",
        "name": "nairobi_wards",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": ward_features,
    }
    subcounties_fc = {
        "type": "FeatureCollection",
        "name": "nairobi_subcounties",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": subcounty_features,
    }

    wards_out = boundary_dir / "nairobi_wards.geojson"
    subcounties_out = boundary_dir / "nairobi_subcounties.geojson"
    report_out = boundary_dir / "nairobi_boundary_build_report.json"

    write_json(wards_out, wards_fc)
    write_json(subcounties_out, subcounties_fc)
    write_json(
        report_out,
        {
            "status": "generated_with_warnings" if missing_ward_features or ward_unmatched_pairs or missing_subcounty_features else "generated",
            "outputs": {
                "wards_geojson": str(wards_out),
                "subcounties_geojson": str(subcounties_out),
            },
            "counts": {
                "ward_features_generated": len(ward_features),
                "ward_features_expected": len(expected_wards),
                "subcounty_features_generated": len(subcounty_features),
                "subcounty_features_expected": len(expected_subcounties),
            },
            "warnings": {
                "upstream_unmatched_ward_pairs": ward_unmatched_pairs,
                "missing_expected_wards": missing_ward_features,
                "missing_expected_subcounties": missing_subcounty_features,
            },
        },
    )

    print(f"Wrote {wards_out} with {len(ward_features)} features")
    print(f"Wrote {subcounties_out} with {len(subcounty_features)} features")
    if missing_ward_features:
        print("Missing expected ward features from upstream source:")
        for item in missing_ward_features:
            print(f"  - {item['subcounty_name']} / {item['ward_name']} (ward_code={item['ward_code']})")


if __name__ == "__main__":
    main()
