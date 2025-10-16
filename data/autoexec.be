# AWS IoT BLE Gateway Simulator - autoexec.be v6.2.0
# Purpose: Communication stability test with statistics tracking

var SCRIPT_VERSION = "6.2.0"
var GATEWAY_THING = "IoT-Gateway-000011"
var MQTT_ENDPOINT = "a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com"

# Virtual BLE Device Configuration
var VIRTUAL_DEVICE = {
    'device_id': '09aa8ad8-f23e-4e75-bcbe-332efeb431ce',
    'shadow_name': 'vibration-sensor-001',
    'type': 'vibration_sensor'
}

tasmota.log("==========================================", 2)
tasmota.log("AWS IoT Test v" + SCRIPT_VERSION, 2)
tasmota.log("==========================================", 2)

# ECC P-256 Certificate
var TLS_KEY_B64 = "uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0="
var TLS_CERT_B64 = "MIICkjCCAXqgAwIBAgIUfz7enrgMaOK7FybCLeBIdEKTBlUwDQYJKoZIhvcNAQELBQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20gSW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI1MTAxNTEyNTY0MloXDTQ5MTIzMTIzNTk1OVowIjEgMB4GA1UEAwwXQVdTIElvVCBFQ0MgQ2VydGlmaWNhdGUwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAQI183bSkt+kFGCVIx6HzZmwTpym5nGwudBoe8/lJx+xtaxMc6WpUwqhYIZeQXYbCzZ1Nto7+a4lEhoxPwW0Sono2AwXjAfBgNVHSMEGDAWgBSl1rkIzW0DM/l9VlyGlJ6U5BPUhTAdBgNVHQ4EFgQUNiL3LQyLa3uNbKE4y9ZPdhKiKM8wDAYDVR0TAQH/BAIwADAOBgNVHQ8BAf8EBAMCB4AwDQYJKoZIhvcNAQELBQADggEBAKWbBvCviCl87/CdwoY1wO19FwOz1gC4ei6TGIxNwCOxF11HnTtSET/rfmbDQ0pXshi8EK/M1NHr8Gfxfo3H1BcKWJxhjIKFQ1COQpgMrhPVaJAvH4vPFKa6uEKrIqHqIIw6cwzkyRPio75bgT/SJWqb9ztUUNfJAjq6IImAUhgmSk+inMGBOLLKnf92bPubu+euiqGcCqghUsYTUr/xkvHExmtfWffV1uLkE7rUF7VByAqFYXUuZnmthDUREgA5GsFnVQtFwgy7l3+VouVtVqrLOCjqQmo50lBoWOKDY+mo9G+8fOypFW+0xzUmW+pPBeWdV8ReWlq06d/H/q9dCBA="

# Check and configure TLS certificates ONLY if needed
var result = tasmota.cmd("TLSKey", true)
var tlskey1 = result != nil && result.find('TLSKey1') != nil ? result['TLSKey1'] : -1

if tlskey1 != 32
    tasmota.log("Configuring TLS certificates...", 2)
    tasmota.cmd("TLSKey1 " + TLS_KEY_B64)
    tasmota.cmd("TLSKey2 " + TLS_CERT_B64)
    tasmota.log("✅ TLS configured", 2)
else
    tasmota.log("TLS already configured", 2)
end

tasmota.log("✅ Configuration complete", 2)

# Subscribe to device shadow topics
import mqtt

# Subscribe to delta for commands
var delta_topic = "$aws/things/" + GATEWAY_THING + "/shadow/name/" + VIRTUAL_DEVICE['shadow_name'] + "/update/delta"
mqtt.subscribe(delta_topic)

# Subscribe to get/accepted for initial state synchronization
var get_accepted_topic = "$aws/things/" + GATEWAY_THING + "/shadow/name/" + VIRTUAL_DEVICE['shadow_name'] + "/get/accepted"
mqtt.subscribe(get_accepted_topic)

# Subscribe to update/accepted for confirmation
var update_accepted_topic = "$aws/things/" + GATEWAY_THING + "/shadow/name/" + VIRTUAL_DEVICE['shadow_name'] + "/update/accepted"
mqtt.subscribe(update_accepted_topic)

tasmota.log("📥 Subscribed to shadow topics: " + VIRTUAL_DEVICE['shadow_name'], 2)

# ============================================================
# Virtual BLE Vibration Sensor
# ============================================================

