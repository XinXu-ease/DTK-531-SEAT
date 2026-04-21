// 全局状态
let currentState = {
  userID: null,
  timeSit: 0,
  timeBlc: 0,
  blcBad: 0,
  seattype: 0,
  normValues: [0, 0, 0, 0],
  mqttConnected: false,
  lastUpdateTime: null
};

let updateInterval = null;

// 初始化
window.addEventListener('DOMContentLoaded', () => {
  console.log('[Pet] Initializing...');
  
  // 从 localStorage 获取 userID
  const savedUserID = localStorage.getItem('userID');
  if (savedUserID) {
    currentState.userID = savedUserID;
    updateBubbleDisplay();
  }

  // 初始化表情
  updateEmoji();

  // 事件监听
  document.getElementById('dashboardBtn').addEventListener('click', openDashboard);
  document.getElementById('minimizeBtn').addEventListener('click', minimizeWindow);
  
  // 在 document 上全局监听 mousemove 来检测 hover
  document.addEventListener('mousemove', (e) => {
    const emoji = document.getElementById('emojiDisplay');
    const emojiRect = emoji.getBoundingClientRect();
    
    // 鼠标在 emoji 范围内
    if (e.clientX >= emojiRect.left && e.clientX <= emojiRect.right &&
        e.clientY >= emojiRect.top && e.clientY <= emojiRect.bottom) {
      showBubble();
    }
  });
  
  // 在容器上监听 mouseleave 隐藏气泡
  const petContainer = document.getElementById('petContainer');
  petContainer.addEventListener('mouseleave', hideBubble);
  
  // 只有点击气泡才打开 dashboard
  document.getElementById('bubble').addEventListener('click', openDashboard);

  // 监听来自主进程的 MQTT 数据
  window.electronAPI.onMQTTData((event, { topic, payload }) => {
    try {
      if (topic === 'chair/sensors') {
        handleSensorData(payload);
      } else if (topic === 'chair/user') {
        handleUserData(payload);
      }
    } catch (e) {
      console.error('[Pet] Error handling MQTT data:', e);
    }
  });

  // 监听 MQTT 连接状态
  window.electronAPI.onMQTTStatus((event, { connected }) => {
    console.log('[Pet] MQTT Status:', connected ? 'Connected' : 'Disconnected');
    currentState.mqttConnected = connected;
    updateMQTTStatus(connected);
  });

  // 定期检查超时
  setInterval(checkTimeout, 1000);
});

// 处理传感器数据
function handleSensorData(payload) {
  currentState.timeSit = payload.time_sit || 0;
  currentState.timeBlc = payload.time_blc || 0;
  currentState.blcBad = payload.blc_bad || 0;
  currentState.seattype = payload.seattype || 0;
  currentState.normValues = payload.norm_values || [0, 0, 0, 0];
  currentState.lastUpdateTime = Date.now();

  // 更新 emoji
  updateEmoji();
  // 更新气泡
  updateBubbleDisplay();
  // 更新小数据显示
  updateDataDisplay();
}

// 处理用户数据
function handleUserData(payload) {
  if (payload.user_id) {
    currentState.userID = payload.user_id;
    localStorage.setItem('userID', payload.user_id);
    updateBubbleDisplay();
  }
}

// 更新 Emoji
function getEmojiByTimeSit(timeSit) {
  if (timeSit === 0) return '😴';
  if (timeSit < 5) return '😄';
  if (timeSit < 15) return '😐';
  return '😭';
}

function updateEmoji() {
  const newEmoji = getEmojiByTimeSit(currentState.timeSit);
  const emojiDisplay = document.getElementById('emojiDisplay');
  
  if (emojiDisplay.textContent !== newEmoji) {
    emojiDisplay.classList.remove('flip');
    // 触发重排以重启动画
    void emojiDisplay.offsetWidth;
    emojiDisplay.classList.add('flip');
    
    setTimeout(() => {
      emojiDisplay.textContent = newEmoji;
      emojiDisplay.classList.remove('flip');
    }, 300);
  }
}

// 更新气泡信息
function updateBubbleDisplay() {
  // 已改为简单提示，无需更新详细数据
}

// 更新小数据显示
function updateDataDisplay() {
  const display = document.getElementById('dataDisplay');
  const status = currentState.seattype ? '👤 Seated' : '🪑 Empty';
  display.textContent = `${status} | Time: ${currentState.timeSit}s`;
}

// 更新 MQTT 状态指示器
function updateMQTTStatus(connected) {
  const statusDot = document.getElementById('mqttStatus');
  if (connected) {
    statusDot.classList.remove('disconnected');
    statusDot.classList.add('connected');
    statusDot.textContent = '🟢';
  } else {
    statusDot.classList.remove('connected');
    statusDot.classList.add('disconnected');
    statusDot.textContent = '🔴';
  }
}

// 检查超时（5秒无数据则重置）
function checkTimeout() {
  if (currentState.lastUpdateTime && Date.now() - currentState.lastUpdateTime > 5000) {
    currentState.timeSit = 0;
    currentState.seattype = 0;
    currentState.normValues = [0, 0, 0, 0];
    currentState.lastUpdateTime = null;
    updateEmoji();
    updateDataDisplay();
  }
}

// 显示气泡
function showBubble() {
  clearTimeout(window.hideBubbleTimeout);
  document.getElementById('bubble').classList.add('show');
}

// 隐藏气泡（带延迟）
function hideBubbleWithDelay() {
  window.hideBubbleTimeout = setTimeout(() => {
    document.getElementById('bubble').classList.remove('show');
  }, 100);
}

// 隐藏气泡（立即）
function hideBubble() {
  clearTimeout(window.hideBubbleTimeout);
  document.getElementById('bubble').classList.remove('show');
}

// 打开仪表板
function openDashboard() {
  if (window.electronAPI) {
    window.electronAPI.openDashboard();
  }
}

// 最小化窗口（在 Electron 中实现）
function minimizeWindow() {
  // Electron 会通过 IPC 处理这个（暂时不实现）
  console.log('[Pet] Minimize clicked');
}
