"""Tests for bill ID normalization and canonical version ID generation."""

import pytest

from src.utils.bill_id import (
    bill_id_to_chamber,
    bill_id_to_number,
    make_canonical_version_id,
    normalize_bill_id,
)


class TestNormalizeBillId:
    def test_simple_senate(self):
        assert normalize_bill_id("SB 93") == "SB00093"

    def test_simple_house(self):
        assert normalize_bill_id("HB 5140") == "HB05140"

    def test_dotted_senate(self):
        assert normalize_bill_id("S.B. 93") == "SB00093"

    def test_dotted_house(self):
        assert normalize_bill_id("H.B. 5140") == "HB05140"

    def test_full_name_senate(self):
        assert normalize_bill_id("Senate Bill 93") == "SB00093"

    def test_full_name_house(self):
        assert normalize_bill_id("House Bill 5140") == "HB05140"

    def test_already_normalized(self):
        assert normalize_bill_id("SB00093") == "SB00093"

    def test_no_number_prefix(self):
        assert normalize_bill_id("SB93") == "SB00093"

    def test_with_no_abbreviation(self):
        assert normalize_bill_id("S.B. No. 93") == "SB00093"

    def test_whitespace_handling(self):
        assert normalize_bill_id("  HB   1  ") == "HB00001"

    def test_case_insensitive(self):
        assert normalize_bill_id("sb 93") == "SB00093"
        assert normalize_bill_id("hb 5140") == "HB05140"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize_bill_id("XB 100")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize_bill_id("")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize_bill_id("not a bill")


class TestBillIdToChamber:
    def test_house(self):
        assert bill_id_to_chamber("HB05140") == "house"

    def test_senate(self):
        assert bill_id_to_chamber("SB00093") == "senate"

    def test_invalid(self):
        with pytest.raises(ValueError):
            bill_id_to_chamber("XB00001")


class TestBillIdToNumber:
    def test_extracts_number(self):
        assert bill_id_to_number("SB00093") == 93
        assert bill_id_to_number("HB05140") == 5140


class TestMakeCanonicalVersionId:
    def test_basic(self):
        result = make_canonical_version_id(2026, "SB00093", 44)
        assert result == "2026-SB00093-FC00044"

    def test_small_numbers(self):
        result = make_canonical_version_id(2026, "HB00001", 1)
        assert result == "2026-HB00001-FC00001"

    def test_large_numbers(self):
        result = make_canonical_version_id(2026, "HB99999", 99999)
        assert result == "2026-HB99999-FC99999"
