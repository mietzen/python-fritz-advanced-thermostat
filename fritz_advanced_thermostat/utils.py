"""Fritz!Box connection and thermostat data generation utilities."""

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests
import urllib3

from .errors import (
    FritzAdvancedThermostatConnectionError,
    FritzAdvancedThermostatExecutionError,
)

# Silence annoying urllib3 Unverified HTTPS warnings, even so if we have checked verify ssl false in requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FritzConnection:
    """Handle HTTP communication with the Fritz!Box."""

    def __init__(self, prefixed_host: str, max_retries: int, timeout: int, ssl_verify: bool) -> None:
        """Initialize connection parameters."""
        self._prefixed_host = prefixed_host
        self._max_retries = max_retries
        self._timeout = timeout
        self._ssl_verify = ssl_verify
        self._logger = logging.getLogger("FritzAdvancedThermostatLogger")
        self._sid = None

    def _generate_headers(self, data: dict) -> dict:
        self._logger.debug("Generating headers for the request.")
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self._prefixed_host,
            "Content-Length": str(len(data)),
            "Accept-Language": "en-GB,en;q=0.9",
            "Host": self._prefixed_host.split("://")[1],
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.2 Safari/605.1.15",
            "Referer": self._prefixed_host,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self._logger.debug("Headers generated: %s", headers)
        return headers

    def post_req(self, payload: dict, site: str) -> str:
        """Send a POST request to the Fritz!Box."""
        url = f"{self._prefixed_host}/{site}"
        payload = {"sid": self._sid} | payload
        self._logger.debug("Sending POST request to %s", url)
        self._logger.debug("Payload: %s", payload)

        data_pkg = []
        for key, value in payload.items():
            if value is None:
                data_pkg.append(key + "=")
            elif isinstance(value, bool):
                if value:
                    data_pkg.append(key + "=on")
            elif value:
                data_pkg.append(key + "=" + quote(str(value), safe=""))

        response = None

        retries = 0
        while retries <= self._max_retries:
            try:
                self._logger.debug("Attempt %s of %s", retries + 1, self._max_retries)
                response = requests.post(
                    url,
                    headers=self._generate_headers(payload),
                    data="&".join(data_pkg),
                    verify=self._ssl_verify,
                    timeout=self._timeout,
                )
                self._logger.debug("Request successful on attempt %s", retries + 1)
                break
            except requests.ConnectionError as e:
                self._logger.warning("Connection Error on attempt %s: %s", retries + 1, e)
                retries += 1
                if retries > self._max_retries:
                    err = f"Tried {self._max_retries} times, Connection Error on loading raw thermostat data"
                    self._logger.exception(err)
                    raise FritzAdvancedThermostatConnectionError(err) from e
                self._logger.debug("Retrying request, attempt %s of %s", retries + 1, self._max_retries)
        if not response:
            err = "Error: Empty response!"
            self._logger.error("Request failed: %s", err)
            raise FritzAdvancedThermostatConnectionError(err)

        self._logger.debug("Received response with status code: %s", response.status_code)

        if response.status_code != requests.codes.ok:
            err = "Error: " + str(response.status_code)
            self._logger.error("Request failed: %s", err)
            raise FritzAdvancedThermostatConnectionError(err)

        self._logger.debug("Response received: %s", response.text)
        return response.text

    def login(self, user: str, password: str) -> None:
        """Authenticate with the Fritz!Box using PBKDF2 challenge-response."""
        url = "/".join([self._prefixed_host, f"login_sid.lua?version=2&user={user}"])
        response = requests.get(
            url, verify=self._ssl_verify, timeout=self._timeout)

        xml_root = ET.fromstring(response.content)
        sid = xml_root.findtext("SID")

        if sid == "0000000000000000":
            challenge_parts = str(xml_root.findtext("Challenge")).split("$")
            iter1 = int(challenge_parts[1])
            salt1 = bytes.fromhex(challenge_parts[2])
            iter2 = int(challenge_parts[3])
            salt2 = bytes.fromhex(challenge_parts[4])

            hash1 = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt1, iter1)
            hash2 = hashlib.pbkdf2_hmac("sha256", hash1, salt2, iter2)

            payload = {
                "response": f"{salt2.hex()}${hash2.hex()}",
                "user": user,
            }
            login_response = requests.post(
                url, data=payload, verify=self._ssl_verify, timeout=self._timeout)
            login_root = ET.fromstring(login_response.content)

            sid = login_root.findtext("SID")

            if sid == "0000000000000000":
                err = "Invalid user or password!"
                self._logger.error(err)
                raise FritzAdvancedThermostatConnectionError(err)
        self._sid = sid

    def get_fritz_os_version(self) -> str:
        """Retrieve the Fritz!OS version from the Fritz!Box."""
        payload = {
            "xhr": "1",
            "page": "overview",
            "xhrId": "first",
            "noMenuRef": "1"}
        response = self.post_req(
            payload, "data.lua")

        try:
            req_data = json.loads(response)
        except json.decoder.JSONDecodeError as e:
            err = "Error: Didn't get a valid json response when loading data\n" + response
            self._logger.exception(err)
            raise FritzAdvancedThermostatExecutionError(err) from e

        if "fritzos" not in req_data["data"]:
            err = "Error: Something went wrong loading the fritzos meta data\n" + response
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

        return req_data["data"]["fritzos"]["nspver"]

