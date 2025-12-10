"""Sensor platform for Pylontech Serial."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfEnergy,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    unique_id_prefix = entry.entry_id

    entities = []
    
    # --- System Sensors ---
    # Voltage
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_volt", "System Voltage", 
        UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, "voltage"
    ))
    # Current
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_curr", "System Current", 
        UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, "current"
    ))
    # SOC
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_soc", "System SOC", 
        PERCENTAGE, SensorDeviceClass.BATTERY, "soc"
    ))
    # Power (Required for dashboard optional graphs)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_power", "System Power", 
        UnitOfPower.WATT, SensorDeviceClass.POWER, "power"
    ))

    # Energy In (Charge) - For Dashboard "Battery Charged"
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_in", "System Energy Charged", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, "energy_in",
        state_class=SensorStateClass.TOTAL_INCREASING
    ))
    
    # Energy Out (Discharge) - For Dashboard "Battery Discharged"
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_out", "System Energy Discharged", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, "energy_out",
        state_class=SensorStateClass.TOTAL_INCREASING
    ))

    # Stored Energy (Capacity)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_energy_stored", "System Stored Energy", 
        UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY_STORAGE, "energy_stored",
        state_class=SensorStateClass.MEASUREMENT
    ))

    # SOH (System Average)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_soh", "System SOH", 
        PERCENTAGE, SensorDeviceClass.BATTERY, "soh",
        state_class=SensorStateClass.MEASUREMENT
    ))

    # Cycle Count (System Average)
    entities.append(PylontechSystemSensor(
        coordinator, unique_id_prefix, "sys_cycles", "System Cycles", 
        None, None, "cycles",
        state_class=SensorStateClass.MEASUREMENT
    ))



    # --- Per Battery Sensors ---
    if coordinator.data and "batteries" in coordinator.data:
        for bat in coordinator.data["batteries"]:
            bat_id = bat["id"]
            # Voltage
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "volt", "Voltage", 
                 UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, "voltage"
            ))
            # Current
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "curr", "Current", 
                 UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, "current"
            ))
            # Temp
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "temp", "Temperature", 
                 UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, "temp"
            ))
            # SOC
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "soc", "SOC", 
                 PERCENTAGE, SensorDeviceClass.BATTERY, "soc"
            ))
            # SOH
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "soh", "SOH", 
                 PERCENTAGE, SensorDeviceClass.BATTERY, "soh"
            ))
            # Cycles
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "cycles", "Cycles", 
                 None, None, "cycles"
            ))
            # Power
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "power", "Power", 
                 UnitOfPower.WATT, SensorDeviceClass.POWER, "power"
            ))
            # Status (Text)
            entities.append(PylontechBatterySensor(
                 coordinator, unique_id_prefix, bat_id, "status", "Status", 
                 None, None, "status"
            ))

    async_add_entities(entities)


class PylontechSystemSensor(CoordinatorEntity, SensorEntity):
    """Representation of a System-wide Sensor."""

    def __init__(self, coordinator, unique_id_prefix, key, name, unit, device_class, json_key, state_class=None):
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._unit = unit
        self._device_class = device_class
        self._json_key = json_key
        self._attr_state_class = state_class
        
        self._attr_unique_id = f"{unique_id_prefix}_{key}"
        self._attr_name = name
        
        # Default Info
        dev_info = {
            "identifiers": {(DOMAIN, "system")},
            "name": "Pylontech Stack",
            "manufacturer": "Pylontech",
            "model": "US Series Stack",
        }
        
        # Enrich with fetched Info
        if hasattr(coordinator, "device_info") and coordinator.device_info:
             if "sw_version" in coordinator.device_info:
                 dev_info["sw_version"] = coordinator.device_info["sw_version"]
             if "model" in coordinator.device_info:
                 dev_info["model"] = coordinator.device_info["model"]
             # If we had a serial number, we could use it in identifiers, but sticking to (DOMAIN, "system") is safer for persistence

        self._attr_device_info = dev_info

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or "system" not in self.coordinator.data:
            return None
        return self.coordinator.data["system"].get(self._json_key)

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_class(self):
        return self._device_class

class PylontechBatterySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Per-Battery Sensor."""

    def __init__(self, coordinator, unique_id_prefix, bat_id, suffix, name_suffix, unit, device_class, json_key):
        super().__init__(coordinator)
        self._bat_id = bat_id
        self._json_key = json_key
        self._unit = unit
        self._device_class = device_class
        
        self._attr_unique_id = f"{unique_id_prefix}_bat{bat_id}_{suffix}"
        self._attr_name = f"Battery {bat_id} {name_suffix}"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"battery_{bat_id}")},
            "name": f"Pylontech Module {bat_id}",
            "manufacturer": "Pylontech",
            "model": "US2000/3000",
            "via_device": (DOMAIN, "system"),
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or "batteries" not in self.coordinator.data:
            return None
        # Find battery with matching ID
        for b in self.coordinator.data["batteries"]:
            if b["id"] == self._bat_id:
                return b.get(self._json_key)
        return None

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_class(self):
        return self._device_class
