import json
import logging
import re
import sys
from urllib.parse import quote

import requests
import urllib3
import hashlib
from packaging import version
import xml.etree.ElementTree as ET

# Silence annoying urllib3 Unverified HTTPS warnings, even so if we have checked verify ssl false in requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .errors import (
    FritzAdvancedThermostatCompatibilityError,
    FritzAdvancedThermostatConnectionError,
    FritzAdvancedThermostatExecutionError,
    FritzAdvancedThermostatKeyError,
)

PYTHON_VERSION = ".".join([str(x) for x in sys.version_info[0:3]])


def get_logger(name: str, level: str = 'warning'):
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


class FritzAdvancedThermostat:
    def __init__(
            self,
            host,
            user,
            password,
            ssl_verify=False,
            experimental=False,
            log_level="warning",
            timeout=60,
            retries=3):
        # Get logger
        self._logger = get_logger(
            'FritzAdvancedThermostatLogger', level=log_level)

        if experimental:
            self._logger.warning("Experimental mode! All checks disabled!")

        if version.parse(PYTHON_VERSION) < version.parse("3.9.0"):
            err = "Error: Update Python!\nPython version: " + PYTHON_VERSION + "\n"\
                "Min. required Python version: 3.9.0"
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

        self._supported_firmware = ["7.29", "7.30", "7.31", "7.56", "7.57"]
        # Set basic properties
        self._experimental = experimental
        self._ssl_verify = ssl_verify
        self._timeout = timeout
        self._retries = retries
        # Set data structures
        self._thermostat_data = dict()
        self._raw_device_data = dict()
        self._changed_devices = set()
        self._thermostats = set()
        self._settable_keys = {
            "common": (
                "Offset",
                "WindowOpenTimer",
                "WindowOpenTrigger",
                "locklocal",
                "lockuiapp",
            ),
            "ungrouped": (
                "Absenktemp", "Heiztemp", "Holiday1Enabled", "Holiday1EndDay", "Holiday1EndHour", "Holiday1EndMonth",
                "Holiday1StartDay", "Holiday1StartHour", "Holiday1StartMonth", "Holiday2Enabled", "Holiday2EndDay",
                "Holiday2EndHour", "Holiday2EndMonth", "Holiday2StartDay", "Holiday2StartHour", "Holiday2StartMonth",
                "Holiday3Enabled", "Holiday3EndDay", "Holiday3EndHour", "Holiday3EndMonth", "Holiday3StartDay",
                "Holiday3StartHour", "Holiday3StartMonth", "Holiday4Enabled", "Holiday4EndDay", "Holiday4EndHour",
                "Holiday4EndMonth", "Holiday4StartDay", "Holiday4StartHour", "Holiday4StartMonth", "Holidaytemp",
                "SummerEnabled", "SummerEndDay", "SummerEndMonth", "SummerStartDay", "SummerStartMonth",
            ),
        }

        self._supported_thermostats = ["FRITZ!DECT 301"]
        self._prefixed_host = host if re.match(
            r"^https?://", host) else "https://" + host

        self._sid = self._login(user=user, password=password)
        self._fritzos = self._get_fritz_os_version()

        self._check_fritzos()

    def _login(self, user: str, password: str) -> str:
        url = "/".join([self._prefixed_host, f"login_sid.lua?version=2&user={user}"])
        response = requests.get(
            url, verify=self._ssl_verify, timeout=self._timeout)

        xml_root = ET.fromstring(response.content)
        sid = xml_root.findtext('SID')

        if sid == '0000000000000000':
            challenge_parts = xml_root.findtext('Challenge').split('$')
            iter1 = int(challenge_parts[1])
            salt1 = bytes.fromhex(challenge_parts[2])
            iter2 = int(challenge_parts[3])
            salt2 = bytes.fromhex(challenge_parts[4])

            hash1 = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), salt1, iter1)
            hash2 = hashlib.pbkdf2_hmac('sha256', hash1, salt2, iter2)

            payload = {
                'response': f"{salt2.hex()}${hash2.hex()}",
                'user': user
            }
            login_response = requests.post(
                url, data=payload, verify=self._ssl_verify, timeout=self._timeout)
            login_root = ET.fromstring(login_response.content)

            sid = login_root.findtext('SID')

            if sid == '0000000000000000':
                err = "Invalid user or password!"
                self._logger.error(err)
                raise FritzAdvancedThermostatConnectionError(err)
        return sid

    def _generate_headers(self, data):
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self._prefixed_host,
            "Content-Length": str(len(data)),
            "Accept-Language": "en-GB,en;q=0.9",
            "Host": self._prefixed_host.split("://")[1],
            "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.2 Safari/605.1.15",
            "Referer": self._prefixed_host,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        return headers

    def _fritz_post_req(self, payload: dict, site: str) -> dict:
        url = "/".join([self._prefixed_host, site])
        retries = 0
        while retries <= self._retries:
            try:
                response = requests.post(
                    url,
                    headers=self._generate_headers(payload),
                    data=payload,
                    verify=self._ssl_verify, timeout=self._timeout)
                break
            except ConnectionError as e:
                self._logger.warning("Connection Error on loading data")
                retries += 1
                if retries > self._retries:
                    err = "Tried 3 times, got Connection Error on loading raw thermostat data"
                    raise FritzAdvancedThermostatConnectionError(err) from e
                else:
                    self._logger.warning("Retry %s of %s", str(
                        retries), str(self._retries))
        if response.status_code != 200:
            err = "Error: " + str(response.status_code)
            self._logger.error(err)
            raise FritzAdvancedThermostatConnectionError(err)
        return response.text

    def _get_fritz_os_version(self) -> str:
        payload = {
            "sid": self._sid,
            "xhr": "1",
            "page": "overview",
            "xhrId": "first",
            "noMenuRef": "1"}
        response = self._fritz_post_req(
            payload, "data.lua")

        try:
            req_data = json.loads(response)
        except json.decoder.JSONDecodeError as e:
            err = "Error: Didn't get a valid json response when loading data\n" + response
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err) from e

        if "fritzos" not in req_data["data"]:
            err = "Error: Something went wrong loading the fritzos meta data\n" + response
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

        return req_data['data']['fritzos']['nspver']

    def _load_raw_device_data(self, force_reload=False):
        if not self._raw_device_data or force_reload:
            payload = {
                "sid": self._sid,
                "xhr": "1",
                "page": "sh_dev",
                "xhrId": "all",
                "useajax": "1"}

            response = self._fritz_post_req(
                payload, "data.lua")

            try:
                req_data = json.loads(response)
            except json.decoder.JSONDecodeError as e:
                err = "Error: Didn't get a valid json response when loading data\n" + response
                self._logger.error(err)
                raise FritzAdvancedThermostatExecutionError(err) from e

            if "devices" not in req_data["data"]:
                err = "Error: Something went wrong loading the raw thermostat data\n" + response
                self._logger.error(err)
                raise FritzAdvancedThermostatExecutionError(err)
            else:
                self._raw_device_data = req_data["data"]

    def _check_fritzos(self):
        if self._fritzos not in self._supported_firmware:
            if self._experimental:
                self._logger.warning("You're using an untested firmware!")
            else:
                err = "Error: Firmenware " + self._fritzos + "is unsupported"
                self._logger.error(err)
                raise FritzAdvancedThermostatCompatibilityError(err)

    def _check_device_name(self, device_name):
        self._generate_thermostat_data()
        if device_name not in self.get_thermostats():
            err = "Error: " + device_name + " not found!\n" + \
                "Available devices:" + ", ".join(self.get_thermostats())
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

    def _check_if_grouped(self, device_name):
        self._load_raw_device_data()
        grouped_thermostats = [i['displayName'] for i in [
            i['members'] for i in self._raw_device_data['groups']][0]]
        return device_name in grouped_thermostats

    def _set_thermostat_values(self, device_name, **kwargs):
        settable_keys = list(self._settable_keys["common"])
        if not self._check_if_grouped(device_name):
            settable_keys += list(self._settable_keys["ungrouped"])
        for key, value in kwargs.items():
            if key in settable_keys:
                if self._thermostat_data[device_name][key] != value:
                    self._changed_devices.add('device_name')
                    self._thermostat_data[device_name][key] = value
            else:
                err = "Error: " + key + " is not in:\n" + \
                    " ".join(settable_keys)
                self._logger.error(err)
                raise FritzAdvancedThermostatKeyError(err)

    def _generate_thermostat_data(self, force_reload=False):
        def __get_object(device: dict, unit_name: str, skill_type: str, skill_name: str = None):
            object = None
            for unit in device['units']:
                if unit['type'] == unit_name:
                    if skill_name:
                        for skill in unit['skills']:
                            if skill['type'] == skill_type:
                                object = skill[skill_name]
                    else:
                        object = unit
            return object

        def __get_schedule(schedules: list, schedule_name):
            schedule = [x for x in schedules if x['name'] == schedule_name]
            return schedule[0] if schedule else None

        def __get_temperature(presets, target):
            temp = "7.5" # Represents Off / AUS
            for preset in presets:
                if preset['name'] == target:
                    temp = str(preset['temperature'])
            return temp

        def __get_lock(locks, target):
            locked = False
            for lock in locks:
                if lock["devControlName"] == target:
                    if lock["isLocked"]:
                        locked = True
            return locked

        def __get_holiday_temp(device_id):
            # I found no other way then to parse the HTML with a regex, I don't know where I can find this.
            payload = {
                "sid": self._sid,
                "xhr": "1",
                "device": device_id,
                "page": "home_auto_hkr_edit"}
            response = self._fritz_post_req(payload, "data.lua")
            regex = r'(?<=<input type="hidden" name="Holidaytemp" value=")\d+\.?\d?(?=" id="uiNum:Holidaytemp">)'
            holiday_temp = re.findall(regex, response)[0]
            return holiday_temp

        if not self._thermostat_data or force_reload:
            self._load_raw_device_data(force_reload)
            for device in self._raw_device_data['devices']:
                name = device['displayName']
                grouped = name in [i['displayName'] for i in [i['members'] for i in self._raw_device_data['groups']][0]]
                if device["category"] == "THERMOSTAT":
                    self._thermostat_data[name] = {}
                    self._thermostat_data[name]["Offset"] = str(__get_object(device, 'TEMPERATURE_SENSOR',  'SmartHomeTemperatureSensor', 'offset'))
                    self._thermostat_data[name]["WindowOpenTimer"] = str(__get_object(device, 'THERMOSTAT',  'SmartHomeThermostat', 'temperatureDropDetection')['doNotHeatOffsetInMinutes'])
                    # WindowOpenTrigger musst always be + 3
                    # xhr - json    GUI
                    #  4     1   -> niedrig
                    #  8     5   -> mittel
                    #  12    9   -> hoch
                    self._thermostat_data[name]["WindowOpenTrigger"] = str(__get_object(device, 'THERMOSTAT',  'SmartHomeThermostat', 'temperatureDropDetection')['sensitivity'] + 3)

                    locks = __get_object(device, 'THERMOSTAT', 'SmartHomeThermostat')['interactionControls']
                    self._thermostat_data[name]["locklocal"] = __get_lock(locks, "BUTTON")
                    self._thermostat_data[name]["lockuiapp"] = __get_lock(locks, "EXTERNAL")
                    self._thermostat_data[name]["Grouped"] = grouped

                    if not grouped:
                        temperatures = __get_object(device, 'THERMOSTAT',  'SmartHomeThermostat', 'presets')
                        self._thermostat_data[name]["Absenktemp"] = __get_temperature(temperatures, "LOWER_TEMPERATURE")
                        self._thermostat_data[name]["Heiztemp"] = __get_temperature(temperatures, "UPPER_TEMPERATURE")

                        summer_time = __get_schedule(__get_object(device, 'THERMOSTAT',  'SmartHomeThermostat', 'timeControl')['timeSchedules'], 'SUMMER_TIME')
                        if summer_time['isEnabled']:
                            self._thermostat_data[name]["SummerEnabled"] = "1"
                            self._thermostat_data[name]["SummerEndDay"] = str(int(summer_time['actions'][0]['timeSetting']['endDate'].split('-')[2]))
                            self._thermostat_data[name]["SummerEndMonth"] = str(int(summer_time['actions'][0]['timeSetting']['endDate'].split('-')[1]))
                            self._thermostat_data[name]["SummerStartDay"] = str(int(summer_time['actions'][0]['timeSetting']['startDate'].split('-')[2]))
                            self._thermostat_data[name]["SummerStartMonth"] = str(int(summer_time['actions'][0]['timeSetting']['startDate'].split('-')[1]))
                        else:
                            self._thermostat_data[name]["SummerEnabled"] = "0"

                        holidays = __get_schedule(__get_object(device, 'THERMOSTAT',  'SmartHomeThermostat', 'timeControl')['timeSchedules'], 'HOLIDAYS')
                        if holidays['isEnabled']:
                            for i, holiday in enumerate(holidays['actions'], 1):
                                self._thermostat_data[name][f"Holiday{i}Enabled"] = "1" if holiday["isEnabled"] else "0"
                                self._thermostat_data[name][f"Holiday{i}EndDay"] = str(int(holiday['timeSetting']['endDate'].split('-')[2]))
                                self._thermostat_data[name][f"Holiday{i}EndHour"] = str(int(holiday['timeSetting']['startTime'].split(':')[1]))
                                self._thermostat_data[name][f"Holiday{i}EndMonth"] = str(int(holiday['timeSetting']['endDate'].split('-')[1]))
                                self._thermostat_data[name][f"Holiday{i}StartDay"] = str(int(holiday['timeSetting']['startDate'].split('-')[2]))
                                self._thermostat_data[name][f"Holiday{i}StartHour"] = str(int(holiday['timeSetting']['startTime'].split(':')[1]))
                                self._thermostat_data[name][f"Holiday{i}StartMonth"] = str(int(holiday['timeSetting']['startDate'].split('-')[1]))
                            self._thermostat_data[name]["Holidaytemp"] = __get_holiday_temp(device['id'])

    def _get_device_id_by_name(self, device_name):
        self._load_raw_device_data()
        return [device['id'] for device in self._raw_device_data['devices'] if device['displayName'] == device_name][0]

    def _generate_data_pkg(self, device_name, dry_run=True):
        self._generate_thermostat_data()
        data_dict = {
            "sid": self._sid,
            "device": self._get_device_id_by_name(device_name),
            "view": None,
            "back_to_page": "sh_dev",
            "ule_device_name": device_name,
            "graphState": "1",
            "tempsensor": "own",
            "ExtTempsensorID": "tochoose",
        }
        data_dict = data_dict | self._thermostat_data[device_name]

        holiday_enabled_count = 0
        holiday_id_count = 1
        for key, value in self._thermostat_data[device_name].items():
            if re.search(r"Holiday\dEnabled", key):
                if value:
                    holiday_enabled_count += int(value)
                    data_dict[
                        f"Holiday {str(holiday_id_count)} ID"] = holiday_id_count
                    holiday_id_count += 1
        if holiday_enabled_count:
            data_dict["HolidayEnabledCount"] = str(holiday_enabled_count)

        if dry_run:
            data_dict = data_dict | {
                "validate": "apply",
                "xhr": "1",
                "useajax": "1",
            }
        else:
            data_dict = data_dict | {
                "xhr": "1",
                "lang": "de",
                "apply": None,
                "oldpage": "/net/home_auto_hkr_edit.lua",
            }
        # Remove timer if grouped, also remove group marker in either case
        if data_dict["Grouped"]:
            for timer in re.findall(r"timer_item_\d",
                                    "|".join(data_dict.keys())):
                data_dict.pop(timer)
            data_dict.pop("graphState")
            data_dict.pop("Grouped")
        else:
            data_dict.pop("Grouped")

        data_pkg = []
        for key, value in data_dict.items():
            if value is None:
                data_pkg.append(key + "=")
            elif isinstance(value, bool):
                if value:
                    data_pkg.append(key + "=on")
            elif value:
                data_pkg.append(key + "=" + quote(str(value), safe=""))
        return "&".join(data_pkg)

    def commit(self):
        while self._changed_devices:
            thermostat = self._thermostat_data[self._changed_devices.pop()]
            # Dry run option is not available in 7.57 ???
            if version.parse("7.0") < version.parse(self._fritzos) <= version.parse("7.31"):
                site = "/".join(["net", "home_auto_hkr_edit.lua"])
                payload = self._generate_data_pkg(
                    thermostat, dry_run=True)
                response = self._fritz_post_req(payload, site)
                try:
                    dry_run_check = json.loads(dry_run_response)
                    if not dry_run_check["ok"]:
                        err = "Error in: " + \
                            ",".join(dry_run_check["tomark"])
                        err += "\n" + dry_run_check["alert"]
                        self._logger.error(err)
                        raise FritzAdvancedThermostatExecutionError(err)
                except json.decoder.JSONDecodeError as exc:
                    if dry_run_response:
                        err = "Error: Something went wrong on setting the thermostat values"
                        err += "\n" + dry_run_response.text
                    else:
                        err = "Error: Something went wrong on dry run"
                        err += "\n" + dry_run_response.text
                    self._logger.error(err)
                    raise FritzAdvancedThermostatExecutionError(
                        err) from exc

            payload = self._generate_data_pkg(thermostat, dry_run=False)
            response = self._fritz_post_req(payload, "data.lua")
            try:
                check = json.loads(response)
                if version.parse("7.0") < version.parse(self._fritzos) <= version.parse("7.31"):
                    if check["pid"] != "sh_dev":
                        err = "Error: Something went wrong setting the thermostat values"
                        err = "\n" + response.text
                        self._logger.error(err)
                        raise FritzAdvancedThermostatExecutionError(
                            err)
                if version.parse("7.50") < version.parse(self._fritzos) <= version.parse("7.57"):
                    if check["data"]["apply"] != "ok":
                        err = "Error: Something went wrong setting the thermostat values"
                        err = "\n" + response.text
                        self._logger.error(err)
                        raise FritzAdvancedThermostatExecutionError(
                            err)
            except json.decoder.JSONDecodeError as exc:
                err = "Error: Didn't get a valid json response when loading data\n" + response
                self._logger.error(err)
                raise FritzAdvancedThermostatExecutionError(err) from e

    def set_thermostat_offset(self, device_name, offset):
        self._check_device_name(device_name)
        if not (float(offset) * 2).is_integer():
            offset = round(offset * 2) / 2
            self._logger.warning(
                "Offset must be entered in 0.5 steps! Your offset was rounded to: %s", "{offset!s}")
        self._set_thermostat_values(device_name, Offset=str(offset))

    def get_thermostat_offset(self, device_name, force_reload=False):
        self._check_device_name(device_name)
        return float(self._thermostat_data[device_name]["Offset"])

    def get_thermostats(self):
        if not self._thermostats:
            self._load_raw_device_data()
            devices = {device['displayName']: {'model': device['model'],
                                            'type': device['category']} for device in self._raw_device_data['devices']}
            for dev_name, dev_data in devices:
                if self._experimental:
                    if dev_data['type'] == 'THERMOSTAT':
                        self._thermostats.add(dev_name)
                        if dev_data['model'] not in self._supported_thermostats:
                            self._logger.warning(
                                "%s - %s is an untested device!", dev_name, dev_data['model'])
                elif dev_data['model'] in self._supported_thermostats:
                    self._thermostats.add(dev_name)
        return self._thermostats
