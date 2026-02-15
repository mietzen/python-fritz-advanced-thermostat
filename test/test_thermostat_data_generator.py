import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fritz_advanced_thermostat.utils import ThermostatDataGenerator


@pytest.fixture
def raw_device_data():
    fixture_path = Path(__file__).parent / "fixtures" / "raw_device_data.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def generator():
    fritz_conn = MagicMock()
    return ThermostatDataGenerator(fritz_conn)


@pytest.fixture
def thermostat_data(generator, raw_device_data):
    return generator.generate(raw_device_data)


class TestGenerateGroupedThermostat:
    """Tests for grouped thermostats (Living Room West / Living Room North)."""

    def test_grouped_devices_detected(self, thermostat_data):
        assert "Living Room West" in thermostat_data
        assert "Living Room North" in thermostat_data

    def test_grouped_has_no_hkr_adaptheat(self, thermostat_data):
        assert "hkr_adaptheat" not in thermostat_data["Living Room West"]
        assert "hkr_adaptheat" not in thermostat_data["Living Room North"]

    def test_grouped_has_no_graph_state(self, thermostat_data):
        assert "graphState" not in thermostat_data["Living Room West"]

    def test_grouped_has_no_schedule_fields(self, thermostat_data):
        data = thermostat_data["Living Room West"]
        assert "Absenktemp" not in data
        assert "Heiztemp" not in data
        assert "SummerEnabled" not in data
        assert "Holiday1Enabled" not in data
        assert "timer_item_0" not in data

    def test_grouped_offset_float(self, thermostat_data):
        assert thermostat_data["Living Room West"]["Offset"] == "-3.5"

    def test_grouped_offset_integer(self, thermostat_data):
        assert thermostat_data["Living Room North"]["Offset"] == "-1"

    def test_grouped_window_open_timer(self, thermostat_data):
        assert thermostat_data["Living Room West"]["WindowOpenTimer"] == "10"

    def test_grouped_window_open_trigger(self, thermostat_data):
        # sensitivity (5) + 3 = 8
        assert thermostat_data["Living Room West"]["WindowOpenTrigger"] == "8"

    def test_grouped_locks(self, thermostat_data):
        assert thermostat_data["Living Room West"]["locklocal"] is False
        assert thermostat_data["Living Room West"]["lockuiapp"] is False

    def test_grouped_roomtemp_integer(self, thermostat_data):
        assert thermostat_data["Living Room West"]["Roomtemp"] == "21"

    def test_grouped_roomtemp_float(self, thermostat_data):
        assert thermostat_data["Living Room North"]["Roomtemp"] == "21.5"


class TestGenerateUngroupedThermostat:
    """Tests for ungrouped thermostat (Kitchen)."""

    def test_ungrouped_device_detected(self, thermostat_data):
        assert "Kitchen" in thermostat_data

    def test_ungrouped_offset(self, thermostat_data):
        assert thermostat_data["Kitchen"]["Offset"] == "-4"

    def test_ungrouped_has_hkr_adaptheat(self, thermostat_data):
        assert thermostat_data["Kitchen"]["hkr_adaptheat"] == "1"

    def test_ungrouped_has_graph_state(self, thermostat_data):
        assert thermostat_data["Kitchen"]["graphState"] == "1"

    def test_ungrouped_temperatures(self, thermostat_data):
        assert thermostat_data["Kitchen"]["Absenktemp"] == "17.5"
        assert thermostat_data["Kitchen"]["Heiztemp"] == "20.5"

    def test_ungrouped_window_settings(self, thermostat_data):
        assert thermostat_data["Kitchen"]["WindowOpenTimer"] == "30"
        assert thermostat_data["Kitchen"]["WindowOpenTrigger"] == "8"

    def test_ungrouped_roomtemp(self, thermostat_data):
        assert thermostat_data["Kitchen"]["Roomtemp"] == "21.5"

    def test_ungrouped_locks(self, thermostat_data):
        assert thermostat_data["Kitchen"]["locklocal"] is False
        assert thermostat_data["Kitchen"]["lockuiapp"] is False


