import json
import re
import requests
from .errors import *
from fritzconnection import FritzConnection
from pyfritzhome import Fritzhome
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from urllib.parse import quote
import logging
import sys


class FritzAdvancedThermostat(object):

    def __init__(self,
                 host,
                 user,
                 password,
                 ssl_verify=False,
                 experimental=False,
                 log_level='warning'):
        # Setup logger
        self._logger = logging.getLogger()
        self._logger.setLevel(log_level.upper())
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self._logger.level)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

        if sys.version_info[0] == 3 and sys.version_info[1] >= 9:
            self._logger.info('Python version: ' +
                              '.'.join([str(x)
                                        for x in sys.version_info[0:3]]))
        else:
            err = 'Error: Update Python!\nPython version: ' + '.'.join([str(x) for x in sys.version_info[0:3]]) + '\n'\
                'Min. required Python version: 3.9.0'
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

        if experimental:
            self._logger.warning('Experimental mode! All checks disabled!')
        # Get SID and devices from Fritzhome
        fh = Fritzhome(host, user, password, ssl_verify)
        fh.login()
        fh.update_devices()
        self._sid = fh._sid
        self._devices = fh._devices
        self._prefixed_host = fh.get_prefixed_host()
        # Check Fritz!OS via FritzConnection
        fc = FritzConnection(address=host, user=user, password=password)
        self._fritzos = fc.system_version
        self._supported_firmware = ['7.29']
        self._check_fritzos()
        # Set basic properties
        self._experimental = experimental
        self._user = user
        self._password = password
        self._ssl_verify = ssl_verify
        # Set data structures
        self._thermostat_data = {}
        self._valid_device_types = ['Heizkörperregler']
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
        self._thermostats = []
        # Setup selenium options
        self._selenium_options = Options()
        self._selenium_options.add_argument('--headless')
        self._selenium_options.add_argument('--no-sandbox')
        self._selenium_options.add_argument('--disable-gpu')
        self._selenium_options.add_argument('--disable-dev-shm-usage')
        self._selenium_options.add_argument("--window-size=1920,1200")
        if not self._ssl_verify:
            self._selenium_options.add_argument('ignore-certificate-errors')

    def _check_fritzos(self):
        if not self._fritzos in self._supported_firmware:
            if self._experimental:
                self._logger.warning('You\'re using an untested firmware!')
            else:
                err = 'Error: Firmenware ' + self._fritzos + 'is unsupported'
                self._logger.error(err)
                raise FritzAdvancedThermostatCompatibilityError(err)

    def _check_device_name(self, device_name):
        if device_name not in self.get_thermostats():
            err = 'Error: ' + device_name + ' not found!\n' + \
                'Available devices:' + ', '.join(self.get_thermostats())
            self._logger.error(err)
            raise FritzAdvancedThermostatExecutionError(err)

    def _get_device_id_by_name(self, device_name):
        for dev in self._devices.values():
            if dev.name == device_name:
                return dev.identifier

    def _load_raw_thermostat_data(self, device_name, force_reload=False):
        if device_name not in self._thermostat_data.keys() or force_reload:
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
        grouped = False
        for row in rows:
            row_text = row.text.split('\n')
            if device_name in row_text:
                valid_device_type = any(
                    [True for x in row_text if x in self._valid_device_types])
                if valid_device_type or self._experimental:
                    if len(row_text) == 5:
                        grouped = True
                    row.find_element(By.TAG_NAME, "button").click()
                    break
                else:
                    err = 'Error: Can\'t find ' + ' or '.join(self._valid_device_types) + \
                        ' in : ' + ' '.join(row_text)
                    self._logger.error(err)
                    FritzAdvancedThermostatKeyError(err)
        # Wait until site is fully loaded
        WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.ID, "uiNumUp:Roomtemp")))
        # Sometimes we need to await a little longer even if all elements are loaded
        sleep(0.5)
        driver.execute_script('var gOrigValues = {}; getOrigValues()')
        thermostat_data = driver.execute_script('return gOrigValues')
        # Find hidden Roomtemp value
        room_temp = driver.execute_script(
            'return jxl.find("input[type=hidden][name=Roomtemp]")[0][\'value\']'
        )
        # Set group marker:
        thermostat_data['Grouped'] = grouped
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
                    err = 'Error: ' + key + ' is not available for: ' + device_name
                    self._logger.error(err)
                    raise FritzAdvancedThermostatKeyError(err)
            else:
                err = 'Error: ' + key + ' is not in:\n' + ' '.join(
                    self._settable_keys)
                self._logger.error(err)
                raise FritzAdvancedThermostatKeyError(err)

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
            "view": None,
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
                if value:
                    holiday_enabled_count += int(value)
                    data_dict['Holiday' + str(holiday_id_count) +
                              'ID'] = holiday_id_count
                    holiday_id_count += 1
        if holiday_enabled_count:
            data_dict['HolidayEnabledCount'] = str(holiday_enabled_count)

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
                'apply': None,
                'oldpage': '/net/home_auto_hkr_edit.lua'
            }
        # Remove timer if grouped, also remove group marker in either case
        if data_dict['Grouped']:
            for timer in re.findall(r'timer_item_\d',
                                    '|'.join(data_dict.keys())):
                data_dict.pop(timer)
            data_dict.pop('graphState')
            data_dict.pop('Grouped')
        else:
            data_dict.pop('Grouped')

        data_pkg = []
        for key, value in data_dict.items():
            if value is None:
                data_pkg.append(key + '=')
            elif isinstance(value, bool):
                if value:
                    data_pkg.append(key + '=on')
                else:
                    data_pkg.append(key + '=off')
            elif value:
                data_pkg.append(key + '=' + quote(str(value), safe=''))
        return '&'.join(data_pkg)

    def commit(self):
        for dev in self._thermostat_data.keys():
            self._check_device_name(dev)
            dry_run_url = '/'.join(
                [self._prefixed_host, 'net', 'home_auto_hkr_edit.lua'])
            set_url = '/'.join([self._prefixed_host, 'data.lua'])
            dry_run_data = self._generate_data_pkg(dev, dry_run=True)
            set_data = self._generate_data_pkg(dev, dry_run=False)
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
                                self._logger.error(err)
                                raise FritzAdvancedThermostatExecutionError(err)
                        else:
                            err = 'Error: ' + str(response.status_code)
                            self._logger.error(err)
                            raise FritzAdvancedThermostatConnectionError(err)
                    else:
                        err = 'Error in: ' + ','.join(dry_run_check['tomark'])
                        err += '\n' + dry_run_check['alert']
                        self._logger.error(err)
                        raise FritzAdvancedThermostatExecutionError(err)
                except json.decoder.JSONDecodeError:
                    if response:
                        err = 'Error: Something went wrong on setting the thermostat values'
                        err += '\n' + response.text
                    else:
                        err = 'Error: Something went wrong on dry run'
                        err += '\n' + dry_run_response.text
                    self._logger.error(err)
                    raise FritzAdvancedThermostatExecutionError(err)
            else:
                err = 'Error: ' + str(dry_run_response.status_code)
                self._logger.error(err)
                raise FritzAdvancedThermostatConnectionError()

    def set_thermostat_offset(self, device_name, offset):
        self._check_device_name(device_name)
        if not (offset * 2).is_integer():
            offset = round(offset * 2) / 2
            self._logger.warning(
                'Offset must be entered in 0.5 steps! Your offset was rounded to: '
                + str(offset))
        self._set_thermostat_values(device_name, Offset=str(offset))

    def get_thermostat_offset(self, device_name, force_reload=False):
        self._check_device_name(device_name)
        self._load_raw_thermostat_data(device_name, force_reload=force_reload)
        return float(self._thermostat_data[device_name]['Offset'])

    def get_thermostats(self):
        if not self._thermostats:
            for dev in self._devices.values():
                if self._experimental:
                    if dev.has_thermostat:
                        self._thermostats.append(dev.name)
                        if dev.productname not in self._supported_thermostats:
                            self._logger.warning(dev.name + ' - ' +
                                                 dev.productname +
                                                 ' is an untested devices!')
                else:
                    if dev.productname in self._supported_thermostats:
                        self._thermostats.append(dev.name)
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


#TODO: Look at timers