class ThermostatDataGenerator:
    """Generate thermostat data packages from raw Fritz!Box device data."""

    def __init__(self, fritz_conn: FritzConnection) -> None:
        """Initialize with a Fritz!Box connection."""
        self._fritz_requests = fritz_conn
        self._logger = logging.getLogger("FritzAdvancedThermostatLogger")

    def _get_object(self, device: dict, unit_name: str, skill_type: str, skill_name: str | None = None) -> any:
        self._logger.debug("Getting object: unit_name=%s, skill_type=%s, skill_name=%s", unit_name, skill_type, skill_name)
        thermostat_obj = None
        for unit in device["units"]:
            if unit["type"] == unit_name:
                if skill_name:
                    for skill in unit["skills"]:
                        if skill["type"] == skill_type:
                            thermostat_obj = skill[skill_name]
                            self._logger.debug("Found object: %s", thermostat_obj)
                else:
                    thermostat_obj = unit
                    self._logger.debug("Found unit: %s", thermostat_obj)
        if thermostat_obj is None:
            self._logger.warning("Object not found: unit_name=%s, skill_type=%s", unit_name, skill_type)
        return thermostat_obj

    def _get_schedule(self, schedules: list, schedule_name: str) -> dict | None:
        self._logger.debug("Getting schedule: %s", schedule_name)
        schedule = [x for x in schedules if x["name"] == schedule_name]
        if schedule:
            self._logger.debug("Schedule found: %s", schedule[0])
            return schedule[0]
        self._logger.warning("Schedule not found: %s", schedule_name)
        return None

    def _get_temperature(self, presets: list, target: str) -> str:
        self._logger.debug("Getting temperature preset: %s", target)
        temp = "7.5"  # Default: Off/AUS
        for preset in presets:
            if preset["name"] == target:
                temp = str(preset["temperature"])
                self._logger.debug("Temperature found: %s", temp)
                break
        return temp

    def _get_lock(self, locks: list, target: str) -> bool:
        self._logger.debug("Checking lock status: %s", target)
        locked = False
        for lock in locks:
            if lock["devControlName"] == target and lock["isLocked"]:
                locked = True
                self._logger.debug("%s is locked", target)
                break
        return locked

    def _get_holiday_temp(self, device_id: int) -> str:
        # I found no other way then to parse the HTML with a regex, I don't know where I can find this.
        self._logger.debug("Getting holiday temperature for device ID: %s", device_id)
        payload = {
            "xhr": "1",
            "device": device_id,
            "page": "home_auto_hkr_edit",
        }
        response = self._fritz_requests.post_req(payload, "data.lua")
        regex = r'(?<=<input type="hidden" name="Holidaytemp" value=")\d+\.?\d?(?=" id="uiNum:Holidaytemp">)'
        holiday_temp = re.findall(regex, response)[0]
        self._logger.debug("Holiday temperature found: %s", holiday_temp)
        return holiday_temp

    def _first_day_in_bitmask(self, bitmask: int) -> int:
        self._logger.debug("Determining first day in bitmask: %s", bitmask)
        for i in range(7):
            if bitmask & (1 << i):
                self._logger.debug("First day in bitmask: %s", i)
                return i
        self._logger.warning("No day found in bitmask")
        return -1

    def _generate_weekly_timers(self, raw_timers: dict) -> dict:
        """Convert weekly timer actions to Fritz!Box timer format.

        Week Binary Conversion (reversed)::

            Mo Tu We Th Fr Sa Su
            1  1  1  1  1  1  1  = 127
            1  0  0  0  0  1  0  = 33
            0  0  1  1  0  1  0  = 44

            timer_item_x=${TIME};${STATE};${DAYS}
            timer_item_0=  0530 ;    1   ; 127
            This means turn the device on at 5:30 on all days of the week
        """
        self._logger.debug("Generating weekly timers for raw timers: %s", raw_timers)

        weekly_timers = {}
        # day - bitmask mapping
        day_to_bit = {
            "MON": 1 << 0,   # Monday -> 1
            "TUE": 1 << 1,   # Tuesday -> 2
            "WED": 1 << 2,   # Wednesday -> 4
            "THU": 1 << 3,   # Thursday -> 8
            "FRI": 1 << 4,   # Friday -> 16
            "SAT": 1 << 5,   # Saturday -> 32
            "SUN": 1 << 6,    # Sunday -> 64
        }

        # action states mapping
        set_action = {
            "UPPER_TEMPERATURE": 1,
            "LOWER_TEMPERATURE": 0,
            "SET_OFF": 0,
        }
        combined_times = {}
        for action in raw_timers["actions"]:
            day = action["timeSetting"]["dayOfWeek"]
            start_time = action["timeSetting"]["startTime"]

            if "presetTemperature" in action["description"]:
                state = action["description"]["presetTemperature"]["name"]
            elif action["description"]["action"] == "SET_OFF":
                state = "SET_OFF"
            else:
                err = "Error: state not found!"
                self._logger.exception(err)
                raise FritzAdvancedThermostatExecutionError(err)

            # Get bitmask and category for the action
            if day in day_to_bit:
                bitmask = day_to_bit[day]
                category = set_action[state]
                time_str = start_time.replace(":", "")[:4]  # Format time to HHMM
                key = (time_str, category)

                # Initialize bitmask if not present
                if key not in combined_times:
                    combined_times[key] = 0

                # Update the bitmask for the day
                combined_times[key] |= bitmask

        sorted_times = sorted(combined_times.items(), key=lambda x: (self._first_day_in_bitmask(x[1]), x[0][0]))

        for i, ((time_str, category), bitmask) in enumerate(sorted_times):
            weekly_timers[f"timer_item_{i}"] = f"{time_str};{category};{bitmask}"
            self._logger.debug("Generated weekly timer: timer_item_%s = %s", i, weekly_timers[f"timer_item_{i}"])

        self._logger.debug("Weekly timers generation complete")
        return weekly_timers

    def _generate_holiday_schedule(self, raw_holidays: dict, device_id: int) -> dict:
        self._logger.debug("Generating holiday schedule for device %s", device_id)

        holiday_schedule = {}
        holiday_id_count = 0
        actions = raw_holidays.get("actions", [])

        for i in range(1, 5):  # Always output all 4 holiday slots
            if i <= len(actions):
                holiday = actions[i - 1]
                if holiday["isEnabled"]:
                    holiday_id_count += 1
                holiday_schedule[f"Holiday{i}Enabled"] = "1" if holiday["isEnabled"] else "0"
                holiday_schedule[f"Holiday{i}EndDay"] = str(int(holiday["timeSetting"]["endDate"].split("-")[2]))
                holiday_schedule[f"Holiday{i}EndHour"] = str(int(holiday["timeSetting"]["endTime"].split(":")[0]))
                holiday_schedule[f"Holiday{i}EndMonth"] = holiday["timeSetting"]["endDate"].split("-")[1]
                holiday_schedule[f"Holiday{i}ID"] = str(i)
                holiday_schedule[f"Holiday{i}StartDay"] = str(int(holiday["timeSetting"]["startDate"].split("-")[2]))
                holiday_schedule[f"Holiday{i}StartHour"] = str(int(holiday["timeSetting"]["startTime"].split(":")[0]))
                holiday_schedule[f"Holiday{i}StartMonth"] = holiday["timeSetting"]["startDate"].split("-")[1]
                self._logger.debug("Holiday schedule %s generated (enabled=%s)", i, holiday["isEnabled"])

        holiday_schedule["HolidayEnabledCount"] = str(holiday_id_count)
        if holiday_id_count > 0:
            holiday_schedule["Holidaytemp"] = self._get_holiday_temp(device_id)
            self._logger.debug("Holiday temperature for device %s: %s", device_id, holiday_schedule["Holidaytemp"])

        self._logger.debug("Holiday schedule generation complete for device %s", device_id)
        return holiday_schedule


    def _generate_summer_time_schedule(self, raw_summer_time: dict) -> dict:
        self._logger.debug("Generating summer time schedule")

        summer_time_schedule = {}
        if raw_summer_time["isEnabled"]:
            summer_time_schedule["SummerEnabled"] = "1"
            summer_time_schedule["SummerEndDay"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["endDate"].split("-")[2]))
            summer_time_schedule["SummerEndMonth"] = raw_summer_time["actions"][0]["timeSetting"]["endDate"].split("-")[1]
            summer_time_schedule["SummerStartDay"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["startDate"].split("-")[2]))
            summer_time_schedule["SummerStartMonth"] = raw_summer_time["actions"][0]["timeSetting"]["startDate"].split("-")[1]
            self._logger.debug("Summer time schedule generated: %s", summer_time_schedule)
        else:
            summer_time_schedule["SummerEnabled"] = "0"
            self._logger.debug("Summer time schedule is not enabled")

        self._logger.debug("Summer time schedule generation complete")
        return summer_time_schedule


    def generate(self, raw_device_data: dict) -> dict:
        """Generate thermostat data from raw Fritz!Box device data."""
        self._logger.debug("Starting to generate thermostat data for raw device data: %s", raw_device_data)

        thermostat_data = {}
        for device in raw_device_data["devices"]:
            name = device["displayName"]
            grouped = name in [i["displayName"] for i in [i["members"] for i in raw_device_data["groups"]][0]]
            if device["category"] == "THERMOSTAT":
                self._logger.debug("Processing thermostat device: %s", name)
                thermostat_data[name] = {}
                offset = self._get_object(device, "TEMPERATURE_SENSOR",  "SmartHomeTemperatureSensor", "offset")
                thermostat_data[name]["Offset"] = str(int(offset)) if offset == int(offset) else str(offset)
                thermostat_data[name]["WindowOpenTimer"] = str(
                    self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "temperatureDropDetection")["doNotHeatOffsetInMinutes"])
                # WindowOpenTrigger musst always be + 3
                #   xhr  -  json     GUI
                # 4  (01)    1   -> niedrig
                # 8  (10)    5   -> mittel
                # 12 (11)    9   -> hoch
                thermostat_data[name]["WindowOpenTrigger"] = str(
                    self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "temperatureDropDetection")["sensitivity"] + 3)
                self._logger.debug("Offset and window settings for %s: Offset=%s, WindowOpenTimer=%s, WindowOpenTrigger=%s",
                                name, thermostat_data[name]["Offset"], thermostat_data[name]["WindowOpenTimer"], thermostat_data[name]["WindowOpenTrigger"])

                locks = self._get_object(device, "THERMOSTAT", "SmartHomeThermostat")["interactionControls"]
                thermostat_data[name]["locklocal"] = self._get_lock(locks, "BUTTON")
                thermostat_data[name]["lockuiapp"] = self._get_lock(locks, "EXTERNAL")
                self._logger.debug("Lock settings for %s: locklocal=%s, lockuiapp=%s",
                                name, thermostat_data[name]["locklocal"], thermostat_data[name]["lockuiapp"])

                used_temp_sensor = self._get_object(device, "THERMOSTAT", "SmartHomeThermostat", "usedTempSensor")
                if used_temp_sensor:
                    room_temp = used_temp_sensor["skills"][0]["currentInCelsius"]
                    thermostat_data[name]["Roomtemp"] = str(int(room_temp)) if room_temp == int(room_temp) else str(room_temp)

                if not grouped:
                    adaptiv_heating = self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "adaptivHeating")
                    thermostat_data[name]["hkr_adaptheat"] = "1" if (adaptiv_heating["isEnabled"] and adaptiv_heating["supported"]) else "0"
                    self._logger.debug("Adaptive heating for %s: %s", name, thermostat_data[name]["hkr_adaptheat"])
                    thermostat_data[name]["graphState"] = "1"
                    temperatures = self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "presets")
                    thermostat_data[name]["Absenktemp"] = self._get_temperature(temperatures, "LOWER_TEMPERATURE")
                    thermostat_data[name]["Heiztemp"] = self._get_temperature(temperatures, "UPPER_TEMPERATURE")
                    self._logger.debug("Temperature settings for %s: Absenktemp=%s, Heiztemp=%s",
                                    name, thermostat_data[name]["Absenktemp"], thermostat_data[name]["Heiztemp"])

                    summer_time = self._get_schedule(self._get_object(device, "THERMOSTAT", "SmartHomeThermostat", "timeControl")["timeSchedules"], "SUMMER_TIME")
                    if summer_time:
                        thermostat_data[name] |= self._generate_summer_time_schedule(summer_time)
                        self._logger.debug("Summer time schedule for %s generated", name)

                    holidays = self._get_schedule(self._get_object(device, "THERMOSTAT", "SmartHomeThermostat", "timeControl")["timeSchedules"], "HOLIDAYS")
                    if holidays:
                        thermostat_data[name] |= self._generate_holiday_schedule(holidays, device["id"])
                        self._logger.debug("Holiday schedule for %s generated", name)

                    raw_weekly_timetable = self._get_schedule(self._get_object(device, "THERMOSTAT", "SmartHomeThermostat", "timeControl")["timeSchedules"], "TEMPERATURE")
                    if raw_weekly_timetable:
                        thermostat_data[name] |= self._generate_weekly_timers(raw_weekly_timetable)
                        self._logger.debug("Weekly timers for %s generated", name)

        self._logger.debug("Thermostat data generation complete")
        return thermostat_data
