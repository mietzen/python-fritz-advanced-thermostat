"""Init file for fritz_advanced_thermostat"""

from .errors import (
    FritzAdvancedThermostatCompatibilityError,
    FritzAdvancedThermostatConnectionError,
    FritzAdvancedThermostatError,
    FritzAdvancedThermostatExecutionError,
    FritzAdvancedThermostatKeyError,
)
from .fritz_advanced_thermostat import FritzAdvancedThermostat

__all__ = (
    "FritzAdvancedThermostat",
    "FritzAdvancedThermostatError",
    "FritzAdvancedThermostatExecutionError",
    "FritzAdvancedThermostatCompatibilityError",
    "FritzAdvancedThermostatKeyError",
    "FritzAdvancedThermostatConnectionError",
)
