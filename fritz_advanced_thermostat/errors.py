class FritzAdvancedThermostatExecutionError(Exception):
    pass

class FritzAdvancedThermostatCompatibilityError(Exception):
    pass

class FritzAdvancedThermostatKeyError(KeyError):
    pass

class FritzAdvancedThermostatConnectionError(ConnectionError):
    pass

FritzAdvancedThermostatError = (FritzAdvancedThermostatExecutionError, FritzAdvancedThermostatCompatibilityError, FritzAdvancedThermostatKeyError, FritzAdvancedThermostatConnectionError)
