const mqtt = require('mqtt');

class MQTTClient {
  constructor() {
    this.client = null;
    this.isConnected = false;
    this.callbacks = {
      onConnect: null,
      onDisconnect: null,
      onMessage: null,
      onError: null
    };
  }

  // 连接到 MQTT broker
  connect(brokerURL = 'mqtt://test.mosquitto.org:1883') {
    return new Promise((resolve, reject) => {
      try {
        this.client = mqtt.connect(brokerURL, {
          reconnectPeriod: 1000,
          connectTimeout: 10000
        });

        this.client.on('connect', () => {
          this.isConnected = true;
          console.log('[MQTT] Connected to broker');
          if (this.callbacks.onConnect) {
            this.callbacks.onConnect();
          }
          resolve();
        });

        this.client.on('disconnect', () => {
          this.isConnected = false;
          console.log('[MQTT] Disconnected from broker');
          if (this.callbacks.onDisconnect) {
            this.callbacks.onDisconnect();
          }
        });

        this.client.on('message', (topic, message) => {
          try {
            const payload = JSON.parse(message.toString());
            if (this.callbacks.onMessage) {
              this.callbacks.onMessage(topic, payload);
            }
          } catch (e) {
            console.error('[MQTT] Failed to parse message:', e);
          }
        });

        this.client.on('error', (error) => {
          console.error('[MQTT] Error:', error);
          if (this.callbacks.onError) {
            this.callbacks.onError(error);
          }
          reject(error);
        });
      } catch (e) {
        reject(e);
      }
    });
  }

  // 订阅主题
  subscribe(topic) {
    if (this.isConnected) {
      this.client.subscribe(topic, (err) => {
        if (err) {
          console.error(`[MQTT] Failed to subscribe to ${topic}:`, err);
        } else {
          console.log(`[MQTT] Subscribed to ${topic}`);
        }
      });
    }
  }

  // 发布消息
  publish(topic, message) {
    if (this.isConnected) {
      this.client.publish(topic, JSON.stringify(message), (err) => {
        if (err) {
          console.error(`[MQTT] Failed to publish to ${topic}:`, err);
        } else {
          console.log(`[MQTT] Published to ${topic}`);
        }
      });
    }
  }

  // 注册回调
  on(event, callback) {
    if (this.callbacks.hasOwnProperty(event)) {
      this.callbacks[event] = callback;
    }
  }

  // 断开连接
  disconnect() {
    if (this.client) {
      this.client.end();
    }
  }
}

// 导出单例
module.exports = new MQTTClient();
