import serial
import time
import json
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
MQTT_BROKER = "192.168.2.10" # Or IP address
MQTT_PORT = 1883
MQTT_USER = "batteries"
MQTT_PASS = "F90ewxDsif2vWP06"

# Base topic for state updates
STATE_TOPIC = "pylontech/stack/state"
# Base topic for HA Discovery (Standard is 'homeassistant')
DISCOVERY_PREFIX = "homeassistant" 
NODE_ID = "pylontech_stack"

# How many batteries do you physically have?
BATTERY_COUNT = 2 

def publish_discovery_config(client):
    """
    Sends the MQTT Discovery payloads so HA creates the entities automatically.
    """
    print("Sending Auto-Discovery Config...")

    # --- 1. DEFINE THE DEVICE ---
    # This groups all sensors under one "Device" in Home Assistant
    device_info = {
        "identifiers": [NODE_ID],
        "name": "Pylontech Battery Stack",
        "manufacturer": "Pylontech",
        "model": "US2000 (Console)",
        "sw_version": "Console-v1"
    }

    # --- 2. DEFINE SENSORS TO CREATE ---
    
    # List of System-wide sensors
    system_sensors = [
        {"id": "sys_soc", "name": "System SOC", "unit": "%", "class": "battery", "tpl": "{{ value_json.system.soc }}"},
        {"id": "sys_volt", "name": "System Voltage", "unit": "V", "class": "voltage", "tpl": "{{ value_json.system.voltage }}"},
        {"id": "sys_curr", "name": "System Current", "unit": "A", "class": "current", "tpl": "{{ value_json.system.current }}"},
        {"id": "sys_power", "name": "System Power", "unit": "W", "class": "power", "tpl": "{{ value_json.system.power }}"},
    ]

    # List of Per-Battery sensors
    bat_sensors = [
        {"suffix": "volt", "name": "Voltage", "unit": "V", "class": "voltage", "prop": "voltage"},
        {"suffix": "curr", "name": "Current", "unit": "A", "class": "current", "prop": "current"},
        {"suffix": "temp", "name": "Temperature", "unit": "°C", "class": "temperature", "prop": "temp"},
        {"suffix": "soc", "name": "SOC", "unit": "%", "class": "battery", "prop": "soc"},
        {"suffix": "status", "name": "Status", "unit": None, "class": None, "prop": "status"}, # Text sensor
    ]

    # --- 3. PUBLISH SYSTEM CONFIGS ---
    for s in system_sensors:
        unique_id = f"{NODE_ID}_{s['id']}"
        config_topic = f"{DISCOVERY_PREFIX}/sensor/{NODE_ID}/{s['id']}/config"
        
        payload = {
            "name": s["name"],
            "unique_id": unique_id,
            "state_topic": STATE_TOPIC,
            "value_template": s["tpl"],
            "device": device_info,
            "availability_topic": STATE_TOPIC,
            "availability_template": "{{ 'online' if value_json.system.count is defined else 'offline' }}"
        }
        if s["unit"]: payload["unit_of_measurement"] = s["unit"]
        if s["class"]: payload["device_class"] = s["class"]

        client.publish(config_topic, json.dumps(payload), retain=True)

    # --- 4. PUBLISH PER-BATTERY CONFIGS ---
    for i in range(1, BATTERY_COUNT + 1):
        for s in bat_sensors:
            unique_id = f"{NODE_ID}_bat{i}_{s['suffix']}"
            object_id = f"bat{i}_{s['suffix']}"
            config_topic = f"{DISCOVERY_PREFIX}/sensor/{NODE_ID}/{object_id}/config"
            
            # Access list by index [i-1] because lists are 0-indexed but batteries are 1-indexed
            template = f"{{{{ value_json.batteries[{i-1}].{s['prop']} }}}}"

            payload = {
                "name": f"Battery {i} {s['name']}",
                "unique_id": unique_id,
                "state_topic": STATE_TOPIC,
                "value_template": template,
                "device": device_info
            }
            if s["unit"]: payload["unit_of_measurement"] = s["unit"]
            if s["class"]: payload["device_class"] = s["class"]
            
            client.publish(config_topic, json.dumps(payload), retain=True)

    print("Discovery sent. Check Home Assistant devices.")

def parse_pwr_response(raw_text):
    """
    Parses the ASCII table from the 'pwr' command.
    Returns a list of battery objects and a summary object.
    """
    batteries = []
    lines = raw_text.splitlines()
    for line in lines:
        parts = line.split()
        if len(parts) > 10 and parts[0].isdigit():
            if "Absent" in line: continue
            try:
                bat_id = int(parts[0])
                # Parsing logic based on your provided table
                voltage = int(parts[1]) / 1000.0
                current = int(parts[2]) / 1000.0
                temp = int(parts[3]) / 1000.0
                status = parts[8]
                soc = int(parts[12].replace('%', ''))
                
                batteries.append({
                    "id": bat_id,
                    "voltage": voltage,
                    "current": current,
                    "temp": temp,
                    "soc": soc,
                    "status": status,
                    "power": round(voltage * current, 2)
                })
            except ValueError as error:
                print("Could not parse response:")
                print(error)
                continue

    total_voltage = 0
    total_current = 0
    avg_soc = 0
    total_power = 0
    
    print(f"Found {len(batteries)} batteries.")
    
    if batteries:
        total_voltage = sum(b['voltage'] for b in batteries) / len(batteries)
        total_current = sum(b['current'] for b in batteries)
        avg_soc = sum(b['soc'] for b in batteries) / len(batteries)
        total_power = total_voltage * total_current

    return {
        "system": {
            "voltage": round(total_voltage, 2),
            "current": round(total_current, 2),
            "soc": round(avg_soc, 1),
            "power": round(total_power, 1),
            "count": len(batteries)
        },
        "batteries": batteries
    }

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "PylonDiscovery")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        # 1. SEND DISCOVERY CONFIG ONCE ON STARTUP
        publish_discovery_config(client)
        
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        print(f"Listening on {SERIAL_PORT}...")

        while True:
            print("Requesting \"pwr\" to batteries...")
            ser.write(b"\n")
            time.sleep(0.2)
            ser.read_all()
            ser.write(b"pwr\n")
            time.sleep(1.5)
            
            print("Reading response...")
            raw_data = ser.read_all().decode('ascii', errors='ignore')
            
            if "Power Volt" in raw_data:
                data = parse_pwr_response(raw_data)
                # Only publish if we actually parsed data
                if data and data["system"]["count"] > 0:
                    print("Parsed response:")
                    print(data)
                    json_str = json.dumps(data)
                    client.publish(STATE_TOPIC, json_str)
                    print("Data published.")
                else:
                    print("Could not parse data:")
                    print(data)
            else:
                print("Got unknown response:")
                print(raw_data)
            
            time.sleep(10)

    except KeyboardInterrupt:
        client.loop_stop()
        ser.close()
        print("Exiting...")

if __name__ == "__main__":
    main()
