import paho.mqtt.client as mqtt

class MQTTClient:
    def __init__(self, code):
        self.broker = "broker.hivemq.com"
        self.port = 1883
        self.topic = f"screenshot/sharing/{code}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def connect(self):
        def on_connect(client, userdata, flags, rc, properties=None):
            print("[MQTT] Connected successfully")

        self.client.on_connect = on_connect
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def send_image(self, base64_image, retain=True):
        payload = f"data:image/jpeg;base64,{base64_image}"
        result = self.client.publish(self.topic, payload, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Screenshot published successfully (retain={'true' if retain else 'false'})")
        else:
            print(f"[MQTT] Failed to publish message, rc={result.rc}")