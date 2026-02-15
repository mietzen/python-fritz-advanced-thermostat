import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest

from fritz_advanced_thermostat import FritzAdvancedThermostat


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _parse_payload_fixture(filename: str) -> dict:
    """Parse a payload fixture file into a dict of key=value pairs."""
    fixture_path = FIXTURES_DIR / filename
    result = {}
    for line in fixture_path.read_text().strip().splitlines():
        key, _, value = line.partition("=")
        result[key] = value
    return result


def _serialize_data_pkg(data_pkg: dict) -> dict:
    """Serialize a data_pkg dict the same way post_req does (minus sid)."""
    result = {}
    for key, value in data_pkg.items():
        if value is None:
            result[key] = ""
        elif isinstance(value, bool):
            if value:
                result[key] = "on"
            # False bools are skipped entirely
        elif value:
            result[key] = quote(str(value), safe="")
    return result


@pytest.fixture
def raw_device_data():
    with open(FIXTURES_DIR / "raw_device_data.json") as f:
        return json.load(f)


@pytest.fixture
def fat(raw_device_data):
    """Create a FritzAdvancedThermostat with mocked connection."""
    with patch("fritz_advanced_thermostat.FritzConnection") as MockConn:
        mock_conn = MockConn.return_value
        mock_conn.get_fritz_os_version.return_value = "7.60"
        mock_conn.post_req.return_value = ""

        fat = FritzAdvancedThermostat(
            host="192.168.178.1",
            user="testuser",
            password="testpass",
        )
        # Inject fixture data directly, bypassing HTTP
        fat._raw_device_data = raw_device_data
        fat._thermostat_data = {}
        return fat


class TestDataPkgGrouped:
    """Test _generate_data_pkg for a grouped thermostat against Fritz!Box fixture."""

    def test_data_pkg_matches_fixture(self, fat):
        with open(FIXTURES_DIR / "expected_data_pkg_grouped.json") as f:
            expected = json.load(f)

        data_pkg = fat._generate_data_pkg("Living Room West")
        assert data_pkg == expected

    def test_serialized_payload_matches_fritzbox(self, fat):
        expected = _parse_payload_fixture("expected_payload_grouped.txt")

        data_pkg = fat._generate_data_pkg("Living Room West")
        serialized = _serialize_data_pkg(data_pkg)

        # Sort both for stable comparison
        assert dict(sorted(serialized.items())) == dict(sorted(expected.items()))

    def test_no_schedule_fields_in_payload(self, fat):
        data_pkg = fat._generate_data_pkg("Living Room West")
        schedule_keys = [
            "Absenktemp", "Heiztemp", "graphState",
            "SummerEnabled", "Holiday1Enabled", "timer_item_0",
            "hkr_adaptheat",
        ]
        for key in schedule_keys:
            assert key not in data_pkg, f"Grouped thermostat should not have {key}"


class TestDataPkgUngrouped:
    """Test _generate_data_pkg for an ungrouped thermostat against Fritz!Box fixture."""

    def test_data_pkg_matches_fixture(self, fat):
        with open(FIXTURES_DIR / "expected_data_pkg_ungrouped.json") as f:
            expected = json.load(f)

        data_pkg = fat._generate_data_pkg("Kitchen")
        assert data_pkg == expected

    def test_serialized_payload_matches_fritzbox(self, fat):
        expected = _parse_payload_fixture("expected_payload_ungrouped.txt")

        data_pkg = fat._generate_data_pkg("Kitchen")
        serialized = _serialize_data_pkg(data_pkg)

        assert dict(sorted(serialized.items())) == dict(sorted(expected.items()))

    def test_has_all_holiday_slots(self, fat):
        data_pkg = fat._generate_data_pkg("Kitchen")
        for i in range(1, 5):
            assert f"Holiday{i}Enabled" in data_pkg
            assert f"Holiday{i}ID" in data_pkg

    def test_has_timer_items(self, fat):
        data_pkg = fat._generate_data_pkg("Kitchen")
        assert data_pkg["timer_item_0"] == "0500;1;127"
        assert data_pkg["timer_item_1"] == "2200;0;127"

    def test_has_summer_schedule(self, fat):
        data_pkg = fat._generate_data_pkg("Kitchen")
        assert data_pkg["SummerEnabled"] == "1"
        assert data_pkg["SummerStartMonth"] == "05"
        assert data_pkg["SummerEndMonth"] == "09"


class TestDataPkgCommonFields:
    """Test fields common to both grouped and ungrouped data packages."""

    @pytest.mark.parametrize("device_name", ["Living Room West", "Kitchen"])
    def test_has_required_metadata(self, fat, device_name):
        data_pkg = fat._generate_data_pkg(device_name)
        assert data_pkg["back_to_page"] == "/smarthome/devices.lua"
        assert data_pkg["tempsensor"] == "own"
        assert data_pkg["ExtTempsensorID"] == "tochoose"
        assert data_pkg["xhr"] == "1"
        assert data_pkg["lang"] == "de"
        assert data_pkg["apply"] is None
        assert data_pkg["view"] is None

    @pytest.mark.parametrize("device_name", ["Living Room West", "Kitchen"])
    def test_has_device_id(self, fat, device_name):
        data_pkg = fat._generate_data_pkg(device_name)
        assert isinstance(data_pkg["device"], int)

    @pytest.mark.parametrize("device_name", ["Living Room West", "Kitchen"])
    def test_has_ule_device_name(self, fat, device_name):
        data_pkg = fat._generate_data_pkg(device_name)
        assert data_pkg["ule_device_name"] == device_name

    @pytest.mark.parametrize("device_name", ["Living Room West", "Kitchen"])
    def test_false_bools_omitted_in_serialization(self, fat, device_name):
        """locklocal=False and lockuiapp=False should be omitted from the serialized payload."""
        data_pkg = fat._generate_data_pkg(device_name)
        serialized = _serialize_data_pkg(data_pkg)
        assert "locklocal" not in serialized
        assert "lockuiapp" not in serialized
