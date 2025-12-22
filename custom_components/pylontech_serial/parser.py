import re
import logging
from datetime import datetime
from .structs import PylontechSystem, PylontechBattery

_LOGGER = logging.getLogger(__name__)

class PylontechParser:
    """Parser for Pylontech BMS serial data."""

    @staticmethod
    def parse_pwr(raw_text: str, current_system: PylontechSystem = None) -> PylontechSystem:
        """Parses 'pwr' command output. Returns updated system object."""
        if current_system is None:
            # Create dummy initial system if not provided, though usually we update an existing state
            current_system = PylontechSystem(0,0,0,0,0,0,0)

        batteries = []
        lines = raw_text.splitlines()
        
        valid_lines = 0
        total_voltage = 0.0
        total_current = 0.0
        total_soc = 0.0
        
        for line in lines:
            parts = line.split()
            # Expecting: ID, Volt, Curr, Temp, Tlow, Thigh, Vlow, Vhigh, Base.St, ...
            # Clean: "1 50691 3806 17000 ..."
            # Length check: ID(0)+V(1)+C(2)+T(3)+Tl(4)+Th(5)+Vl(6)+Vh(7)+Stat(8)...
            
            if len(parts) > 10 and parts[0].isdigit():
                if "Absent" in line: continue
                try:
                    bat_id = int(parts[0])
                    voltage = int(parts[1]) / 1000.0
                    current = int(parts[2]) / 1000.0
                    temp = int(parts[3]) / 1000.0
                    # Status is at index 8 (Base.St)
                    status = parts[8]
                    # SOC is at index 12 (Coulomb) - usually ends with %
                    soc = int(parts[12].replace('%', ''))
                    
                    power = round(voltage * current, 2)
                    
                    bat = PylontechBattery(
                        sys_id=bat_id,
                        voltage=voltage,
                        current=current,
                        temperature=temp,
                        soc=soc,
                        status=status,
                        power=power,
                        raw=line.strip()
                    )
                    batteries.append(bat)
                    
                    total_voltage += voltage
                    total_current += current
                    total_soc += soc
                    valid_lines += 1
                    
                except (ValueError, IndexError) as error:
                    _LOGGER.error(f"Error parsing pwr line '{line}': {error}")
                    continue
        
        current_system.batteries = batteries
        current_system.raw = raw_text
        
        if valid_lines > 0:
            current_system.voltage = round(total_voltage / valid_lines, 2)
            current_system.current = round(total_current, 2)
            current_system.soc = round(total_soc / valid_lines, 1)
            current_system.power = round(current_system.voltage * current_system.current, 1)
        
        return current_system

    @staticmethod
    def parse_info(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'info' command output."""
        lines = raw_text.splitlines()
        for line in lines:
            if ":" in line:
                parts = line.split(":", 1)
                key = parts[0].strip().lower()
                val = parts[1].strip()
                
                # Device address      : 1
                # Manufacturer        : Pylon
                # Board version       : PHANTOMSAV10R03
                # Main Soft version   : B66.6
                # Soft  version       : V2.4
                # Boot  version       : V2.0
                # Comm version        : V2.0
                # Barcode             : PPTBH02400710243
                # Specification       : 48V/50AH
                # Cell Number         : 15
                
                if "manufacturer" in key: system.manufacturer = val
                if "device name" in key or "model" in key: system.model = val
                if "main soft" in key or "sw_version" in key: system.fw_version = val
                if "barcode" in key: system.barcode = val
                if "specification" in key: system.spec = val
                if "cell number" in key:
                    try:
                        system.cell_count = int(val)
                    except: pass
                    
        return system

    @staticmethod
    def parse_stat(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'stat' command output."""
        # Clean output from docs:
        # CYCLE Times     :      430
        
        # We look for "CYCLE Times"
        cycle_match = re.search(r"CYCLE Times\s*:\s*(\d+)", raw_text, re.IGNORECASE)
        if cycle_match:
            system.cycles = int(cycle_match.group(1))
            
        # SOH? The docs 'stat' output doesn't show SOH explicitly as a key value pair in the list?
        # "SOH Times       :        0" ? No that's probably a counter of SOH events.
        # "Pwr Coulomb     : 153311400"
        
        # The 'soh' command output in docs shows "SOHCount   SOHStatus". It doesn't show SOH %.
        # Usually Pylontech gives SOH%. 
        # But 'stat' output in docs has "Pwr Percent : 89". Maybe that's SOC?
        
        # If the user says "exclude info from individual battery", implying we should find it for stack.
        # If 'soh' command gives 0 SOHCount, maybe SOH is not reported nicely.
        # Let's check 'info' or 'pwr'.
        # 'pwr' doesn't show SOH.
        
        # In previous code we looked for "SOH : value".
        # If not found, we might default to 100 or None.
        
        return system

    @staticmethod
    def parse_time(raw_text: str, system: PylontechSystem) -> PylontechSystem:
        """Parses 'time' command output.
        Example: Ds3231 2025-12-21 21:14:53
        """
        # Look for YYYY-MM-DD HH:MM:SS pattern
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", raw_text)
        if match:
             system.bms_time = match.group(1)
        return system

    @staticmethod
    def generate_time_command(timestamp: datetime) -> str:
        """Generates the 'time' command for specific datetime."""
        # time [year] [month] [day] [hour] [minute] [second]
        # Example: time 25 12 21 13 00 00
        return timestamp.strftime("time %y %m %d %H %M %S")
