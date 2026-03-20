"""Tests for the YAML client profile loader."""

import tempfile
from pathlib import Path

import yaml

from src.scoring.client_profile_loader import (
    get_client_metadata,
    load_all_profiles,
    load_client_profile,
)


def _write_yaml(directory: Path, filename: str, data: dict) -> Path:
    path = directory / filename
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


class TestLoadClientProfile:
    def test_loads_basic_profile(self, tmp_path):
        data = {
            "client_id": "test_client",
            "client_name": "Test Client",
            "is_active": True,
            "alert_threshold": 50,
            "positive_keywords": ["transportation", "transit"],
            "subject_priorities": {"transportation": 1.0, "education": 0.5},
            "committee_keywords": ["Transportation Committee"],
            "watched_bills": ["SB00009"],
        }
        path = _write_yaml(tmp_path, "test.yaml", data)

        profile = load_client_profile(path)

        assert profile.client_id == "test_client"
        assert "transportation" in profile.keywords
        assert "transit" in profile.keywords
        assert "transportation" in profile.subject_interests
        assert "education" in profile.subject_interests
        assert profile.alert_threshold == 50.0
        assert "SB00009" in profile.watched_bills

    def test_includes_agency_keywords(self, tmp_path):
        data = {
            "client_id": "c1",
            "positive_keywords": ["transit"],
            "agency_keywords": ["DOT", "OPM"],
        }
        path = _write_yaml(tmp_path, "c1.yaml", data)
        profile = load_client_profile(path)

        assert "transit" in profile.keywords
        assert "dot" in profile.keywords  # lowercased
        assert "opm" in profile.keywords

    def test_missing_client_id_raises(self, tmp_path):
        data = {"positive_keywords": ["test"]}
        path = _write_yaml(tmp_path, "bad.yaml", data)

        try:
            load_client_profile(path)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "client_id" in str(e)

    def test_defaults_threshold(self, tmp_path):
        data = {"client_id": "c2"}
        path = _write_yaml(tmp_path, "c2.yaml", data)
        profile = load_client_profile(path)
        assert profile.alert_threshold == 30.0


class TestLoadAllProfiles:
    def test_loads_all_yaml_files(self, tmp_path):
        _write_yaml(tmp_path, "a.yaml", {"client_id": "a", "is_active": True})
        _write_yaml(tmp_path, "b.yml", {"client_id": "b", "is_active": True})
        _write_yaml(tmp_path, "readme.txt", {"client_id": "skip"})  # not yaml

        profiles = load_all_profiles(tmp_path)
        ids = [p.client_id for p in profiles]

        assert "a" in ids
        assert "b" in ids
        assert "skip" not in ids

    def test_skips_inactive(self, tmp_path):
        _write_yaml(tmp_path, "active.yaml", {"client_id": "active", "is_active": True})
        _write_yaml(tmp_path, "inactive.yaml", {"client_id": "inactive", "is_active": False})

        profiles = load_all_profiles(tmp_path)
        ids = [p.client_id for p in profiles]

        assert "active" in ids
        assert "inactive" not in ids

    def test_skips_invalid_files(self, tmp_path):
        _write_yaml(tmp_path, "good.yaml", {"client_id": "good"})
        # Write invalid YAML content
        (tmp_path / "bad.yaml").write_text("not: valid: yaml: [")

        profiles = load_all_profiles(tmp_path)
        # Should still load the good one
        assert len(profiles) >= 1

    def test_empty_dir_returns_empty(self, tmp_path):
        profiles = load_all_profiles(tmp_path)
        assert profiles == []

    def test_missing_dir_returns_empty(self):
        profiles = load_all_profiles(Path("/nonexistent/path"))
        assert profiles == []


class TestGetClientMetadata:
    def test_extracts_metadata(self, tmp_path):
        data = {
            "client_id": "test",
            "client_name": "Test Corp",
            "is_active": True,
            "alert_threshold": 78,
            "digest_threshold": 58,
            "positive_keywords": ["test"],
        }
        path = _write_yaml(tmp_path, "test.yaml", data)

        meta = get_client_metadata(path)

        assert meta["client_id"] == "test"
        assert meta["display_name"] == "Test Corp"
        assert meta["is_active"] is True
        assert meta["alert_threshold"] == 78
        assert meta["digest_threshold"] == 58
        assert "profile_yaml" in meta
