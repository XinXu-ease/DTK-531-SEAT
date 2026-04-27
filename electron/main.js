const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const os = require('os');
const mqtt = require('mqtt');

let petWindow;
let dashboardWindow;
let mqttClient;
let latestMqttData = {
  sensors: null,
  user: null
};

// 初始化 MQTT 连接（连接到树莓派本地 broker）
function initMQTT() {
  console.log('[Electron] Connecting to MQTT broker at 172.20.4.137:1883...');
  
  mqttClient = mqtt.connect('mqtt://172.20.4.137:1883', {
    clientId: 'electron-chair-' + Date.now(),
    reconnectPeriod: 3000,
    connectTimeout: 10000
  });

  mqttClient.on('connect', () => {
    console.log('[Electron] MQTT Connected');
    mqttClient.subscribe('chair/sensors', { qos: 1 });
    mqttClient.subscribe('chair/user', { qos: 1 });
    
    // 通知所有窗口 MQTT 已连接
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('mqtt-status', { connected: true });
    }
    if (dashboardWindow && !dashboardWindow.isDestroyed()) {
      dashboardWindow.webContents.send('mqtt-status', { connected: true });
    }
  });

  mqttClient.on('message', (topic, message) => {
    try {
      const payload = JSON.parse(message.toString());
      
      if (topic === 'chair/sensors') {
        latestMqttData.sensors = payload;
        // 实时推送给前端
        if (petWindow && !petWindow.isDestroyed()) {
          petWindow.webContents.send('mqtt-data', { topic, payload });
        }
        if (dashboardWindow && !dashboardWindow.isDestroyed()) {
          dashboardWindow.webContents.send('mqtt-data', { topic, payload });
        }
      } else if (topic === 'chair/user') {
        latestMqttData.user = payload;
        if (petWindow && !petWindow.isDestroyed()) {
          petWindow.webContents.send('mqtt-data', { topic, payload });
        }
        if (dashboardWindow && !dashboardWindow.isDestroyed()) {
          dashboardWindow.webContents.send('mqtt-data', { topic, payload });
        }
      }
    } catch (err) {
      console.error('[Electron] MQTT message parse error:', err);
    }
  });

  mqttClient.on('error', (error) => {
    console.error('[Electron] MQTT Error:', error);
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('mqtt-status', { connected: false });
    }
    if (dashboardWindow && !dashboardWindow.isDestroyed()) {
      dashboardWindow.webContents.send('mqtt-status', { connected: false });
    }
  });

  mqttClient.on('disconnect', () => {
    console.log('[Electron] MQTT Disconnected');
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('mqtt-status', { connected: false });
    }
    if (dashboardWindow && !dashboardWindow.isDestroyed()) {
      dashboardWindow.webContents.send('mqtt-status', { connected: false });
    }
  });
}

// 发布消息到 MQTT
ipcMain.handle('mqtt-publish', async (event, topic, payload) => {
  if (mqttClient) {
    mqttClient.publish(topic, JSON.stringify(payload), { qos: 1 });
    return { success: true };
  }
  return { success: false, error: 'MQTT not connected' };
});

// 创建桌宠浮窗
function createPetWindow() {
  petWindow = new BrowserWindow({
    width: 150,                        /* 够容纳 emoji */
    height: 150,
    x: 100,
    y: 100,
    frame: false,                          // 无边框
    transparent: true,                     // 透明背景
    alwaysOnTop: true,                     // 始终在顶部
    skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false
    }
  });

  petWindow.loadFile(path.join(__dirname, 'src', 'pet', 'pet.html'));

  // 如果不在生产环境，打开开发工具
  // petWindow.webContents.openDevTools();

  petWindow.on('closed', () => {
    petWindow = null;
  });
}

// 创建仪表板窗口
function createDashboardWindow() {
  if (dashboardWindow) {
    dashboardWindow.focus();
    return;
  }

  dashboardWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false
    }
  });

  dashboardWindow.loadFile(path.join(__dirname, 'src', 'dashboard', 'dashboard.html'));

  // dashboardWindow.webContents.openDevTools();

  dashboardWindow.on('closed', () => {
    dashboardWindow = null;
  });
}

// 应用启动
app.on('ready', () => {
  createPetWindow();
  initMQTT();  // 初始化 MQTT 连接
});

// 来自 pet.js 的 IPC 事件：打开仪表板
ipcMain.on('open-dashboard', () => {
  createDashboardWindow();
});

// 来自 pet.js 的 IPC 事件：获取窗口位置（同步）
ipcMain.on('get-pet-window-position', (event) => {
  if (petWindow) {
    const [x, y] = petWindow.getPosition();
    event.returnValue = { x, y };
  } else {
    event.returnValue = { x: 0, y: 0 };
  }
});

// 来自 pet.js 的 IPC 事件：设置窗口位置
ipcMain.on('set-pet-window-position', (event, x, y) => {
  if (petWindow) {
    petWindow.setPosition(Math.round(x), Math.round(y));
  }
});

// 来自 dashboard.js 的 IPC 事件：关闭应用
ipcMain.on('close-app', () => {
  app.quit();
});

// 来自 dashboard.js 的 IPC 事件：获取 LLM 建议
ipcMain.handle('get-llm-advice', async (event, userID) => {
  return new Promise((resolve, reject) => {
    const pythonBinary = os.platform() === 'win32' ? 'python' : 'python3';
    const pythonScript = path.join(__dirname, 'llm_advice_handler.py');
    
    const process = spawn(pythonBinary, [pythonScript, userID]);
    
    let stdout = '';
    let stderr = '';
    
    process.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    
    process.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    
    process.on('close', (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdout);
          resolve(result);
        } catch (err) {
          reject(new Error('Failed to parse Python output: ' + stdout));
        }
      } else {
        reject(new Error('Python script error: ' + stderr));
      }
    });
    
    process.on('error', (err) => {
      reject(new Error('Failed to spawn Python process: ' + err.message));
    });
  });
});

// 所有窗口关闭时退出应用
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (petWindow === null) {
    createPetWindow();
  }
});
