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

#TODO: Write error class
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

    #TODO: Only set values if they are available, e.g. timer and holiday, look for push service
    def _generate_data_pkg(self, req_type, device_name, offset):
        current_thermostat_data = self._get_raw_thermostat_data(device_name)
        holiday_enabled_count = str(sum([
            int(y) for x, y in current_thermostat_data.items()
            if re.search(r"Holiday\dEnabled", x)
        ]))
        common_data = "sid={SID}&\
            device={DEV_ID}&\
            view=&\
            back_to_page=sh_dev&\
            ule_device_name={DEV_NAME}&\
            locklocal=off&\
            lockuiapp=off&\
            Heiztemp={HEATING_TEMP}&\
            Absenktemp={NIGHT_TEMP}&\
            graphState=1&\
            timer_item_0={TIMER0}&\
            timer_item_1={TIMER1}&\
            Holidaytemp={HOLIDAY_TEMP}&\
            Holiday1StartDay={HOLIDAY_1_START_DAY}&\
            Holiday1StartMonth={HOLIDAY_1_START_MONTH}&\
            Holiday1StartHour={HOLIDAY_1_START_HOUR}&\
            Holiday1EndDay={HOLIDAY_1_END_DAY}&\
            Holiday1EndMonth={HOLIDAY_1_END_MONTH}&\
            Holiday1EndHour={HOLIDAY_1_END_HOUR}&\
            Holiday1Enabled={HOLIDAY_1_ENABLED}&\
            Holiday1ID={HOLIDAY_1_ID}&\
            Holiday2StartDay={HOLIDAY_2_START_DAY}&\
            Holiday2StartMonth={HOLIDAY_2_START_MONTH}&\
            Holiday2StartHour={HOLIDAY_2_START_HOUR}&\
            Holiday2EndDay={HOLIDAY_2_END_DAY}&\
            Holiday2EndMonth={HOLIDAY_2_END_MONTH}&\
            Holiday2EndHour={HOLIDAY_2_END_HOUR}&\
            Holiday2Enabled={HOLIDAY_2_ENABLED}&\
            Holiday2ID={HOLIDAY_2_ID}&\
            Holiday3StartDay={HOLIDAY_3_START_DAY}&\
            Holiday3StartMonth={HOLIDAY_3_START_MONTH}&\
            Holiday3StartHour={HOLIDAY_3_START_HOUR}&\
            Holiday3EndDay={HOLIDAY_3_END_DAY}&\
            Holiday3EndMonth={HOLIDAY_3_END_MONTH}&\
            Holiday3EndHour={HOLIDAY_3_END_HOUR}&\
            Holiday3Enabled={HOLIDAY_3_ENABLED}&\
            Holiday3ID={HOLIDAY_3_ID}&\
            Holiday4StartDay={HOLIDAY_4_START_DAY}&\
            Holiday4StartMonth={HOLIDAY_4_START_MONTH}&\
            Holiday4StartHour={HOLIDAY_4_START_HOUR}&\
            Holiday4EndDay={HOLIDAY_4_END_DAY}&\
            Holiday4EndMonth={HOLIDAY_4_END_MONTH}&\
            Holiday4EndHour={HOLIDAY_4_END_HOUR}&\
            Holiday4Enabled={HOLIDAY_4_ENABLED}&\
            Holiday4ID={HOLIDAY_4_ID}&\
            HolidayEnabledCount={HOLIDAY_ENABLED_COUNT}&\
            SummerStartDay={SUMMER_START_DAY}&\
            SummerStartMonth={SUMMER_START_MONTH}&\
            SummerEndDay={SUMMER_END_DAY}&\
            SummerEndMonth={SUMMER_END_MONTH}&\
            SummerEnabled={SUMMER_ENABLED}&\
            WindowOpenTrigger={WINDOW_OPEN_TRIGGER}&\
            WindowOpenTimer={WINDOW_OPEN_TIMER}&\
            tempsensor=own&\
            Roomtemp={ROOM_TEMP}&\
            ExtTempsensorID=tochoose&\
            Offset={OFFSET}".format(
            SID=self._sid,
            DEV_ID=self._get_device_id_by_name(device_name),
            DEV_NAME=device_name,
            HEATING_TEMP=current_thermostat_data['Heiztemp'],
            NIGHT_TEMP=current_thermostat_data['Absenktemp'],
            TIMER0=quote(current_thermostat_data['timer_item_0']),
            TIMER1=quote(current_thermostat_data['timer_item_1']),
            HOLIDAY_TEMP=current_thermostat_data['Holidaytemp'],
            HOLIDAY_1_START_DAY=current_thermostat_data['Holiday1StartDay'],
            HOLIDAY_1_START_MONTH=current_thermostat_data['Holiday1StartMonth'],
            HOLIDAY_1_START_HOUR=current_thermostat_data['Holiday1StartHour'],
            HOLIDAY_1_END_DAY=current_thermostat_data['Holiday1EndDay'],
            HOLIDAY_1_END_MONTH=current_thermostat_data['Holiday1EndMonth'],
            HOLIDAY_1_END_HOUR=current_thermostat_data['Holiday1EndHour'],
            HOLIDAY_1_ENABLED=current_thermostat_data['Holiday1Enabled'],
            HOLIDAY_1_ID='1',
            HOLIDAY_2_START_DAY=current_thermostat_data['Holiday2StartDay'],
            HOLIDAY_2_START_MONTH=current_thermostat_data['Holiday2StartMonth'],
            HOLIDAY_2_START_HOUR=current_thermostat_data['Holiday2StartHour'],
            HOLIDAY_2_END_DAY=current_thermostat_data['Holiday2EndDay'],
            HOLIDAY_2_END_MONTH=current_thermostat_data['Holiday2EndMonth'],
            HOLIDAY_2_END_HOUR=current_thermostat_data['Holiday2EndHour'],
            HOLIDAY_2_ENABLED=current_thermostat_data['Holiday2Enabled'],
            HOLIDAY_2_ID='2',
            HOLIDAY_3_START_DAY=current_thermostat_data['Holiday3StartDay'],
            HOLIDAY_3_START_MONTH=current_thermostat_data['Holiday3StartMonth'],
            HOLIDAY_3_START_HOUR=current_thermostat_data['Holiday3StartHour'],
            HOLIDAY_3_END_DAY=current_thermostat_data['Holiday3EndDay'],
            HOLIDAY_3_END_MONTH=current_thermostat_data['Holiday3EndMonth'],
            HOLIDAY_3_END_HOUR=current_thermostat_data['Holiday3EndHour'],
            HOLIDAY_3_ENABLED=current_thermostat_data['Holiday3Enabled'],
            HOLIDAY_3_ID='3',
            HOLIDAY_4_START_DAY=current_thermostat_data['Holiday4StartDay'],
            HOLIDAY_4_START_MONTH=current_thermostat_data['Holiday4StartMonth'],
            HOLIDAY_4_START_HOUR=current_thermostat_data['Holiday4StartHour'],
            HOLIDAY_4_END_DAY=current_thermostat_data['Holiday4EndDay'],
            HOLIDAY_4_END_MONTH=current_thermostat_data['Holiday4EndMonth'],
            HOLIDAY_4_END_HOUR=current_thermostat_data['Holiday4EndHour'],
            HOLIDAY_4_ENABLED=current_thermostat_data['Holiday4Enabled'],
            HOLIDAY_4_ID='4',
            HOLIDAY_ENABLED_COUNT=holiday_enabled_count,
            SUMMER_START_DAY=current_thermostat_data['SummerStartDay'],
            SUMMER_START_MONTH=current_thermostat_data['SummerStartMonth'],
            SUMMER_END_DAY=current_thermostat_data['SummerEndDay'],
            SUMMER_END_MONTH=current_thermostat_data['SummerEndMonth'],
            SUMMER_ENABLED=current_thermostat_data['SummerEnabled'],
            WINDOW_OPEN_TRIGGER=current_thermostat_data['WindowOpenTrigger'],
            WINDOW_OPEN_TIMER=current_thermostat_data['WindowOpenTimer'],
            ROOM_TEMP=current_thermostat_data['Roomtemp'],
            OFFSET=offset)
        if req_type == 'verify':
            data = common_data + '&validate=apply&xhr=1&useajax=1'
        elif req_type == 'set':
            data = 'xhr=1&lang=de&' + common_data + '&apply=&oldpage=%2Fnet%2Fhome_auto_hkr_edit.lua'
        else:
            print('error')
        return data.replace(' ','')
