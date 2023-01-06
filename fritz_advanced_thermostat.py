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

class FritzAdvancedThermostat(Fritzhome):
    def __init__(self,
                 host,
                 user,
                 password,
                 ssl_verify=False):
        super().__init__(host, user, password, ssl_verify)
        self._selenium_options = Options()
        self._selenium_options.headless = True
        self._selenium_options.add_argument("--window-size=1920,1200")
        self.login()

    def _get_raw_thermostat_data(self, device_name):
        driver = webdriver.Chrome(options=self._selenium_options)
        driver.get(self.get_prefixed_host())
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
        WebDriverWait(driver,
                      60).until(EC.element_to_be_clickable((By.ID, "uiNumUp:Roomtemp")))
        driver.execute_script('var gOrigValues = {}; getOrigValues()')
        thermostat_data = driver.execute_script('return gOrigValues')
        room_temp = driver.execute_script(
            'return jxl.find("input[type=hidden][name=Roomtemp]")[0][\'value\']'
        )
        thermostat_data['Roomtemp'] = room_temp
        driver.quit()
        return thermostat_data

    def _get_device_id_by_name(self, device_name):
        if self._devices is None:
            self.update_devices()
        for dev in self._devices.values():
            if dev.name == device_name:
                return dev.identifier

    def set_thermostat_offset(self, device_name, offset):
        verify_url = '/'.join(
            [self.get_prefixed_host(), 'net', 'home_auto_hkr_edit.lua'])
        set_url = '/'.join([self.get_prefixed_host(), 'data.lua'])
        verify_data = self._generate_data_pkg('verify', device_name, offset)
        set_data = self._generate_data_pkg('set', device_name, offset)
        verification = requests.post(
            verify_url,
            headers=self._generate_headers(verify_data),
            data=verify_data,
            verify=self._ssl_verify)
        if verification.status_code == 200:
            check = json.loads(verification.text)
            if check['ok']:
                status = requests.post(set_url,
                            headers=self._generate_headers(set_data),
                            data=set_data,
                            verify=self._ssl_verify)
                if status.status_code != 200:
                    print('Error: ' + str(status.status_code))
            else:
                for i in check['tomark']:
                    print('Error in: ' + i)
                print(check['alert'])
        else:
            print('Error: ' + str(verification.status_code))

    def _generate_headers(self, data):
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.get_prefixed_host(),
            "Content-Length": str(len(data)),
            "Accept-Language": "en-GB,en;q=0.9",
            "Host": self.get_prefixed_host().split('://')[1],
            "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.2 Safari/605.1.15",
            "Referer": self.get_prefixed_host(),
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
        return headers

    def _generate_data_pkg(self, req_type, device_name, offset):
        current_thermostat_data = self._get_raw_thermostat_data(device_name)
        common_data = "sid=" + self._sid + "&" + \
            "device=" + self._get_device_id_by_name(device_name) + "&" + \
            "view=&" + \
            "back_to_page=sh_dev&" + \
            "ule_device_name=" + device_name + "&" + \
            "locklocal=off&" + \
            "lockuiapp=off&" + \
            "Heiztemp=" + current_thermostat_data['Heiztemp'] + "&" + \
            "Absenktemp=" + current_thermostat_data['Absenktemp'] + "&" + \
            "graphState=1&"
        for key in current_thermostat_data.keys():
            if re.match(r"timer_item_\d+", key):
                common_data += key + "=" + quote(current_thermostat_data[key]) + "&"

        holiday_enabled_count = 0
        for key in current_thermostat_data.keys():
            if re.match(r"Holiday\d\w+", key):
                common_data += key + "=" + current_thermostat_data[key] + "&"
            if re.match(r"Holiday\dEnabled", key):
                holiday_enabled_count += 1
        common_data += "HolidayEnabledCount=" + str(holiday_enabled_count) + "&"
        
        for key in current_thermostat_data.keys():
            if re.match(r"Summer\w+", key):
                common_data += key + "=" + quote(current_thermostat_data[key]) + "&"

        common_data += "WindowOpenTrigger=" + current_thermostat_data['WindowOpenTrigger'] + "&" + \
            "WindowOpenTimer=" + current_thermostat_data['WindowOpenTimer'] + "&" + \
            "tempsensor=own&" + \
            "Roomtemp=" + current_thermostat_data['Roomtemp'] + "&" + \
            "ExtTempsensorID=tochoose&" + \
            "Offset=" + offset + "&"

        if req_type == 'verify':
            data = common_data + 'validate=apply&xhr=1&useajax=1'
        elif req_type == 'set':
            data = 'xhr=1&lang=de&' + common_data + 'apply=&oldpage=%2Fnet%2Fhome_auto_hkr_edit.lua'
        else:
            print('error')
        return data.replace(' ','')
