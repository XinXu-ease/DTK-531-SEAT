const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const os = require('os');

let petWindow;
let dashboardWindow;

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
