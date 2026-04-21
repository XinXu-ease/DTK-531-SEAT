// 全局状态
let currentState = {
  userID: null,
  timeSit: 0,
  timeBlc: 0,
  blcBad: 0,
  seattype: 0,
  normValues: [0, 0, 0, 0],
  rawValues: [0, 0, 0, 0],
  mqttConnected: false,
  lastUpdateTime: null
};

// 初始化
window.addEventListener('DOMContentLoaded', () => {
  console.log('[Dashboard] Initializing...');

  // 从 localStorage 获取 userID
  const savedUserID = localStorage.getItem('userID') || '';
  currentState.userID = savedUserID;
  document.getElementById('global-user-id').value = savedUserID;
  updateStatusDisplay();

  // 初始化心情卡片
  updateMoodCard();

  // 事件监听
  document.getElementById('closeBtn').addEventListener('click', closeApp);
  document.getElementById('btn-sync-global-user').addEventListener('click', syncGlobalUserID);
  document.getElementById('btn-logout-user').addEventListener('click', logout);
  document.getElementById('global-user-id').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') syncGlobalUserID();
  });

  // Tab 切换
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      switchTab(e.target.dataset.tab);
    });
  });

  // Calibration 按钮
  document.getElementById('btn-record-0').addEventListener('click', () => startRecording('0'));
  document.getElementById('btn-record-1').addEventListener('click', () => startRecording('1'));

  // Get Advice 按钮
  document.getElementById('btn-get-advice').addEventListener('click', getAdviceFromLLM);

  // 监听来自主进程的 MQTT 数据
  window.electronAPI.onMQTTData((event, { topic, payload }) => {
    try {
      if (topic === 'chair/sensors') {
        handleSensorData(payload);
      } else if (topic === 'chair/user') {
        handleUserData(payload);
      }
    } catch (e) {
      console.error('[Dashboard] Error handling MQTT data:', e);
    }
  });

  // 监听 MQTT 连接状态
  window.electronAPI.onMQTTStatus((event, { connected }) => {
    console.log('[Dashboard] MQTT Status:', connected ? 'Connected' : 'Disconnected');
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
  currentState.rawValues = payload.raw_values || [0, 0, 0, 0];
  currentState.lastUpdateTime = Date.now();

  updateUI();
}

// 处理用户数据
function handleUserData(payload) {
  if (payload.user_id) {
    currentState.userID = payload.user_id;
    localStorage.setItem('userID', payload.user_id);
    document.getElementById('global-user-id').value = payload.user_id;
    updateStatusDisplay();
  }
}

// 更新 UI
function updateUI() {
  updateStatusDisplay();
  updateMoodCard();
  updateStateCards();
  updateMetrics();
  updatePressureBars();
  updateRawData();
}

// 更新状态条
function updateStatusDisplay() {
  // 更新时间
  const now = new Date();
  const timeStr = now.toLocaleTimeString('zh-CN');
  document.getElementById('last-update').textContent = timeStr;

  // 更新用户 ID
  document.getElementById('current-user-id').textContent = currentState.userID || '--';
}

// 更新 MQTT 状态指示器
function updateMQTTStatus(connected) {
  const statusDot = document.getElementById('mqtt-status');
  if (connected) {
    statusDot.textContent = '●';
    statusDot.classList.add('connected');
    statusDot.classList.remove('disconnected');
  } else {
    statusDot.textContent = '●';
    statusDot.classList.add('disconnected');
    statusDot.classList.remove('connected');
  }
}

// 获取 Emoji
function getEmojiByTimeSit(timeSit) {
  if (timeSit === 0) return '😴';
  if (timeSit < 5) return '😄';
  if (timeSit < 15) return '😐';
  return '😭';
}

// 获取心情文本
function getMoodTextByTimeSit(timeSit) {
  if (timeSit === 0) return 'No one sitting';
  if (timeSit < 5) return 'Keep up the good posture!';
  if (timeSit < 15) return 'You have been sitting for a while...';
  return 'Time to take a break!';
}

// 更新心情卡片
function updateMoodCard() {
  const emoji = getEmojiByTimeSit(currentState.timeSit);
  const moodEmoji = document.getElementById('mood-emoji');
  const moodText = document.getElementById('mood-text');

  if (moodEmoji.textContent !== emoji) {
    moodEmoji.style.animation = 'none';
    setTimeout(() => {
      moodEmoji.style.animation = 'bounce-mood 1s infinite';
    }, 10);
  }

  moodEmoji.textContent = emoji;
  moodText.textContent = getMoodTextByTimeSit(currentState.timeSit);
}

// 更新状态卡片
function updateStateCards() {
  document.getElementById('seated-state').textContent = currentState.seattype ? '👤 Seated' : '🪑 Empty';
  document.getElementById('seated-state').style.color = currentState.seattype ? '#4CAF50' : '#f44336';

  const balanceText = currentState.blcBad ? '❌ Unbalanced' : '✓ Balanced';
  document.getElementById('balance-state').textContent = balanceText;
  document.getElementById('balance-state').style.color = currentState.blcBad ? '#f44336' : '#4CAF50';

  document.getElementById('time-sit-display').textContent = currentState.timeSit + 's';
}

// 更新指标
function updateMetrics() {
  document.getElementById('time-sit').textContent = currentState.timeSit;
  document.getElementById('time-blc').textContent = currentState.timeBlc;
}

// 更新压力柱
function updatePressureBars() {
  const total = currentState.normValues.reduce((a, b) => a + b, 0) || 1;
  const bars = ['fl', 'fr', 'bl', 'br'];

  bars.forEach((bar, idx) => {
    const percentage = Math.round((currentState.normValues[idx] / total) * 100);
    document.getElementById(`pressure-${bar}`).style.width = percentage + '%';
  });
}

// 更新原始数据
function updateRawData() {
  const displayData = {
    timestamp: new Date(currentState.lastUpdateTime || Date.now()).toISOString(),
    user_id: currentState.userID || 'not_set',
    seattype: currentState.seattype ? 'Seated' : 'Empty',
    raw_values: currentState.rawValues,
    norm_values: currentState.normValues,
    blc_bad: currentState.blcBad,
    time_sit: currentState.timeSit,
    time_blc: currentState.timeBlc,
    mqtt_connected: currentState.mqttConnected
  };

  document.getElementById('raw-data-display').textContent = JSON.stringify(displayData, null, 2);
}

// 检查超时（5秒无数据则重置）
function checkTimeout() {
  if (currentState.lastUpdateTime && Date.now() - currentState.lastUpdateTime > 5000) {
    currentState.timeSit = 0;
    currentState.seattype = 0;
    currentState.normValues = [0, 0, 0, 0];
    currentState.lastUpdateTime = null;
    updateUI();
  }
}

// 同步全局用户 ID
function syncGlobalUserID() {
  const userID = document.getElementById('global-user-id').value.trim();
  if (!userID) {
    showSyncStatus('Please enter a user ID', 'error');
    return;
  }

  currentState.userID = userID;
  localStorage.setItem('userID', userID);

  // 发布到 MQTT：同时开启 recording 模式
  if (currentState.mqttConnected) {
    window.electronAPI.publishMQTT('chair/user', { 
      user_id: userID,
      recording: true
    }).then(() => {
      console.log('[Dashboard] User ID synced to MQTT');
    }).catch(err => {
      console.error('[Dashboard] Failed to publish user ID:', err);
    });
  }

  updateStatusDisplay();
  showSyncStatus('✓ Synced & Recording Started', 'success');
}

// 登出用户并停止记录
function logout() {
  const currentUserID = currentState.userID;
  
  if (!currentUserID) {
    showSyncStatus('No user logged in', 'error');
    return;
  }

  // 清除本地状态
  currentState.userID = null;
  localStorage.removeItem('userID');
  document.getElementById('global-user-id').value = '';

  // 发布到 MQTT：关闭 recording 模式
  if (currentState.mqttConnected) {
    window.electronAPI.publishMQTT('chair/user', { 
      user_id: null,
      recording: false
    }).then(() => {
      console.log('[Dashboard] User logged out in MQTT');
    }).catch(err => {
      console.error('[Dashboard] Failed to publish logout:', err);
    });
  }

  updateStatusDisplay();
  showSyncStatus('✓ Logged Out & Recording Stopped', 'success');
}

// 显示同步状态
function showSyncStatus(message, type) {
  const status = document.getElementById('user-sync-status');
  status.textContent = message;
  status.className = 'sync-status ' + type;

  if (type === 'success') {
    setTimeout(() => {
      status.textContent = '';
      status.className = 'sync-status';
    }, 2000);
  }
}

// 启动录制
function startRecording(label) {
  const userID = currentState.userID || '';
  const duration = parseInt(document.getElementById('duration-input').value) || 30;

  if (!userID) {
    showCalibrationStatus('Please sync user ID from main interface first', 'error');
    return;
  }

  if (!currentState.mqttConnected) {
    showCalibrationStatus('MQTT not connected', 'error');
    return;
  }

  // 发布录制命令
  const command = {
    user_id: userID,
    recording: true,
    label: label,
    duration: duration
  };

  window.electronAPI.publishMQTT('chair/user', command).then(() => {
    const labelName = label === '0' ? 'Balanced' : 'Unbalanced';
    showCalibrationStatus(`Started recording ${labelName} for ${duration}s...`, 'success');

    // 自动停止（持续时间后）
    setTimeout(() => {
      const stopCommand = {
        user_id: userID,
        recording: false
      };
      window.electronAPI.publishMQTT('chair/user', stopCommand).then(() => {
        showCalibrationStatus(`✓ Recording completed for ${labelName}`, 'success');
      });
    }, duration * 1000);
  }).catch(err => {
    console.error('[Dashboard] Failed to start recording:', err);
    showCalibrationStatus('Failed to start recording', 'error');
  });
}

// 显示校准状态
function showCalibrationStatus(message, type) {
  const status = document.getElementById('calibration-status');
  status.textContent = message;
  status.className = 'calibration-status ' + type;
}

// 切换标签页
function switchTab(tabName) {
  // 隐藏所有标签页
  document.querySelectorAll('.tab-content').forEach(tab => {
    tab.classList.remove('active');
  });

  // 移除所有按钮的活跃状态
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });

  // 显示选择的标签页
  document.getElementById(tabName).classList.add('active');

  // 标记对应按钮为活跃
  document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
}

