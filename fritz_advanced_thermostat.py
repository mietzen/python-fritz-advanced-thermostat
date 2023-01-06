from time import sleep
import requests
import re
import json
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pyfritzhome import Fritzhome


class FritzAdvancedThermostatError(Exception):
    pass


class FritzAdvancedThermostatKeyError(KeyError):
    pass


class FritzAdvancedThermostatConnectionError(ConnectionError):
    pass


class FritzAdvancedThermostat(object):

    def __init__(self, host, user, password, ssl_verify=False):
        self._fritz_home = Fritzhome(host, user, password, ssl_verify)
        self._fritz_home.login()
        self._fritz_home.update_devices()
        self._sid = self._fritz_home._sid
        self._user = user
        self._password = password
        self._ssl_verify = ssl_verify
        self._devices = self._fritz_home._devices
        self._prefixed_host = self._fritz_home.get_prefixed_host()
        self._thermostat_data = {}
        self._settable_keys = [
            "Holiday1Enabled", "Holiday1EndDay", "Holiday1EndHour",
            "Holiday1EndMonth", "Holiday1StartDay", "Holiday1StartHour",
            "Holiday1StartMonth", "Holiday2Enabled", "Holiday2EndDay",
            "Holiday2EndHour", "Holiday2EndMonth", "Holiday2StartDay",
            "Holiday2StartHour", "Holiday2StartMonth", "Holiday3Enabled",
            "Holiday3EndDay", "Holiday3EndHour", "Holiday3EndMonth",
            "Holiday3StartDay", "Holiday3StartHour", "Holiday3StartMonth",
            "Holiday4Enabled", "Holiday4EndDay", "Holiday4EndHour",
            "Holiday4EndMonth", "Holiday4StartDay", "Holiday4StartHour",
            "Holiday4StartMonth", "Holidaytemp", "Offset", "SummerEnabled",
            "SummerEndDay", "SummerEndMonth", "SummerStartDay",
            "SummerStartMonth", "WindowOpenTimer", "WindowOpenTrigger",
            "locklocal", "lockuiapp"
        ]
        self._supported_thermostats = ['FRITZ!DECT 301']
        self._supported_firmware = ['7.29']
        self._thermostats = [
            x.name for x in self._devices.values()
            if x.productname in self._supported_thermostats
        ]
        self._selenium_options = Options()
        self._selenium_options.headless = True
        self._selenium_options.add_argument("--window-size=1920,1200")

    def _check_device_name(self, device_name):
        if device_name not in self._thermostats:
            err = 'Error:\n' + device_name + ' not found!\n' + \
                'Available devices:' + ', '.join(self._thermostats)
            raise FritzAdvancedThermostatError(err)

    def _get_device_id_by_name(self, device_name):
        for dev in self._devices.values():
            if dev.name == device_name:
                return dev.identifier

    def _load_raw_thermostat_data(self, device_name, reload_device=False):
        if device_name not in self._thermostat_data.keys() or reload_device:
            self._scrape_thermostat_data(device_name)

    def _scrape_thermostat_data(self, device_name):
        driver = webdriver.Chrome(options=self._selenium_options)
        driver.get(self._prefixed_host)
        driver.find_element(By.ID, "uiViewUser").send_keys(self._user)
        driver.find_element(By.ID, "uiPass").send_keys(self._password)
        WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.ID, "submitLoginBtn"))).click()
        WebDriverWait(driver,
                      60).until(EC.element_to_be_clickable(
                          (By.ID, "sh_menu"))).click()
        WebDriverWait(driver,
                      60).until(EC.element_to_be_clickable(
                          (By.ID, "sh_dev"))).click()
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "v-grid-container")))
        rows = driver.find_elements(By.CLASS_NAME, "v-grid-container")
        for row in rows:
            if device_name in row.text.split('\n'):
                row.find_element(By.TAG_NAME, "button").click()
                break
        # Wait until site is fully loaded
        WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.ID, "uiNumUp:Roomtemp")))
        sleep(
            0.5
        )  # Sometimes we need to await a little longer even if all elements are loaded
        driver.execute_script('var gOrigValues = {}; getOrigValues()')
        thermostat_data = driver.execute_script('return gOrigValues')
        room_temp = driver.execute_script(
            'return jxl.find("input[type=hidden][name=Roomtemp]")[0][\'value\']'
        )
        thermostat_data['Roomtemp'] = room_temp
        driver.quit()
        self._thermostat_data[device_name] = thermostat_data

    def _set_thermostat_values(self, device_name, **kwargs):
        self._load_raw_thermostat_data(device_name)
        for key, value in kwargs.items():
            if key in self._settable_keys:
                if key in self._thermostat_data[device_name].keys():
                    self._thermostat_data[device_name][key] = value
                else:
                    raise FritzAdvancedThermostatKeyError(
                        'Error:\n' + key + ' is not available for: ' +
                        device_name)
            else:
                raise FritzAdvancedThermostatKeyError(
                    'Error:\n' + key + ' is not in:\n' +
                    ' '.join(self._settable_keys))

    def _generate_headers(self, data):
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self._prefixed_host,
            "Content-Length": str(len(data)),
            "Accept-Language": "en-GB,en;q=0.9",
            "Host": self._prefixed_host.split('://')[1],
            "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.2 Safari/605.1.15",
            "Referer": self._prefixed_host,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        return headers

    def _generate_data_pkg(self, device_name, dry_run=True):
        self._load_raw_thermostat_data(device_name)
        data_dict = {
            "sid": self._sid,
            "device": self._get_device_id_by_name(device_name),
            "view": '',
            "back_to_page": "sh_dev",
            "ule_device_name": device_name,
            "graphState": "1",
            "tempsensor": "own",
            "ExtTempsensorID": "tochoose"
        }
        data_dict = data_dict | self._thermostat_data[device_name]

        holiday_enabled_count = 0
        holiday_id_count = 1
        for key, value in self._thermostat_data[device_name].items():
            if re.search(r"Holiday\dEnabled", key):
                holiday_enabled_count += int(value)
                data_dict['Holiday' + str(holiday_id_count) +
                          'ID'] = holiday_id_count
                holiday_id_count += 1
        data_dict['HolidayEnabledCount'] = holiday_enabled_count

        if dry_run:
            data_dict = data_dict | {
                'validate': 'apply',
                'xhr': '1',
                'useajax': '1'
            }
        else:
            data_dict = data_dict | {
                'xhr': '1',
                'lang': 'de',
                'apply': '',
                'oldpage': '/net/home_auto_hkr_edit.lua'
            }

        data_pkg = []
        for key, value in data_dict.items():
            if isinstance(value, bool):
                if value:
                    data_pkg.append(key + '=on')
                else:
                    data_pkg.append(key + '=off')
            else:
                data_pkg.append(key + '=' + quote(str(value), safe=''))
        return '&'.join(data_pkg)

    def commit(self, device_name):
        self._check_device_name(device_name)
        dry_run_url = '/'.join(
            [self._prefixed_host, 'net', 'home_auto_hkr_edit.lua'])
        set_url = '/'.join([self._prefixed_host, 'data.lua'])
        dry_run_data = self._generate_data_pkg(device_name, dry_run=True)
        set_data = self._generate_data_pkg(device_name, dry_run=False)
        dry_run_response = requests.post(
            dry_run_url,
            headers=self._generate_headers(dry_run_data),
            data=dry_run_data,
            verify=self._ssl_verify)
        if dry_run_response.status_code == 200:
            try:
                dry_run_check = json.loads(dry_run_response.text)
                if dry_run_check['ok']:
                    response = requests.post(
                        set_url,
                        headers=self._generate_headers(set_data),
                        data=set_data,
                        verify=self._ssl_verify)
                    if response.status_code == 200:
                        check = json.loads(response.text)
                        if check['pid'] != 'sh_dev':
                            err = 'Error: Something went wrong setting the thermostat values'
                            err = '\n' + response.text
                            raise FritzAdvancedThermostatError(err)
                    else:
                        raise FritzAdvancedThermostatConnectionError(
                            'Error: ' + str(response.status_code))
                else:
                    err = 'Error in: ' + ','.join(dry_run_check['tomark'])
                    err += '\n' + dry_run_check['alert']
                    raise FritzAdvancedThermostatError(err)
            except json.decoder.JSONDecodeError:
                if response:
                    err = 'Error: Something went wrong on setting the thermostat values'
                    err += '\n' + response.text
                else:
                    err = 'Error: Something went wrong on dry run'
                    err += '\n' + dry_run_response.text
                raise FritzAdvancedThermostatError(err)
        else:
            raise FritzAdvancedThermostatConnectionError(
                'Error: ' + str(dry_run_response.status_code))

    def set_thermostat_offset(self, device_name, offset):
        self._check_device_name(device_name)
        self._set_thermostat_values(device_name, Offset=str(offset))

    def get_thermostat_offset(self, device_name, reload_device=False):
        self._check_device_name(device_name)
        self._load_raw_thermostat_data(device_name,
                                       reload_device=reload_device)
        return self._thermostat_data[device_name]['Offset']

    def get_thermostats(self):
        return self._thermostats


#TODO: Implement

    def set_hollidays(self):
        pass

    def get_hollidays(self):
        pass

    def set_summer(self):
        pass

    def get_summer(self):
        pass

    def set_lock(self):
        pass

    def get_lock(self):
        pass
