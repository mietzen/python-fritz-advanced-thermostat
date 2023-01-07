# Advanced Fritz Thermostat

A library for setting the values [AHA requests](https://avm.de/fileadmin/user_upload/Global/Service/Schnittstellen/AHA-HTTP-Interface.pdf) won't let you!

For basic settings use [Heikos (hthiery)](https://github.com/hthiery) amazing [pyfritzhome](https://github.com/hthiery/python-fritzhome)!

## Disclaimer

This library will always be hacky and will never leave a "beta state".

It uses undocumented API's and selenium for data scraping.
I use this library myself and I give my best to keep it updated.

But beware with any FritzOS upgrade this library might stop working, don't uses this if you can't live with that!

**Also Remember:** I'm doing this for **free** as a **hobby**!


## Tested configurations

|     Device     | Tested in FritzOS |
|:--------------:|:-----------------:|
| FRITZ!DECT 301 |       7.29        |

If you have a different device or FritzOS version set `experimental=True` this will disable all checks, but beware there might be dragons!

## Setup

Install using `pip`:

```shell
pip install fritzadvancedthermostat
```

You will also need to [setup a user](https://github.com/hthiery/python-fritzhome#fritzbox-user).

## Example Usage

```python
from fritz_advanced_thermostat import FritzAdvancedThermostat

host='192.168.178.1'
user='my-user'
password='my-password'

fat = FritzAdvancedThermostat(host, user, password, ssl_verify=False, experimental=False)

print('Available thermostats:')
devices = fat.get_thermostats()
for dev in devices:
    print('Device name: ' + dev)

device_name = devices[0]
current_offset = fat.get_thermostat_offset(device_name)
print('Current offset of ' + device_name + ': ' + str(current_offset))
fat.set_thermostat_offset(device_name, current_offset + 1)
fat.commit(device_name)

new_offset = fat.get_thermostat_offset(device_name, force_reload=True)
print('New offset of ' + device_name + ': ' + str(new_offset))
```

## Contribute

Contributions are always welcome, just open a PR, specially if you find a way to obtain the thermostat data without selenium!