class TestSummerTimeSchedule:
    def test_summer_enabled(self, thermostat_data):
        assert thermostat_data["Kitchen"]["SummerEnabled"] == "1"

    def test_summer_start(self, thermostat_data):
        assert thermostat_data["Kitchen"]["SummerStartDay"] == "21"
        assert thermostat_data["Kitchen"]["SummerStartMonth"] == "05"

    def test_summer_end(self, thermostat_data):
        assert thermostat_data["Kitchen"]["SummerEndDay"] == "10"
        assert thermostat_data["Kitchen"]["SummerEndMonth"] == "09"


class TestHolidaySchedule:
    def test_all_disabled_holidays_present(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        for i in range(1, 5):
            assert f"Holiday{i}Enabled" in data
            assert f"Holiday{i}ID" in data
            assert f"Holiday{i}StartDay" in data
            assert f"Holiday{i}StartHour" in data
            assert f"Holiday{i}StartMonth" in data
            assert f"Holiday{i}EndDay" in data
            assert f"Holiday{i}EndHour" in data
            assert f"Holiday{i}EndMonth" in data

    def test_all_holidays_disabled(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        for i in range(1, 5):
            assert data[f"Holiday{i}Enabled"] == "0"

    def test_holiday_enabled_count_zero(self, thermostat_data):
        assert thermostat_data["Kitchen"]["HolidayEnabledCount"] == "0"

    def test_holiday_ids_sequential(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        for i in range(1, 5):
            assert data[f"Holiday{i}ID"] == str(i)

    def test_disabled_holiday_dates_from_json(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        # Kitchen holidays have startDate=2019-02-15, endDate=2019-03-01
        assert data["Holiday1StartDay"] == "15"
        assert data["Holiday1StartMonth"] == "02"
        assert data["Holiday1EndDay"] == "1"
        assert data["Holiday1EndMonth"] == "03"

    def test_disabled_holiday_hours_from_json(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        # Kitchen holidays have startTime=00:00:00, endTime=00:00:00
        assert data["Holiday1StartHour"] == "0"
        assert data["Holiday1EndHour"] == "0"


class TestWeeklyTimers:
    def test_timer_items_present(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        assert "timer_item_0" in data
        assert "timer_item_1" in data

    def test_timer_format(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        # All days same schedule: 05:00 ON, 22:00 OFF -> bitmask 127 (all days)
        assert data["timer_item_0"] == "0500;1;127"
        assert data["timer_item_1"] == "2200;0;127"

    def test_timer_values_not_placeholders(self, thermostat_data):
        data = thermostat_data["Kitchen"]
        for key, value in data.items():
            if key.startswith("timer_item_"):
                assert "{" not in value, f"{key} contains unresolved placeholder: {value}"
                assert "}" not in value, f"{key} contains unresolved placeholder: {value}"


class TestHolidayWithEnabled:
    """Test holiday schedule when some holidays are enabled (Living Room devices have 1 enabled)."""

    def test_first_holiday_enabled(self, thermostat_data, generator):
        # Living Room West is grouped, so no holidays in its data.
        # We need to test _generate_holiday_schedule directly with fixture data.
        pass

    def test_generate_holiday_with_enabled(self, generator, raw_device_data):
        """Directly test _generate_holiday_schedule with data that has 1 enabled holiday."""
        device = raw_device_data["devices"][0]  # Living Room West
        thermostat_skill = device["units"][0]["skills"][0]
        holidays = [s for s in thermostat_skill["timeControl"]["timeSchedules"] if s["name"] == "HOLIDAYS"][0]

        # Mock _get_holiday_temp since it makes HTTP requests
        generator._get_holiday_temp = MagicMock(return_value="22")
        result = generator._generate_holiday_schedule(holidays, device["id"])

        assert result["Holiday1Enabled"] == "1"
        assert result["Holiday1StartDay"] == "1"
        assert result["Holiday1StartMonth"] == "05"
        assert result["Holiday1EndDay"] == "20"
        assert result["Holiday1EndMonth"] == "05"
        assert result["Holiday1StartHour"] == "0"
        assert result["Holiday1EndHour"] == "23"

        assert result["Holiday2Enabled"] == "0"
        assert result["Holiday3Enabled"] == "0"
        assert result["Holiday4Enabled"] == "0"

        assert result["HolidayEnabledCount"] == "1"
        assert result["Holidaytemp"] == "22"
