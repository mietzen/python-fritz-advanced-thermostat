
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pyfritzhome import Fritzhome

class FritzAdvancedThermostat(Fritzhome):
    def __init__(self, host, user, password, chromedriver_path, ssl_verify=False):
        super().__init__(host, user, password, ssl_verify)
        selenium_options = Options()
        selenium_options.headless = True
        selenium_options.add_argument("--window-size=1920,1200")
        self.login()
        self._driver = webdriver.Chrome(options=selenium_options, executable_path=chromedriver_path)

    def __del__(self):
        self._driver.quit()
        
    def _get_raw_thermostat_data(self, device_name):
        self._driver.get(self.get_prefixed_host())
        self._driver.find_element(By.ID, "uiViewUser").send_keys(self._user)
        self._driver.find_element(By.ID, "uiPass").send_keys(self._password)
        WebDriverWait(self._driver, 60).until(EC.element_to_be_clickable((By.ID, "submitLoginBtn"))).click()
        WebDriverWait(self._driver, 60).until(EC.element_to_be_clickable((By.ID, "sh_menu"))).click()
        WebDriverWait(self._driver, 60).until(EC.element_to_be_clickable((By.ID, "sh_dev"))).click()
        WebDriverWait(self._driver, 60).until(EC.presence_of_element_located((By.CLASS_NAME, "v-grid-container")))
        rows = self._driver.find_elements(By.CLASS_NAME, "v-grid-container")
        for row in rows:
            if device_name in row.text.split('\n'):
                row.find_element(By.TAG_NAME, "button").click()
                break

        WebDriverWait(self._driver, 60).until(EC.element_to_be_clickable((By.ID, "uiApply")))
        self._driver.execute_script('var gOrigValues = {}; getOrigValues()')
        thermostat_data = self._driver.execute_script('return gOrigValues')
        room_temp = self._driver.execute_script('return jxl.find("input[type=hidden][name=Roomtemp]")[0][\'value\']')
        thermostat_data['Roomtemp'] = room_temp
        self._driver.close()
        return thermostat_data

    def _get_device_id_by_name(self, device_name):
        if self._devices is None:
            self.update_devices()
        for dev in self._devices.values():
            if dev.name == device_name:
                return dev.identifier

    def set_thermostat_offset(self, device_name, offset):        
        verify_url = '/'.join([self.get_prefixed_host(), 'net', 'home_auto_hkr_edit.lua'])
        set_url = '/'.join([self.get_prefixed_host(), 'data.lua'])
        verify_data = self._generate_data_pkg('verify', device_name, offset)
        set_data = self._generate_data_pkg('set', device_name, offset)
        verification = requests.post(verify_url, headers=self._generate_headers(verify_data), json=verify_data)
        requests.post(set_url, headers=self._generate_headers(set_data), json=set_data)

    def _generate_headers(self, data):
        headers = {"Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.get_prefixed_host,
            "Content-Length": str(len(data)),
            "Accept-Language": "en-GB,en;q=0.9",
            "Host": self.get_prefixed_host.split('://')[1],
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.2 Safari/605.1.15",
            "Referer": self.get_prefixed_host,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"}
        return headers
    
    def _generate_data_pkg(self, req_type, device_name, offset):
        current_thermostat_data = self._get_raw_thermostat_data(device_name)
        common_data = "\
            sid={SID}&\
            device={DEV_ID}&\
            view=&\
            back_to_page=sh_dev&\
            ule_device_name={DEV_NAME}&\
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
                SID= self._sid,
                DEV_ID= self._get_device_id_by_name(device_name),
                DEV_NAME= device_name,
                HEATING_TEMP= current_thermostat_data[],
                NIGHT_TEMP= current_thermostat_data[],
                TIMER0= current_thermostat_data[],
                TIMER1= current_thermostat_data[],
                HOLIDAY_TEMP= current_thermostat_data[],
                HOLIDAY_1_START_DAY= current_thermostat_data[],
                HOLIDAY_1_START_MONTH= current_thermostat_data[],
                HOLIDAY_1_START_HOUR= current_thermostat_data[],
                HOLIDAY_1_END_DAY= current_thermostat_data[],
                HOLIDAY_1_END_MONTH= current_thermostat_data[],
                HOLIDAY_1_END_HOUR= current_thermostat_data[],
                HOLIDAY_1_ENABLED= current_thermostat_data[],
                HOLIDAY_1_ID= current_thermostat_data[],
                HOLIDAY_2_START_DAY= current_thermostat_data[],
                HOLIDAY_2_START_MONTH= current_thermostat_data[],
                HOLIDAY_2_START_HOUR= current_thermostat_data[],
                HOLIDAY_2_END_DAY= current_thermostat_data[],
                HOLIDAY_2_END_MONTH= current_thermostat_data[],
                HOLIDAY_2_END_HOUR= current_thermostat_data[],
                HOLIDAY_2_ENABLED= current_thermostat_data[],
                HOLIDAY_2_ID= current_thermostat_data[],
                HOLIDAY_3_START_DAY= current_thermostat_data[],
                HOLIDAY_3_START_MONTH= current_thermostat_data[],
                HOLIDAY_3_START_HOUR= current_thermostat_data[],
                HOLIDAY_3_END_DAY= current_thermostat_data[],
                HOLIDAY_3_END_MONTH= current_thermostat_data[],
                HOLIDAY_3_END_HOUR= current_thermostat_data[],
                HOLIDAY_3_ENABLED= current_thermostat_data[],
                HOLIDAY_3_ID= current_thermostat_data[],
                HOLIDAY_4_START_DAY= current_thermostat_data[],
                HOLIDAY_4_START_MONTH= current_thermostat_data[],
                HOLIDAY_4_START_HOUR= current_thermostat_data[],
                HOLIDAY_4_END_DAY= current_thermostat_data[],
                HOLIDAY_4_END_MONTH= current_thermostat_data[],
                HOLIDAY_4_END_HOUR= current_thermostat_data[],
                HOLIDAY_4_ENABLED= current_thermostat_data[],
                HOLIDAY_4_ID= current_thermostat_data[],
                HOLIDAY_ENABLED_COUNT= current_thermostat_data[],
                SUMMER_START_DAY= current_thermostat_data[],
                SUMMER_START_MONTH= current_thermostat_data[],
                SUMMER_END_DAY= current_thermostat_data[],
                SUMMER_END_MONTH= current_thermostat_data[],
                SUMMER_ENABLED= current_thermostat_data[],
                WINDOW_OPEN_TRIGGER= current_thermostat_data[],
                WINDOW_OPEN_TIMER= current_thermostat_data[],
                ROOM_TEMP= current_thermostat_data[],
                OFFSET= offset
            )
        if req_type == 'verify':
            data = common_data + '&validate=apply&xhr=1&useajax=1'
        elif req_type == 'set':
            data = common_data + '&validate=&xhr=1'
        else:
            print('error')
        return data