// 关闭应用
function closeApp() {
  if (window.electronAPI) {
    window.electronAPI.closeApp();
  }
}

// 获取 LLM 建议
async function getAdviceFromLLM() {
  const userID = currentState.userID || document.getElementById('global-user-id').value;
  
  if (!userID) {
    showAdviceStatus('Please set user ID first', 'error');
    return;
  }

  // 显示加载状态
  const statusEl = document.getElementById('advice-status');
  const displayEl = document.getElementById('advice-display');
  const contentEl = document.getElementById('advice-content');
  const btnEl = document.getElementById('btn-get-advice');
  
  statusEl.style.display = 'block';
  statusEl.className = 'advice-status loading';
  statusEl.textContent = 'Loading...';
  displayEl.style.display = 'none';
  btnEl.disabled = true;

  try {
    // 通过 IPC 调用 Python llm_utils.generate_llm_advice
    const result = await window.electronAPI.getLLMAdvice(userID);

    if (!result.success) {
      showAdviceStatus(`LLM Error: ${result.error}`, 'error');
      displayEl.style.display = 'none';
      return;
    }

    const advice = result.advice || 'No advice received';

    // 显示建议
    contentEl.textContent = advice;
    displayEl.style.display = 'block';
    statusEl.style.display = 'none';
  } catch (error) {
    console.error('Error getting advice:', error);
    showAdviceStatus(`Failed to get LLM advice: ${error.message}`, 'error');
    displayEl.style.display = 'none';
  } finally {
    btnEl.disabled = false;
  }
}


// 显示建议状态
function showAdviceStatus(message, type) {
  const statusEl = document.getElementById('advice-status');
  statusEl.textContent = message;
  statusEl.className = 'advice-status ' + type;
  statusEl.style.display = 'block';
}
