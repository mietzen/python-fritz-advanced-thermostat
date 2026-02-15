"""Fritz!DECT Advanced Thermostat Control Module.

This module provides a class for managing and controlling Fritz!DECT thermostats connected to a Fritz!Box router.
It allows for advanced operations such as setting temperature offsets, retrieving thermostat data, and committing
changes to the Fritz!Box.

The main class, FritzAdvancedThermostat, handles authentication, data retrieval, and modification of thermostat
settings. It supports various Fritz!OS versions and includes both stable and experimental features.

Classes:
    FritzAdvancedThermostat: Main class for interacting with Fritz!DECT thermostats.

Usage:
    from fritz_advanced_thermostat import FritzAdvancedThermostat

    thermostat = FritzAdvancedThermostat(host="192.168.178.1", user="username", password="password")
    thermostat.set_thermostat_offset("Living Room", 0.5)
    thermostat.commit()

Note:
    This module requires Python 3.12.0 or later.

Raises:
    FritzAdvancedThermostatExecutionError: For general execution errors.
    FritzAdvancedThermostatConnectionError: For connection-related errors.
    FritzAdvancedThermostatCompatibilityError: For unsupported Fritz!OS versions.
    FritzAdvancedThermostatKeyError: For invalid thermostat setting keys.

Dependencies:
    - requests
    - packaging

"""

from __future__ import annotations

import json
import logging
import re
import sys

from packaging import version

from .errors import (
    FritzAdvancedThermostatCompatibilityError,
    FritzAdvancedThermostatExecutionError,
    FritzAdvancedThermostatKeyError,
)
from .errors import (
    FritzAdvancedThermostatConnectionError as FritzAdvancedThermostatConnectionError,
)
from .errors import (
    FritzAdvancedThermostatError as FritzAdvancedThermostatError,
)
from .utils import FritzConnection, ThermostatDataGenerator

PYTHON_VERSION = ".".join([str(x) for x in sys.version_info[0:3]])


