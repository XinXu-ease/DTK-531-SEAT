const { contextBridge, ipcRenderer } = require('electron');

// 暴露 IPC 通道给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  openDashboard: () => ipcRenderer.send('open-dashboard'),
  getPetWindowPosition: () => ipcRenderer.sendSync('get-pet-window-position'),
  setPetWindowPosition: (x, y) => ipcRenderer.send('set-pet-window-position', x, y),
  closeApp: () => ipcRenderer.send('close-app'),
  
  // 获取 LLM 建议
  getLLMAdvice: (userID) => ipcRenderer.invoke('get-llm-advice', userID),
  
  // 监听来自主进程的消息
  onPetShownInTaskbar: (callback) => ipcRenderer.on('pet-shown-in-taskbar', callback),
  onDashboardClosed: (callback) => ipcRenderer.on('dashboard-closed', callback)
});

// 暴露 localStorage（虽然浏览器已有，但这样更安全）
contextBridge.exposeInMainWorld('storageAPI', {
  getUserID: () => localStorage.getItem('userID'),
  setUserID: (id) => localStorage.setItem('userID', id),
  clearUserID: () => localStorage.removeItem('userID')
});
