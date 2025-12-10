"""DataUpdateCoordinator for Pylontech Serial."""
import asyncio
import logging
import serial
import time
from datetime import datetime, timedelta
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PylontechCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Pylontech battery."""

    def __init__(self, hass: HomeAssistant, port, baud_rate, poll_interval, battery_capacity):
        """Initialize."""
        self.port = port
        self.baud_rate = baud_rate
        self.battery_capacity = battery_capacity
        self.serial = None
        
        # Energy calculation state
        self.last_update_time = None
        self.system_energy_in = 0.0  # kWh (Charge)
        self.system_energy_out = 0.0 # kWh (Discharge)
        
        self.device_info = {} # Populated by 'info' command

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )

    def _open_serial(self):
        if self.serial is None:
            _LOGGER.debug(f"Opening serial port {self.port} at {self.baud_rate}")
            self.serial = serial.Serial(self.port, self.baud_rate, timeout=2)
        elif not self.serial.is_open:
             self.serial.open()

    def _close_serial(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

    async def _async_update_data(self):
        """Fetch data from the device."""
        if not self.device_info:
             await self.hass.async_add_executor_job(self._read_info_data)
        return await self.hass.async_add_executor_job(self._read_full_data)

    def _read_info_data(self):
        """Read device info (firmware, serial) once."""
        try:
            self._open_serial()
            self.serial.reset_input_buffer()
            self.serial.write(b"\n")
            time.sleep(0.1)
            self.serial.read_all()

            _LOGGER.debug("Sending 'info' command")
            self.serial.write(b"info\n")
            time.sleep(1.0)
            
            raw_data = self.serial.read_all().decode('ascii', errors='ignore')
            raw_data = self.serial.read_all().decode('ascii', errors='ignore')

            # Parse info
            # Output format varies, but usually contains:
            # Device: ...
            # Version: ...
            # Serial: ...
            # or just unstructured text
            
            lines = raw_data.splitlines()
            info = {}
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].strip().lower()
                    val = parts[1].strip()
                    if "ver" in key: info["sw_version"] = val
                    if "serial" in key or "barcode" in key: info["serial_number"] = val
                    if "device" in key: info["model"] = val
            
            self.device_info = info
            _LOGGER.info(f"Parsed device info: {self.device_info}")

        except Exception as e:
            _LOGGER.warning(f"Failed to fetch device info: {e}")
            # Don't fail the main update, just log

    def _read_full_data(self):
        """Read data from serial synchronously."""
        try:
            self._open_serial()
            
            # Flush junk
            self.serial.reset_input_buffer()
            self.serial.write(b"\n")
            time.sleep(0.1)
            self.serial.read_all()

            # Send command
            _LOGGER.debug("Sending 'pwr' command")
            self.serial.write(b"pwr\n")
            time.sleep(1.0) # Wait for response
            
            raw_data_pwr = self.serial.read_all().decode('ascii', errors='ignore')
            _LOGGER.debug(f"Received pwr data: {raw_data_pwr[:100]}...") # Log first 100 chars
            
            if "Power Volt" not in raw_data_pwr:
                # Try once more?
                _LOGGER.warning("Invalid response for 'pwr', retrying...")
                time.sleep(1.0)
                raw_data_pwr = self.serial.read_all().decode('ascii', errors='ignore')
            
            if "Power Volt" not in raw_data_pwr:
                 raise UpdateFailed("Did not receive valid 'pwr' response header.")

            # Send STAT command (since soh command was returning cell voltages and help confirmed stat exists)
            _LOGGER.debug("Sending 'stat' command for SOH/Cycles")
            self.serial.write(b"stat\n")
            time.sleep(1.0) # Wait for response
            
            raw_data_stat = self.serial.read_all().decode('ascii', errors='ignore')
            # _LOGGER.warning(f"DEBUG: Received stat raw data:\n{raw_data_stat}") # Keep warning for verification if needed, or downgrade to debug

            data = self._parse_pwr_response(raw_data_pwr)
            stat_map = self._parse_stat_response(raw_data_stat)
            
            # Merge STAT data (SOH, Cycles)
            if stat_map:
                for bat in data["batteries"]:
                    bat_id = bat["id"]
                    if bat_id in stat_map:
                        bat_data = stat_map[bat_id]
                        if "soh" in bat_data: bat["soh"] = bat_data["soh"]
                        if "cycles" in bat_data: bat["cycles"] = bat_data["cycles"]
                
                # Recalculate System SOH
                soh_values = [b.get("soh") for b in data["batteries"] if b.get("soh") is not None]
                if soh_values:
                    data["system"]["soh"] = round(sum(soh_values) / len(soh_values), 1)
                    
                # Calculate System Cycles (Average? Or Max?)
                # Usually max or average. Let's do average.
                cycle_values = [b.get("cycles") for b in data["batteries"] if b.get("cycles") is not None]
                if cycle_values:
                    data["system"]["cycles"] = int(sum(cycle_values) / len(cycle_values))

            return data

        except Exception as e:
            self._close_serial()
            raise UpdateFailed(f"Serial Error: {e}")

    def _parse_pwr_response(self, raw_text):
        """Parses the ASCII table from the 'pwr' command."""
        batteries = []
        lines = raw_text.splitlines()
        for line in lines:
            parts = line.split()
            # Basic validation of line format
            if len(parts) > 10 and parts[0].isdigit():
                if "Absent" in line: continue
                try:
                    bat_id = int(parts[0])
                    # Original logic: voltage=1, current=2, temp=3, status=8, soc=12
                    voltage = int(parts[1]) / 1000.0
                    current = int(parts[2]) / 1000.0
                    temp = int(parts[3]) / 1000.0
                    status = parts[8]
                    soc = int(parts[12].replace('%', ''))
                    
                    power = round(voltage * current, 2)

                    batteries.append({
                        "id": bat_id,
                        "voltage": voltage,
                        "current": current,
                        "temp": temp,
                        "soc": soc,
                        "status": status,
                        "power": power
                    })
                except (ValueError, IndexError) as error:
                   _LOGGER.error(f"Error parsing pwr line '{line}': {error}")
                   continue

        if not batteries:
            raise UpdateFailed("No batteries found in response.")

        # Aggregate System Data
        total_voltage = sum(b['voltage'] for b in batteries) / len(batteries)
        total_current = sum(b['current'] for b in batteries) # Parallel connection
        avg_soc = sum(b['soc'] for b in batteries) / len(batteries)
        total_power_w = total_voltage * total_current

        # Energy Calculation (Riemann Sum / Trapezoidal roughly)
        now = datetime.now()
        if self.last_update_time:
            time_diff = (now - self.last_update_time).total_seconds() / 3600.0 # Hours
            energy_kwh = (total_power_w * time_diff) / 1000.0
            
            # Assign to In or Out
            # Assumption: Current > 0 is Charging (In), Current < 0 is Discharging (Out)
            # Or usually: Discharge is positive for load.
            # Let's infer from Pylontech common behavior: 
            # Often +Current = Charge, -Current = Discharge. 
            # BUT standard convention is usually Discharge (+), Charge (-). 
            # We will expose both raw counters, user can verify.
            # actually if total_power_w is POSITIVE, let's assume Charging (In).
            # If NEGATIVE, Discharging (Out).
            # Let's calibrate: 
            if total_power_w >= 0:
                 self.system_energy_in += abs(energy_kwh)
            else:
                 self.system_energy_out += abs(energy_kwh)
        
        self.last_update_time = now

        return {
            "system": {
                "voltage": round(total_voltage, 2),
                "current": round(total_current, 2),
                "soc": round(avg_soc, 1),
                "power": round(total_power_w, 1),
                "energy_in": round(self.system_energy_in, 3),   # kWh
                "energy_out": round(self.system_energy_out, 3), # kWh
                "energy_stored": round(len(batteries) * self.battery_capacity * (avg_soc / 100.0), 3), # kWh
                "count": len(batteries)
            },
            "batteries": batteries
        }

    def _parse_stat_response(self, raw_text):
        """Parses the 'stat' command output for SOH and Cycles."""
        stat_map = {}
        
        try:
             # Basic regex for "Bat <id> ... SOH <val>" or "CYCLE Times : <val>"
             # The user log shows: "stat @ Device address 1 ... CYCLE Times : 427 ..."
             # This implies "Device address 1" is the battery ID.
             
             # Regex to find blocks per battery or lines
             # Log: "stat @ Device address 1 Data Items ..."
             
             # Let's find all occurences of "Device address (\d+)" and then look for "CYCLE Times : (\d+)" in the same block?
             # Or just split by "stat @" if multiple are present?
             # User log showed repeated "DEBUG: Received stat raw data: ... address 1 ..."
             
             # A simple robust way: 
             # Find all matches of: "Device address\s*(\d+).*?CYCLE Times\s*[:]\s*(\d+)"
             # And also look for "SOH : (\d+)" if it exists (it didn't in user log, but might in others)
             
             # Combined regex might be tricky if SOH is missing.
             # Let's try to match ID and text chunk, then parse chunk.
             
             # Match lines starting with "stat @" or containing "Device address"
             # Actually, split text by "$$" or newlines?
             # The log was one long line? "stat @ Device address 1 ... $$ pylon>"
             
             # Regex for ID and Cycles
             cycle_matches = re.findall(r"Device address\s*(\d+).*?CYCLE Times\s*[:]\s*(\d+)", raw_text, re.IGNORECASE | re.DOTALL)
             for m in cycle_matches:
                 bat_id = int(m[0])
                 cycles = int(m[1])
                 if bat_id not in stat_map: stat_map[bat_id] = {}
                 stat_map[bat_id]["cycles"] = cycles
                 
             # Regex for ID and SOH (if it exists)
             soh_matches = re.findall(r"Device address\s*(\d+).*?SOH\s*[:]\s*(\d+)", raw_text, re.IGNORECASE | re.DOTALL)
             for m in soh_matches:
                 bat_id = int(m[0])
                 soh = int(m[1])
                 if bat_id not in stat_map: stat_map[bat_id] = {}
                 stat_map[bat_id]["soh"] = soh
                 
        except Exception as e:
            _LOGGER.error(f"Error parsing STAT: {e}")
            
        return stat_map
