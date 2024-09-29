import logging
import requests
from errors import FritzAdvancedThermostatConnectionError

class FritzRequests():
    def __init__(self, prefixed_host: str, max_retries: int, timeout: int, ssl_verify: bool) -> None:
        self._prefixed_host = prefixed_host
        self._max_retries = max_retries
        self._timeout =timeout
        self._ssl_verify = ssl_verify
        self._logger = logging.getLogger("FritzAdvancedThermostatLogger")

    def _generate_headers(self, data: dict) -> dict:
        return {
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

    def post(self, payload: dict, site: str) -> dict:
        url = f"{self._prefixed_host}/{site}"
        retries = 0
        while retries <= self._max_retries:
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
                if retries > self._max_retries:
                    err = "Tried 3 times, got Connection Error on loading raw thermostat data"
                    raise FritzAdvancedThermostatConnectionError(err) from e
                self._logger.warning("Retry %s of %s", str(
                    retries), str(self._max_retries))
        if response.status_code != requests.codes.ok:
            err = "Error: " + str(response.status_code)
            self._logger.error(err)
            raise FritzAdvancedThermostatConnectionError(err)
        return response.text

class ThermostatDataGenerator():
    def __init__(self, sid: str, fritz_requests: FritzRequests) -> None:
        self._sid = sid
        self._fritz_requests = fritz_requests
        self._logger = logging.getLogger("FritzAdvancedThermostatLogger")

    def _get_object(self, device: dict, unit_name: str, skill_type: str, skill_name: str | None = None) -> any:
        thermostat_obj = None
        for unit in device["units"]:
            if unit["type"] == unit_name:
                if skill_name:
                    for skill in unit["skills"]:
                        if skill["type"] == skill_type:
                            thermostat_obj = skill[skill_name]
                else:
                    thermostat_obj = unit
        return thermostat_obj

    def _get_schedule(self, schedules: list, schedule_name: str) -> dict | None:
        schedule = [x for x in schedules if x["name"] == schedule_name]
        return schedule[0] if schedule else None

    def _get_temperature(self, presets: list, target: str) -> str:
        temp = "7.5" # Represents Off / AUS
        for preset in presets:
            if preset["name"] == target:
                temp = str(preset["temperature"])
        return temp

    def _get_lock(self, locks: list, target: str) -> bool:
        locked = False
        for lock in locks:
            if lock["devControlName"] == target and lock["isLocked"]:
                locked = True
        return locked

    def _get_holiday_temp(self, device_id: int) -> str:
        # I found no other way then to parse the HTML with a regex, I don't know where I can find this.
        payload = {
            "sid": self._sid,
            "xhr": "1",
            "device": device_id,
            "page": "home_auto_hkr_edit"}
        response = self.fritz_requests.post(payload, "data.lua")
        regex = r'(?<=<input type="hidden" name="Holidaytemp" value=")\d+\.?\d?(?=" id="uiNum:Holidaytemp">)'
        return re.findall(regex, response)[0]

    def _first_day_in_bitmask(self, bitmask: int) -> int:
        for i in range(7):
            if bitmask & (1 << i):
                return i
        return -1

    def _generate_weekly_timers(self, raw_timers: dict) -> dict:
        """
        Week Binary Conversion (reversed)
        Mo Tu We Th Fr Sa Su
        1  1  1  1  1  1  1  = 127
        1  0  0  0  0  1  0  = 33
        0  0  1  1  0  1  0  = 44

        timer_item_x=${TIME};${STATE};${DAYS}
        timer_item_0=  0530 ;    1   ; 127
        This means turn the device on at 5:30 on all days of the week
        """

        weekly_timers = {}
        # day - bitmask mapping
        day_to_bit = {
            'MON': 1 << 0,   # Monday -> 1
            'TUE': 1 << 1,   # Tuesday -> 2
            'WED': 1 << 2,   # Wednesday -> 4
            'THU': 1 << 3,   # Thursday -> 8
            'FRI': 1 << 4,   # Friday -> 16
            'SAT': 1 << 5,   # Saturday -> 32
            'SUN': 1 << 6    # Sunday -> 64
        }

        # action states mapping
        set_action = {
            'UPPER_TEMPERATURE': 1,
            'LOWER_TEMPERATURE': 0,
            'SET_OFF': 0
        }
        combined_times = {}
        for action in raw_timers['actions']:
            day = action['timeSetting']['dayOfWeek']
            start_time = action['timeSetting']['startTime']

            if 'presetTemperature' in action['description']:
                state = action['description']['presetTemperature']['name']
            elif action['description']['action'] == 'SET_OFF':
                state = 'SET_OFF'

            # Get bitmask and category for the action
            if day in day_to_bit:
                bitmask = day_to_bit[day]
                category = set_action[state]
                time_str = start_time.replace(':', '')[:4]  # Format time to HHMM
                key = (time_str, category)

                # Initialize bitmask if not present
                if key not in combined_times:
                    combined_times[key] = 0

                # Update the bitmask for the day
                combined_times[key] |= bitmask

        sorted_times = sorted(combined_times.items(), key=lambda x: (self._first_day_in_bitmask(x[1]), x[0][0]))

        for i, ((time_str, category), bitmask) in enumerate(sorted_times):
            weekly_timers[f"timer_item_{i}"] = "{time_str};{category};{bitmask}"

        return weekly_timers

    def _generate_holiday_schedule(self, raw_holidays: dict, device_id) -> dict:
        holiday_schedule = {}
        if raw_holidays["isEnabled"]:
            holiday_id_count = 0
            for i, holiday in enumerate(raw_holidays["actions"], 1):
                if holiday["isEnabled"]:
                    holiday_id_count += 1
                    holiday_schedule[f"Holiday{i}Enabled"] = "1"
                    holiday_schedule[f"Holiday{holiday_id_count!s}ID"] = holiday_id_count
                    holiday_schedule[f"Holiday{i}EndDay"] = str(int(holiday["timeSetting"]["endDate"].split("-")[2]))
                    holiday_schedule[f"Holiday{i}EndHour"] = str(int(holiday["timeSetting"]["startTime"].split(":")[1]))
                    holiday_schedule[f"Holiday{i}EndMonth"] = str(int(holiday["timeSetting"]["endDate"].split("-")[1]))
                    holiday_schedule[f"Holiday{i}StartDay"] = str(int(holiday["timeSetting"]["startDate"].split("-")[2]))
                    holiday_schedule[f"Holiday{i}StartHour"] = str(int(holiday["timeSetting"]["startTime"].split(":")[1]))
                    holiday_schedule[f"Holiday{i}StartMonth"] = str(int(holiday["timeSetting"]["startDate"].split("-")[1]))
            holiday_schedule["HolidayEnabledCount"] = str(holiday_id_count - 1)
            holiday_schedule["Holidaytemp"] = self._get_holiday_temp(device_id)

        return holiday_schedule

    def _generate_summer_time_schedule(self, raw_summer_time: dict) -> dict:
        summer_time_schedule = {}
        if raw_summer_time["isEnabled"]:
            summer_time_schedule["SummerEnabled"] = "1"
            summer_time_schedule["SummerEndDay"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["endDate"].split("-")[2]))
            summer_time_schedule["SummerEndMonth"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["endDate"].split("-")[1]))
            summer_time_schedule["SummerStartDay"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["startDate"].split("-")[2]))
            summer_time_schedule["SummerStartMonth"] = str(int(raw_summer_time["actions"][0]["timeSetting"]["startDate"].split("-")[1]))
        else:
            summer_time_schedule["SummerEnabled"] = "0"
        return summer_time_schedule

    def generate(self, raw_device_data) -> dict:
        thermostat_data = {}
        for device in raw_device_data["devices"]:
            name = device["displayName"]
            grouped = name in [i["displayName"] for i in [i["members"] for i in raw_device_data["groups"]][0]]
            if device["category"] == "THERMOSTAT":
                thermostat_data[name] = {}
                thermostat_data[name]["Offset"] = str(
                    self._get_object(device, "TEMPERATURE_SENSOR",  "SmartHomeTemperatureSensor", "offset"))
                thermostat_data[name]["WindowOpenTimer"] = str(
                    self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "temperatureDropDetection")["doNotHeatOffsetInMinutes"])
                # WindowOpenTrigger musst always be + 3
                #   xhr  -  json     GUI
                # 4  (01)    1   -> niedrig
                # 8  (10)    5   -> mittel
                # 12 (11)    9   -> hoch
                thermostat_data[name]["WindowOpenTrigger"] = str(
                    self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "temperatureDropDetection")["sensitivity"] + 3)

                locks = self._get_object(device, "THERMOSTAT", "SmartHomeThermostat")["interactionControls"]
                thermostat_data[name]["locklocal"] = self._get_lock(locks, "BUTTON")
                thermostat_data[name]["lockuiapp"] = self._get_lock(locks, "EXTERNAL")

                adaptiv_heating = self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "adaptivHeating")
                thermostat_data[name]["hkr_adaptheat"] = adaptiv_heating['isEnabled'] and adaptiv_heating['supported']

                if not grouped:
                    thermostat_data[name]['graphState'] = "1"
                    temperatures = self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "presets")
                    thermostat_data[name]["Absenktemp"] = self._get_temperature(temperatures, "LOWER_TEMPERATURE")
                    thermostat_data[name]["Heiztemp"] = self._get_temperature(temperatures, "UPPER_TEMPERATURE")

                    summer_time = self._get_schedule(self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "timeControl")["timeSchedules"], "SUMMER_TIME")
                    thermostat_data[name] |= self._generate_summer_time_schedule(summer_time)

                    holidays = self._get_schedule(self._get_object(device, "THERMOSTAT",  "SmartHomeThermostat", "timeControl")["timeSchedules"], "HOLIDAYS")
                    thermostat_data[name] |= self._generate_holiday_schedule(holidays, device["id"])

                    raw_weekly_timetable = self._get_schedule(self._get_object(device, "THERMOSTAT", "SmartHomeThermostat", "timeControl")["timeSchedules"], "TEMPERATURE")
                    thermostat_data[name] |= self._generate_weekly_timers(raw_weekly_timetable)

        return thermostat_data
