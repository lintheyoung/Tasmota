# AWS IoT Stability Test - autoexec.be v5.2.0
# Purpose: Minimal configuration to avoid restart loops

var SCRIPT_VERSION = "5.2.0"
var DEVICE_ID = "IoT-Gateway-000011"
var MQTT_ENDPOINT = "a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com"

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

# ============================================================
# MQTT Stability Monitor - Simplified
# ============================================================

class MQTTStabilityMonitor
    var test_interval
    var message_count
    var last_publish_time
    var start_time

    def init(interval_sec)
        self.test_interval = interval_sec * 1000
        self.message_count = 0
        self.last_publish_time = tasmota.millis() + 15000  # First message after 15s
        self.start_time = tasmota.millis()
        tasmota.log("Stability Monitor started (30s interval)", 2)
    end

    def every_second()
        var now = tasmota.millis()

        if now - self.last_publish_time >= self.test_interval
            self.send_message()
            self.last_publish_time = now
        end
    end

    def send_message()
        self.message_count += 1
        var uptime = (tasmota.millis() - self.start_time) / 1000

        import json
        var payload = json.dump({
            "msg": self.message_count,
            "uptime": uptime
        })

        tasmota.cmd("Publish test/stability/" + DEVICE_ID + " " + payload)
        tasmota.log("📤 #" + str(self.message_count) + " @" + str(uptime) + "s", 2)

        if self.message_count % 10 == 0
            tasmota.log("📊 Stats: " + str(self.message_count) + " messages, " + str(uptime/60) + " min uptime", 2)
        end
    end
end

var monitor = MQTTStabilityMonitor(30)
tasmota.add_driver(monitor)

tasmota.log("🚀 Monitoring started - first message in 15s", 2)
tasmota.log("==========================================", 2)
