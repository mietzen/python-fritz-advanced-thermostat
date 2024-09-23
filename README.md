# Advanced Fritz Thermostat

A library for setting the values [AHA requests](https://avm.de/fileadmin/user_upload/Global/Service/Schnittstellen/AHA-HTTP-Interface.pdf) won't let you!

For basic settings use [Heikos (hthiery)](https://github.com/hthiery) amazing [pyfritzhome](https://github.com/hthiery/python-fritzhome)!


This library will always be hacky and will never leave the "beta state", since it uses undocumented API's and selenium for data scraping.
I use this library myself and I give my best to keep it updated.

But with any FritzOS upgrade this library might stop working, don't uses this if you can't live with that!

**Remember:** I'm doing this for **free** as a **hobby**, so be nice!

## Requirements

* Python 3.9.0 or higher

## Tested configurations

|     Device     | Tested in FritzOS |
|:--------------:|:-----------------:|
| FRITZ!DECT 301 |       7.29        |
| FRITZ!DECT 301 |       7.30        |
| FRITZ!DECT 301 |       7.31        |
| FRITZ!DECT 301 |       7.56        |
| FRITZ!DECT 301 |       7.57        |

If you have a different device or FritzOS version set `experimental=True` this will disable all checks, but beware there might be dragons!

## Setup

Install using `pip`:

```shell
pip install fritz-advanced-thermostat
```

You will also need to [setup a user](https://github.com/hthiery/python-fritzhome#fritzbox-user).

## Example Usage

```python
from fritz_advanced_thermostat import FritzAdvancedThermostat
from fritz_advanced_thermostat import FritzAdvancedThermostatError

host = '192.168.178.1'
user = 'my-user'
password = 'my-password'

try:
    fat = FritzAdvancedThermostat(host, user, password, ssl_verify=False, experimental=False)

    print('Available thermostats:')
    devices = fat.get_thermostats()
    for dev in devices:
        print('Device name: ' + dev)

    device_name = next(iter(devices))  # Get the first device name
    current_offset = fat.get_thermostat_offset(device_name)
    print(f'Current offset of {device_name}: {current_offset}')

    fat.set_thermostat_offset(device_name, current_offset + 1)
    fat.commit()

    new_offset = fat.get_thermostat_offset(device_name, force_reload=True)
    print(f'New offset of {device_name}: {new_offset}')

except FritzAdvancedThermostatError as err:
    print('An error occurred, check the logs!')
    print(err)
```

## Credits

Thanks to:
- [Argelbargel](https://github.com/Argelbargel) from the openHab community for [showing me a way](https://community.openhab.org/t/groovy-script-rule-to-update-temperature-offsets-of-avm-fritz-dect-301-302-based-on-external-temperature-sensors/139917) to obtain the thermostat data without selenium.

## Disclaimer

**This package is not related to or developed by AVM. No relationship between the developer of this package and AVM exists.**

**All trademarks, logos and brand names are the property of their respective owners. All company, product and service names used in this package are for identification purposes only. Use of these names,trademarks and brands does not imply endorsement.**