class VirtualVibrationSensor
    var device_id
    var shadow_name
    var gateway_thing

    # Sensor state
    var battery
    var status
    var vibration_threshold
    var sensitivity
    var vibration_level
    var vibration_detected
    var event_count
    var last_trigger_time

    # Timing
    var telemetry_interval
    var last_telemetry_time
    var start_time

    # Statistics
    var telemetry_sent
    var telemetry_confirmed
    var telemetry_failed
    var last_stats_time
    var stats_interval

    # MQTT topics
    var delta_topic
    var update_topic
    var get_topic
    var get_accepted_topic
    var update_accepted_topic
    var initialized

    def init(device_id, shadow_name, gateway_thing, interval_sec)
        self.device_id = device_id
        self.shadow_name = shadow_name
        self.gateway_thing = gateway_thing

        # Initialize sensor state
        self.battery = 100
        self.status = "ok"
        self.vibration_threshold = 5.0
        self.sensitivity = "high"
        self.vibration_level = 0.0
        self.vibration_detected = false
        self.event_count = 0
        self.last_trigger_time = nil
        self.initialized = false

        # Timing
        self.telemetry_interval = interval_sec * 1000
        self.last_telemetry_time = tasmota.millis() + 20000  # First telemetry after 20s (wait for GET response)
        self.start_time = tasmota.millis()

        # Statistics
        self.telemetry_sent = 0
        self.telemetry_confirmed = 0
        self.telemetry_failed = 0
        self.last_stats_time = tasmota.millis()
        self.stats_interval = 300000  # Report stats every 5 minutes

        # MQTT topics
        self.delta_topic = "$aws/things/" + gateway_thing + "/shadow/name/" + shadow_name + "/update/delta"
        self.update_topic = "$aws/things/" + gateway_thing + "/shadow/name/" + shadow_name + "/update"
        self.get_topic = "$aws/things/" + gateway_thing + "/shadow/name/" + shadow_name + "/get"
        self.get_accepted_topic = "$aws/things/" + gateway_thing + "/shadow/name/" + shadow_name + "/get/accepted"
        self.update_accepted_topic = "$aws/things/" + gateway_thing + "/shadow/name/" + shadow_name + "/update/accepted"

        tasmota.log("🔧 Virtual Sensor initialized: " + shadow_name, 2)
        tasmota.log("   Device ID: " + device_id, 2)
    end

    def mqtt_connected()
        # Send GET request to retrieve current shadow state (for reconnection recovery)
        tasmota.log("📡 Sending Shadow GET request for: " + self.shadow_name, 2)
        tasmota.cmd("Publish " + self.get_topic + " ")
        self.initialized = true
    end

    def every_second()
        var now = tasmota.millis()

        # Send GET request once after MQTT is connected (check every second until sent)
        if !self.initialized && now - self.start_time >= 10000
            tasmota.log("📡 Sending Shadow GET request for: " + self.shadow_name, 2)
            tasmota.cmd("Publish " + self.get_topic + " ")
            self.initialized = true
        end

        # Send telemetry at regular intervals
        if now - self.last_telemetry_time >= self.telemetry_interval
            self.generate_and_send_telemetry()
            self.last_telemetry_time = now
        end

        # Report statistics periodically
        if now - self.last_stats_time >= self.stats_interval
            self.report_statistics()
            self.last_stats_time = now
        end
    end

    def generate_and_send_telemetry()
        import math
        import json

        # Simulate vibration level based on sensitivity
        var sensitivity_multiplier = 1.0
        if self.sensitivity == 'high'
            sensitivity_multiplier = 1.5
        elif self.sensitivity == 'low'
            sensitivity_multiplier = 0.5
        end

        # Random vibration (10% chance of strong vibration)
        if math.rand() % 100 < 10
            self.vibration_level = (3.0 + math.rand() % 70 / 10.0) * sensitivity_multiplier
        else
            self.vibration_level = (math.rand() % 30 / 10.0) * sensitivity_multiplier
        end

        # Check threshold
        var previous_state = self.vibration_detected
        self.vibration_detected = self.vibration_level >= self.vibration_threshold

        # Trigger event if state changed
        if self.vibration_detected && !previous_state
            self.event_count += 1
            self.last_trigger_time = tasmota.rtc()['local']
            tasmota.log("⚠️ Vibration detected! Level: " + str(self.vibration_level) + " (Threshold: " + str(self.vibration_threshold) + ")", 2)
        end

        # Battery drain (slower: every 10 telemetry cycles)
        if math.rand() % 10 == 0 && self.battery > 0
            self.battery -= 1
        end

        # Build telemetry payload (matching Python structure EXACTLY)
        var telemetry = {
            'deviceId': self.device_id,              # CRITICAL: deviceId for APP to identify device
            'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',  # Gateway device ID
            'battery': self.battery,
            'status': self.status,
            'vibration_detected': self.vibration_detected,
            'vibration_level': self.vibration_level,
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time,
            'timestamp': tasmota.rtc()['local']
        }

        # Update shadow reported state
        self.update_shadow_reported(telemetry, false)
        self.telemetry_sent += 1
    end

    def update_shadow_reported(reported, clear_desired)
        import json

        var payload = nil

        if clear_desired
            # Clear desired state to prevent delta loop
            payload = json.dump({
                'state': {
                    'reported': reported,
                    'desired': nil  # This clears the desired state
                }
            })
        else
            payload = json.dump({
                'state': {
                    'reported': reported
                }
            })
        end

        tasmota.cmd("Publish " + self.update_topic + " " + payload)
        tasmota.log("📤 Telemetry: vibration=" + str(reported['vibration_level']) + ", events=" + str(reported['event_count']), 2)
    end

    def mqtt_data(topic, idx, payload_s, payload_b)
        import json

        # Handle Shadow GET response (initial state sync)
        if topic == self.get_accepted_topic
            tasmota.log("📥 Shadow GET response received", 2)
            var shadow = json.load(payload_s)

            if shadow != nil
                var state = shadow.find('state')
                if state != nil
                    var desired = state.find('desired')
                    var reported = state.find('reported')

                    # Check for pending commands
                    if desired != nil && reported != nil
                        var desired_req_id = desired.find('reqId')
                        var reported_req_id = reported.find('lastAckedReqId')

                        if desired_req_id != nil && desired_req_id != reported_req_id
                            tasmota.log("📋 Found pending command: " + desired_req_id, 2)
                            var cmd = desired.find('cmd')
                            if cmd != nil
                                self.execute_command(desired_req_id, cmd)
                            end
                        end
                    end
                end
            end
            return true
        end

        # Handle Shadow Update Accepted (confirmation)
        if topic == self.update_accepted_topic
            tasmota.log("✅ Shadow update confirmed", 3)  # Debug level
            self.telemetry_confirmed += 1
            return true
        end

        # Handle Shadow Delta (command from AWS IoT)
        if topic == self.delta_topic
            tasmota.log("📩 Delta received for " + self.shadow_name, 2)

            var delta = json.load(payload_s)

            if delta == nil
                tasmota.log("⚠️ Invalid JSON in delta", 2)
                return true
            end

            # Extract command and reqId
            var state = delta.find('state')
            if state == nil
                return true
            end

            var cmd = state.find('cmd')
            var req_id = state.find('reqId')

            if cmd == nil || req_id == nil
                tasmota.log("⚠️ Missing cmd or reqId in delta", 2)
                return true
            end

            tasmota.log("🎯 Command: " + str(cmd) + " (reqId=" + req_id + ")", 2)

            # Execute command
            self.execute_command(req_id, cmd)
            return true
        end

        return false
    end

    def execute_command(req_id, cmd)
        import json

        var action = cmd.find('action')
        if action == nil
            action = 'unknown'
        end

        tasmota.log("⚙️ Command received: " + action + " (reqId=" + req_id + ")", 2)

        # Apply command updates to internal state (simplified)
        var new_threshold = cmd.find('vibration_threshold')
        if new_threshold != nil
            self.vibration_threshold = new_threshold
        end

        var new_sensitivity = cmd.find('sensitivity')
        if new_sensitivity != nil
            self.sensitivity = new_sensitivity
        end

        if action == 'reset_counter'
            self.event_count = 0
            self.last_trigger_time = nil
        end

        # Send ACK with COMPLETE state (including all telemetry fields)
        var result = {
            'deviceId': self.device_id,
            'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
            'lastAckedReqId': req_id,
            'battery': self.battery,
            'status': self.status,
            'vibration_detected': self.vibration_detected,
            'vibration_level': self.vibration_level,
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time,
            'timestamp': tasmota.rtc()['local']
        }

        self.update_shadow_reported(result, true)  # Clear desired state
        tasmota.log("✅ Command ACK sent: " + action, 2)
    end

    def send_error(req_id, error_code, error_msg)
        import json

        var error_report = {
            'lastError': {
                'reqId': req_id,
                'code': error_code,
                'message': error_msg
            }
        }

        self.update_shadow_reported(error_report)
        tasmota.log("❌ Error: " + error_code + " - " + error_msg, 2)
    end

    def report_statistics()
        var success_rate = 0.0
        if self.telemetry_sent > 0
            success_rate = (self.telemetry_confirmed * 100.0) / self.telemetry_sent
        end

        var uptime_sec = (tasmota.millis() - self.start_time) / 1000
        var uptime_min = uptime_sec / 60

        tasmota.log("==========================================", 2)
        tasmota.log("📊 Communication Statistics Report", 2)
        tasmota.log("==========================================", 2)
        tasmota.log("⏱️  Uptime: " + str(uptime_min) + " minutes", 2)
        tasmota.log("📤 Telemetry Sent: " + str(self.telemetry_sent), 2)
        tasmota.log("✅ Confirmed: " + str(self.telemetry_confirmed), 2)
        tasmota.log("❌ Failed: " + str(self.telemetry_failed), 2)
        tasmota.log("📈 Success Rate: " + str(success_rate) + "%", 2)
        tasmota.log("==========================================", 2)
    end
end

# Initialize virtual sensor
var sensor = VirtualVibrationSensor(
    VIRTUAL_DEVICE['device_id'],
    VIRTUAL_DEVICE['shadow_name'],
    GATEWAY_THING,
    10  # 10 seconds telemetry interval for stability testing
)
tasmota.add_driver(sensor)

tasmota.log("🚀 BLE Gateway - Communication Stability Test", 2)
tasmota.log("📡 Gateway Thing: " + GATEWAY_THING, 2)
tasmota.log("🔌 Virtual Device: " + VIRTUAL_DEVICE['shadow_name'], 2)
tasmota.log("   Device ID: " + VIRTUAL_DEVICE['device_id'], 2)
tasmota.log("📤 Telemetry interval: 10 seconds", 2)
tasmota.log("📊 Statistics report: Every 5 minutes", 2)
tasmota.log("📥 Command handling: Simplified (ACK only)", 2)
tasmota.log("==========================================", 2)
