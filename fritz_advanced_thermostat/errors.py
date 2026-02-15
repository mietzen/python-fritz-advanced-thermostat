"""Custom exceptions for FritzAdvancedThermostat."""


class FritzAdvancedThermostatExecutionError(Exception):
    """Unknown error while executing."""


class FritzAdvancedThermostatCompatibilityError(Exception):
    """Fritz!BOX is not compatible with this module."""


class FritzAdvancedThermostatKeyError(KeyError):
    """Error while obtaining a key from the Fritz!BOX."""


class FritzAdvancedThermostatConnectionError(ConnectionError):
    """Error while connecting to the Fritz!BOX."""


FritzAdvancedThermostatError = (FritzAdvancedThermostatExecutionError, FritzAdvancedThermostatCompatibilityError, FritzAdvancedThermostatKeyError, FritzAdvancedThermostatConnectionError)