class FritzAdvancedThermostat:
    """A class to manage and control Fritz!DECT thermostats connected to a Fritz!Box.

    Args:
        host (str): The IP address or URL of the Fritz!Box.
        user (str): The username for Fritz!Box authentication.
        password (str): The password for Fritz!Box authentication.
        ssl_verify (bool, optional): Whether to verify SSL certificates during HTTP requests. Defaults to False.
        experimental (bool, optional): Enables experimental mode with disabled checks for unsupported features. Defaults to False.
        log_level (str, optional): The logging level for internal logging. Defaults to "warning".
        timeout (int, optional): The timeout for HTTP requests in seconds. Defaults to 60.
        retries (int, optional): Number of retry attempts for failed HTTP requests. Defaults to 3.

    Attributes:
        _logger (Logger): Internal logger for the class.
        _supported_firmware (list): List of supported Fritz!OS firmware versions.
        _experimental (bool): Whether experimental mode is enabled.
        _ssl_verify (bool): Whether SSL verification is enabled.
        _timeout (int): Timeout for HTTP requests.
        _retries (int): Number of retry attempts for failed HTTP requests.
        _thermostat_data (dict): Stores thermostat-related data.
        _raw_device_data (dict): Stores raw device data fetched from Fritz!Box.
        _changed_devices (set): Set of thermostats whose data has been changed.
        _thermostats (set): Set of available thermostats.
        _settable_keys (dict): Dictionary of keys that can be set on the thermostat.
        _supported_thermostats (list): List of supported thermostat devices.
        _prefixed_host (str): The full URL of the Fritz!Box, including the protocol.
        _sid (str): Session ID for Fritz!Box authentication.
        _fritzos (str): Current Fritz!OS version of the Fritz!Box.

    Raises:
        FritzAdvancedThermostatExecutionError: If the current Python version is less than 3.9.0.
        FritzAdvancedThermostatConnectionError: If login or HTTP requests fail.
        FritzAdvancedThermostatCompatibilityError: If the Fritz!OS version is unsupported.
        FritzAdvancedThermostatKeyError: If trying to set a thermostat value with an unsupported key.

    """

    def __init__(
            self,
            host: str,
            user: str,
            password: str,
            timeout: int = 60,
            retries: int = 3,
            ssl_verify: bool = False,
            experimental: bool = False) -> None:
        """Initialize the FritzAdvancedThermostat class.

        This method sets up the connection to the Fritz!Box and initializes
        necessary attributes for managing Fritz!DECT thermostats.

        Args:
            host (str): The IP address or URL of the Fritz!Box.
            user (str): The username for Fritz!Box authentication.
            password (str): The password for Fritz!Box authentication.
            log_level (str, optional): The logging level for internal logging. Defaults to "warning".
            timeout (int, optional): The timeout for HTTP requests in seconds. Defaults to 60.
            retries (int, optional): Number of retry attempts for failed HTTP requests. Defaults to 3.
            ssl_verify (bool): Whether to verify SSL certificates during HTTP requests.
            experimental (bool): Enables experimental mode with disabled checks for unsupported features.

        Raises:
            FritzAdvancedThermostatExecutionError: If the Python version is less than 3.9.0.
            FritzAdvancedThermostatConnectionError: If login or HTTP requests fail.
            FritzAdvancedThermostatCompatibilityError: If the Fritz!OS version is unsupported.
            FritzAdvancedThermostatKeyError: If trying to set a thermostat value with an unsupported key.

        """
        self._logger = logging.getLogger("FritzAdvancedThermostatLogger")

        if experimental:
            self._logger.warning("Experimental mode! All checks disabled!")

        if version.parse(PYTHON_VERSION) < version.parse("3.12.0"):
            err = "Error: Update Python!\nPython version: " + PYTHON_VERSION + \
            "\nMin. required Python version: 3.12.0"
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

        self._supported_firmware = ["7.60"]
        # Set basic properties
        self._experimental = experimental
        self._ssl_verify = ssl_verify
        self._timeout = timeout
        # Set data structures
        self._thermostat_data = {}
        self._raw_device_data = {}
        self._changed_devices = set()
        self._thermostats = set()
        self._settable_keys = {
            "common": (
                "Offset",
                "hkr_adaptheat",
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

        self._supported_thermostats = ["FRITZ!Smart Thermo 301"]
        self._prefixed_host = host if re.match(
            r"^https?://", host) else "https://" + host

        # Setup utils objects
        self._fritz_conn = FritzConnection(self._prefixed_host, retries, timeout, ssl_verify)
        self._fritz_conn.login(user=user, password=password)
        self._thermostat_data_generator = ThermostatDataGenerator(self._fritz_conn)

        # Check FritzOS version
        self._fritzos = self._fritz_conn.get_fritz_os_version()
        if self._fritzos not in self._supported_firmware:
            if self._experimental:
                self._logger.warning("You're using an untested firmware!")
            else:
                err = "Error: Firmenware " + self._fritzos + "is unsupported"
                self._logger.error(err)
                raise FritzAdvancedThermostatCompatibilityError(err)

    def _load_raw_device_data(self, force_reload: bool = False) -> None:
        if not self._raw_device_data or force_reload:
            payload = {
                "xhr": "1",
                "page": "sh_dev",
                "xhrId": "all",
                "useajax": "1"}

            response = self._fritz_conn.post_req(
                payload, "data.lua")

            try:
                req_data = json.loads(response)
            except json.decoder.JSONDecodeError as e:
                err = "Error: Didn't get a valid json response when loading data\n" + response
                self._logger.exception(err)
                raise FritzAdvancedThermostatExecutionError(err) from e

            if "devices" not in req_data["data"]:
                err = "Error: Something went wrong loading the raw thermostat data\n" + response
                self._logger.error(err)
                raise FritzAdvancedThermostatExecutionError(err)
            self._raw_device_data = req_data["data"]

    def _generate_thermostat_data(self, force_reload: bool = False) -> None:
        self._load_raw_device_data(force_reload)
        if not self._thermostat_data or force_reload:
            self._thermostat_data = self._thermostat_data_generator.generate(self._raw_device_data)

    def _check_device_name(self, device_name: str) -> None:
        self._generate_thermostat_data()
        if device_name not in self.get_thermostats():
            err = "Error: " + device_name + " not found!\n" + \
                "Available devices:" + ", ".join(self.get_thermostats())
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

    def _check_if_grouped(self, device_name: str) -> bool:
        self._load_raw_device_data()
        grouped_thermostats = [i["displayName"] for i in [
            i["members"] for i in self._raw_device_data["groups"]][0]]
        return device_name in grouped_thermostats

    def _set_thermostat_values(self, device_name: str, **kwargs: any) -> None:
        settable_keys = list(self._settable_keys["common"])
        if not self._check_if_grouped(device_name):
            settable_keys += list(self._settable_keys["ungrouped"])
        for key, value in kwargs.items():
            if key in settable_keys:
                if self._thermostat_data[device_name][key] != value:
                    self._changed_devices.add(device_name)
                    self._thermostat_data[device_name][key] = value
            else:
                err = "Error: " + key + " is not in:\n" + \
                    " ".join(settable_keys)
                self._logger.error(err)
                raise FritzAdvancedThermostatKeyError(err)

    def _get_device_id_by_name(self, device_name: str) -> int:
        self._load_raw_device_data()
        return [device["id"] for device in self._raw_device_data["devices"] if device["displayName"] == device_name][0]

    def _generate_data_pkg(self, device_name: str) -> dict:
        self._generate_thermostat_data()
        data_dict = {
            "device": self._get_device_id_by_name(device_name),
            "view": None,
            "back_to_page": "/smarthome/devices.lua",
            "ule_device_name": device_name,
            "tempsensor": "own",
            "ExtTempsensorID": "tochoose",
        }

        data_dict |= self._thermostat_data[device_name]

        data_dict |= {
            "xhr": "1",
            "lang": "de",
            "apply": None,
            "page": "home_auto_hkr_edit",
        }

        return data_dict

    def commit(self) -> None:
        """Commit the changes to the thermostats by sending the updated data to the FRITZ!Box.

        FRITZ!OS version behavior:
        - For versions between 7.0 and 7.31 (inclusive), a dry run is performed to validate thermostat settings.
        - For versions between 7.50 and 7.57 (inclusive), the thermostat settings are committed directly, and the
        response is checked to confirm success.

        Raises:
            FritzAdvancedThermostatExecutionError: If the thermostat settings update fails at any stage, including
            invalid responses, failure during the dry run, or issues applying the settings.

        """
        while self._changed_devices:
            thermostat_name = self._changed_devices.pop()

            payload = self._generate_data_pkg(thermostat_name)
            response = self._fritz_conn.post_req(payload, "data.lua")
            try:
                check = json.loads(response)
                if check["data"]["apply"] != "ok":
                    err = "Error: Something went wrong setting the thermostat values"
                    err = "\n" + response
                    self._logger.error(err)
                    raise FritzAdvancedThermostatExecutionError(
                        err)
            except json.decoder.JSONDecodeError as e:
                err = "Error: Didn't get a valid json response when loading data\n" + response
                self._logger.exception(err)
                raise FritzAdvancedThermostatExecutionError(err) from e

    def set_thermostat_offset(self, device_name: str, offset: str | float) -> None:
        """Set the temperature offset for a specified thermostat device.

        This method allows setting a temperature offset for the given thermostat device.
        The offset must be provided in increments of 0.5 degrees. If not, it will be rounded
        to the nearest 0.5 increment, and a warning will be logged.

        Args:
            device_name (str): The name of the thermostat device.
            offset (str | float): The desired temperature offset, either as a string or float.
                                  It must be in 0.5°C increments. If not, it will be rounded.

        Raises:
            FritzAdvancedThermostatExecutionError: If the provided device name is invalid.

        """
        self._check_device_name(device_name)
        if not (float(offset) * 2).is_integer():
            offset = round(float(offset) * 2) / 2
            self._logger.warning(
                "Offset must be entered in 0.5 steps! Your offset was rounded to: %s", "{offset!s}")
        self._set_thermostat_values(device_name, Offset=str(offset))

    def get_thermostat_offset(self, device_name: str, force_reload: bool = False) -> float:
        """Retrieve the thermostat temperature offset for a given device.

        This method returns the temperature offset for the specified thermostat device. It ensures that
        the thermostat data is up to date, optionally forcing a reload of the data if needed. If the
        device name is not found or invalid, an exception will be raised.

        Args:
            device_name (str): The name of the thermostat device to retrieve the offset for.
            force_reload (bool, optional): If True, forces a reload of thermostat data before retrieving
                                        the offset. Defaults to False.

        Returns:
            float: The temperature offset of the specified thermostat device.

        Raises:
            KeyError: If the specified device name is not found in the thermostat data.

        """
        self._generate_thermostat_data(force_reload)
        self._check_device_name(device_name)
        return float(self._thermostat_data[device_name]["Offset"])

    def get_thermostat_temperature(self, device_name: str, force_reload: bool = False) -> float:
        """Retrieve the current room temperature for a given thermostat device.

        Args:
            device_name (str): The name of the thermostat device to retrieve the temperature for.
            force_reload (bool, optional): If True, forces a reload of thermostat data before retrieving
                                        the temperature. Defaults to False.

        Returns:
            float: The current room temperature of the specified thermostat device.

        Raises:
            KeyError: If the specified device name is not found in the thermostat data.

        """
        self._generate_thermostat_data(force_reload)
        self._check_device_name(device_name)
        return float(self._thermostat_data[device_name]["Roomtemp"])

    def get_thermostats(self) -> set:
        """Retrieve a set of thermostat device names.

        This method returns a set of thermostat names, loading raw device data if it hasn't been loaded yet.
        Depending on whether the `experimental` flag is set, it either includes all thermostat devices or only
        those that are in the supported thermostat models.

        Returns:
            set: A set containing the names of the thermostat devices.

        """
        if not self._thermostats:
            self._load_raw_device_data()
            devices = {device["displayName"]: {"model": device["model"],
                                            "type": device["category"]} for device in self._raw_device_data["devices"]}
            for dev_name, dev_data in devices.items():
                if self._experimental:
                    if dev_data["type"] == "THERMOSTAT":
                        self._thermostats.add(dev_name)
                        if dev_data["model"] not in self._supported_thermostats:
                            self._logger.warning(
                                "%s - %s is an untested device!", dev_name, dev_data["model"])
                elif dev_data["model"] in self._supported_thermostats:
                    self._thermostats.add(dev_name)
        return self._thermostats

    def reload_thermostat_data(self) -> None:
        """Force a reload of all thermostat data from the Fritz!Box."""
        self._generate_thermostat_data(True)
