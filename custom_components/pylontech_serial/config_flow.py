"""Config flow for Pylontech Serial integration."""
import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_BAUD_RATE, CONF_POLL_INTERVAL, CONF_BATTERY_CAPACITY, DEFAULT_BAUD_RATE, DEFAULT_POLL_INTERVAL, DEFAULT_BATTERY_CAPACITY

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pylontech Serial."""

    VERSION = 1


    async def async_step_usb(self, discovery_info: UsbServiceInfo):
        """Handle USB discovery."""
        await self.async_set_unique_id(discovery_info.serial_number or discovery_info.device)
        self._abort_if_unique_id_configured()

        return await self.async_step_user(usb_device=discovery_info.device)

    async def async_step_user(self, user_input=None, usb_device=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Pylontech Battery", data=user_input)

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {}
        for port in ports:
            list_of_ports[port.device] = f"{port.device} - {port.description}"

        if usb_device and usb_device not in list_of_ports:
            list_of_ports[usb_device] = usb_device

        default_port = usb_device if usb_device else vol.UNDEFINED

        schema = vol.Schema({
            vol.Required(CONF_SERIAL_PORT, default=default_port): vol.In(list_of_ports),
            vol.Required(CONF_BAUD_RATE, default=DEFAULT_BAUD_RATE): int,
            vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
            vol.Required(CONF_BATTERY_CAPACITY, default=DEFAULT_BATTERY_CAPACITY): float,
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Handle user options."""
        errors = {}
        
        current_port = self.config_entry.options.get(CONF_SERIAL_PORT, self.config_entry.data.get(CONF_SERIAL_PORT))
        current_baud = self.config_entry.options.get(CONF_BAUD_RATE, self.config_entry.data.get(CONF_BAUD_RATE))
        current_poll = self.config_entry.options.get(CONF_POLL_INTERVAL, self.config_entry.data.get(CONF_POLL_INTERVAL))
        current_cap = self.config_entry.options.get(CONF_BATTERY_CAPACITY, self.config_entry.data.get(CONF_BATTERY_CAPACITY))

        if user_input is not None:
             return self.async_create_entry(title="", data=user_input)

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {}
        for port in ports:
            list_of_ports[port.device] = f"{port.device} - {port.description}"
        
        # Ensure current port is in list (even if not currently connected/detected, to avoid validation error if user doesn't want to change it but it's offline)
        if current_port not in list_of_ports:
            list_of_ports[current_port] = current_port

        schema = vol.Schema({
            vol.Required(CONF_SERIAL_PORT, default=current_port): vol.In(list_of_ports),
            vol.Required(CONF_BAUD_RATE, default=current_baud): int,
            vol.Required(CONF_POLL_INTERVAL, default=current_poll): int,
            vol.Required(CONF_BATTERY_CAPACITY, default=current_cap): float,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
