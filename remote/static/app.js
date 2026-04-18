/* WebSocket & Real-time Update Logic */

// Initialize Socket.IO connection
const socket = io();

// UI Elements
const mqttStatus = document.getElementById('mqtt-status');
const wsStatus = document.getElementById('ws-status');
const lastUpdate = document.getElementById('last-update');

const seatedIcon = document.getElementById('seated-icon');
const seatedText = document.getElementById('seated-text');
const balanceIcon = document.getElementById('balance-icon');
const balanceText = document.getElementById('balance-text');
const vibrationIcon = document.getElementById('vibration-icon');
const vibrationText = document.getElementById('vibration-text');
const vibrationCard = document.getElementById('vibration-card');

const timeSit = document.getElementById('time-sit');
const timeSitMin = document.getElementById('time-sit-min');
const timeBlc = document.getElementById('time-blc');
const timeBlcMin = document.getElementById('time-blc-min');

const sensorValues = ['sensor-0', 'sensor-1', 'sensor-2', 'sensor-3'];
const sensorValText = ['sensor-0-val', 'sensor-1-val', 'sensor-2-val', 'sensor-3-val'];

const rawDataDisplay = document.getElementById('raw-data');

const moodEmoji = document.getElementById('mood-emoji');
const moodStatus = document.getElementById('mood-status');

// ============ UI Elements - Calibration ============
const userIdInput = document.getElementById('user-id-input');
const btnSyncUser = document.getElementById('btn-sync-user');
const calibDuration = document.getElementById('calib-duration');
const btnRecordBalanced = document.getElementById('btn-record-balanced');
const btnRecordUnbalanced = document.getElementById('btn-record-unbalanced');
const calibMessage = document.getElementById('calib-message');
const currentUserIdSpan = document.getElementById('current-user-id');

// ============ UI Elements - Global User ID ============
const globalUserIdInput = document.getElementById('global-user-id');
const btnSyncGlobalUser = document.getElementById('btn-sync-global-user');
const userSyncStatus = document.getElementById('user-sync-status')

// ============ Signal Timeout Configuration ============
const SIGNAL_TIMEOUT = 5000; // 5秒无信号后重置UI
let lastDataReceivedTime = Date.now();
let signalTimeoutCheck = null;
let currentUserId = '';

// ============ WebSocket Events ============
socket.on('connect', () => {
    console.log('[WebSocket] Connected');
    updateConnectionStatus('ws', true);
    lastDataReceivedTime = Date.now();
    startSignalTimeoutCheck();
});

socket.on('disconnect', () => {
    console.log('[WebSocket] Disconnected');
    updateConnectionStatus('ws', false);
    resetAllUI();
    stopSignalTimeoutCheck();
});

socket.on('chair_data', (data) => {
    console.log('[Update] Received data:', data);
    lastDataReceivedTime = Date.now();
    updateConnectionStatus('mqtt', true);
    updateUI(data);
    updateLastUpdateTime();
});

socket.on('mqtt_status', (status) => {
    console.log('[MQTT Status] Update:', status.status);
    const isConnected = status.status === 'connected';
    updateConnectionStatus('mqtt', isConnected);
});

socket.on('user_id_synced', (result) => {
    /**
     * Handle user ID sync response
     */
    if (result.status === 'success') {
        console.log('[User ID] Synced:', result.user_id);
        showCalibMessage(`✓ User ID synced: ${result.user_id}`, 'success');
    } else {
        console.error('[User ID] Sync failed:', result.message);
        showCalibMessage(`✗ Error: ${result.message}`, 'error');
    }
});

socket.on('calibration_status', (result) => {
    /**
     * Handle calibration response
     */
    if (result.status === 'started') {
        const labelText = result.label === 0 ? 'Balanced (Label 0)' : 'Unbalanced (Label 1)';
        console.log('[Calibration] Recording started:', labelText);
        showCalibMessage(`✓ Recording ${labelText}...`, 'success');
    } else if (result.status === 'error') {
        console.error('[Calibration] Error:', result.message);
        showCalibMessage(`✗ Calibration error: ${result.message}`, 'error');
    }
});

// ============ Connection Status ============
function updateConnectionStatus(type, connected) {
    const element = type === 'ws' ? wsStatus : mqttStatus;
    if (connected) {
        element.textContent = '●';
        element.classList.remove('disconnected');
        element.classList.add('connected');
        element.style.opacity = '1';
    } else {
        element.textContent = '●';
        element.classList.remove('connected');
        element.classList.add('disconnected');
        element.style.opacity = '1';
    }
}

function updateLastUpdateTime() {
    const now = new Date();
    const time = now.toLocaleTimeString('zh-CN');
    lastUpdate.textContent = time;
}

// ============ Signal Timeout Detection ============
function startSignalTimeoutCheck() {
    /**
     * 启动超时检查：如果超过SIGNAL_TIMEOUT毫秒没收到信号，重置UI
     */
    stopSignalTimeoutCheck(); // 先停止旧的检查
    
    signalTimeoutCheck = setInterval(() => {
        const timeSinceLastUpdate = Date.now() - lastDataReceivedTime;
        
        if (timeSinceLastUpdate > SIGNAL_TIMEOUT) {
            console.warn(`[Timeout] No signal for ${timeSinceLastUpdate}ms, resetting UI...`);
            updateConnectionStatus('mqtt', false);
            resetAllUI();
        }
    }, 1000); // 每秒检查一次
}

function stopSignalTimeoutCheck() {
    /**
     * 停止超时检查
     */
    if (signalTimeoutCheck) {
        clearInterval(signalTimeoutCheck);
        signalTimeoutCheck = null;
    }
}

function resetAllUI() {
    /**
     * 重置所有UI元素到初始状态
     */
    console.log('[Reset] Resetting all UI elements...');
    
    // Reset seating state
    seatedIcon.textContent = '🪑';
    seatedText.textContent = 'No Signal';
    seatedText.style.color = '#999';
    
    // Reset balance state
    balanceIcon.textContent = '❓';
    balanceText.textContent = 'Waiting...';
    balanceText.style.color = '#999';
    
    // Reset vibration state
    vibrationIcon.classList.remove('pulse');
    vibrationText.textContent = 'Disconnected';
    vibrationText.style.color = '#f44336';
    
    // Reset mood emoji
    moodEmoji.textContent = '🙁';
    moodEmoji.style.animation = 'none';
    moodStatus.textContent = 'Waiting for signal...';
    moodStatus.style.color = '#f44336';
    
    // Reset time metrics
    timeSit.textContent = '--';
    timeSitMin.textContent = '--';
    timeBlc.textContent = '--';
    timeBlcMin.textContent = '--';
    
    // Reset sensor bars
    sensorValues.forEach((sensorId, index) => {
        const bar = document.getElementById(sensorId);
        const valText = document.getElementById(sensorValText[index]);
        if (bar) bar.style.height = '0%';
        if (valText) valText.textContent = '--';
    });
    
    // Reset raw data display
    rawDataDisplay.textContent = JSON.stringify({
        status: 'Waiting for signal...',
        message: 'No data received from MQTT broker'
    }, null, 2);
    
    lastUpdate.textContent = '--:--:--';
}

// ============ UI Update Function ============
function updateUI(data) {
    // Update seated state
    const isSeated = data.seattype === true || data.seattype === 1;
    updateSeatedState(isSeated);

    // Update balance state
    const isBadBalance = data.blc_bad === true || data.blc_bad === 1;
    updateBalanceState(isBadBalance, isSeated);

    // Update vibration state
    const shouldVibrate = data.should_vibrate === true || data.should_vibrate === 1;
    updateVibrationState(shouldVibrate);

    // Update time metrics
    updateTimeMetrics(data.time_sit, data.time_blc);

    // Update sensor bars
    updateSensorBars(data.norm_values);

    // Update raw data display
    updateRawData(data);
}

function updateSeatedState(isSeated) {
    const seatedCard = seatedIcon.closest('.seated-state');
    if (isSeated) {
        seatedIcon.textContent = '🪑';
        seatedText.textContent = 'Seated';
        seatedText.style.color = '#4CAF50';
        seatedCard.classList.remove('empty');
    } else {
        seatedIcon.textContent = '🪑';
        seatedText.textContent = 'Empty';
        seatedText.style.color = '#f44336';
        seatedCard.classList.add('empty');
    }
}

function updateBalanceState(isBadBalance, isSeated) {
    const balanceCard = balanceIcon.closest('.balance-state');
    if (!isSeated) {
        balanceIcon.textContent = '❓';
        balanceText.textContent = 'Unknown';
        balanceText.style.color = '#999';
        balanceCard.classList.remove('bad');
    } else if (isBadBalance) {
        balanceIcon.textContent = '⚠️';
        balanceText.textContent = 'Bad Posture';
        balanceText.style.color = '#FF9800';
        balanceCard.classList.add('bad');
    } else {
        balanceIcon.textContent = '✔️';
        balanceText.textContent = 'Good Posture';
        balanceText.style.color = '#4CAF50';
        balanceCard.classList.remove('bad');
    }
}

function updateVibrationState(shouldVibrate) {
    if (shouldVibrate) {
        vibrationIcon.classList.add('pulse');
        vibrationText.textContent = 'Alert Active';
        vibrationText.style.color = '#f44336';
        vibrationCard.classList.add('active');
    } else {
        vibrationIcon.classList.remove('pulse');
        vibrationText.textContent = 'Inactive';
        vibrationText.style.color = '#999';
        vibrationCard.classList.remove('active');
    }
}

function updateTimeMetrics(timeSitVal, timeBlcVal) {
    // Time seated
    const sitSeconds = Math.floor(timeSitVal);
    const sitMinutes = Math.floor(timeSitVal / 60);
    timeSit.textContent = timeSitVal.toFixed(1) + 's';
    timeSitMin.textContent = sitMinutes + ' min';

    // Time bad balance
    const blcSeconds = Math.floor(timeBlcVal);
    const blcMinutes = Math.floor(timeBlcVal / 60);
    timeBlc.textContent = timeBlcVal.toFixed(1) + 's';
    timeBlcMin.textContent = blcMinutes + ' min';

    // Update mood emoji based on sit time
    updateMoodEmoji(timeSitVal);
}

function getEmojiByTimeSeated(timeSitVal) {
    /**
     * 根据坐着时间返回对应的emoji和状态信息
     * 阈值映射（演示模式）：
     * 实际15分钟 = UI中5秒
     * 实际45分钟 = UI中15秒
     * 
     * < 5s: 😄 (开心)
     * 5-15s: 😐 (平常)
     * >= 15s: 😭 (累了)
     */
    const timeSeconds = timeSitVal; // 直接用秒数
    
    if (timeSeconds < 5) {
        return {
            emoji: '😄',
            status: 'Keep it up!',
            statusColor: '#4CAF50'
        };
    } else if (timeSeconds < 15) {
        return {
            emoji: '😐',
            status: 'Take a break soon',
            statusColor: '#FF9800'
        };
    } else {
        return {
            emoji: '😭',
            status: 'Time to rest!',
            statusColor: '#f44336'
        };
    }
}

function updateMoodEmoji(timeSitVal) {
    /**
     * 更新mood emoji - 根据坐着时间显示不同表情
     * 并添加过渡动画效果
     */
    const moodData = getEmojiByTimeSeated(timeSitVal);
    const currentEmoji = moodEmoji.textContent;
    
    // 如果emoji改变，添加旋转动画
    if (currentEmoji !== moodData.emoji) {
        moodEmoji.style.animation = 'none';
        
        // 触发重新计算以应用动画
        void moodEmoji.offsetWidth;
        
        // 平滑过渡emoji
        moodEmoji.style.opacity = '0.5';
        moodEmoji.style.transform = 'scale(0.8) rotateX(90deg)';
        
        setTimeout(() => {
            moodEmoji.textContent = moodData.emoji;
            moodEmoji.style.opacity = '1';
            moodEmoji.style.transform = 'scale(1) rotateX(0deg)';
            moodEmoji.style.animation = 'mood-bounce 1s ease-in-out infinite';
        }, 150);
    } else {
        moodEmoji.style.animation = 'mood-bounce 1s ease-in-out infinite';
    }
    
    moodStatus.textContent = moodData.status;
    moodStatus.style.color = moodData.statusColor;
}

function updateSensorBars(normValues) {
    if (!normValues || normValues.length !== 4) return;

    normValues.forEach((value, index) => {
        // Clamp value between 0 and 1
        const percentage = Math.min(100, Math.max(0, value * 100));
        
        const bar = document.getElementById(sensorValues[index]);
        const valText = document.getElementById(sensorValText[index]);

        if (bar) {
            bar.style.height = percentage + '%';
        }
        if (valText) {
            valText.textContent = value.toFixed(2);
        }
    });
}

function updateRawData(data) {
    const displayData = {
        timestamp: new Date(data.timestamp * 1000).toISOString(),
        user_id: data.user_id || currentUserId || 'not_set',
        seattype: data.seattype ? 'Seated' : 'Empty',
        blc_bad: data.blc_bad ? 'Bad' : 'Good',
        time_sit_s: data.time_sit.toFixed(1),
        time_blc_s: data.time_blc.toFixed(1),
        should_vibrate: data.should_vibrate ? 'Yes' : 'No',
        raw_pressure: data.raw_values,
        normalized_pressure: data.norm_values.map(v => v.toFixed(3))
    };

    rawDataDisplay.textContent = JSON.stringify(displayData, null, 2);
}

// ============ Tab Navigation ============
function setupTabNavigation() {
    /**
     * Setup tab switching functionality
     */
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.getAttribute('data-tab');
            
            // Remove active class from all buttons and contents
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked button and corresponding content
            btn.classList.add('active');
            const tabContent = document.getElementById(tabName + '-tab');
            if (tabContent) {
                tabContent.classList.add('active');
            }
        });
    });
}

// ============ Calibration Controls ============
function setupCalibrationControls() {
    /**
     * Setup calibration mode controls
     */
    btnSyncUser.addEventListener('click', syncUserID);
    btnRecordBalanced.addEventListener('click', () => recordCalibration(0));
    btnRecordUnbalanced.addEventListener('click', () => recordCalibration(1));
}

function syncUserID() {
    /**
     * Sync user ID to server via WebSocket
     */
    const userId = userIdInput.value.trim();
    
    if (!userId) {
        showCalibMessage('Please enter a user ID', 'error');
        return;
    }
    
    currentUserId = userId;
    currentUserIdSpan.textContent = userId;
    
    // Emit user_id update to server
    socket.emit('set_user_id', { user_id: userId });
    
    showCalibMessage(`User ID synced: ${userId}`, 'success');
    console.log('[Calibration] User ID synced:', userId);
}

function recordCalibration(label) {
    /**
     * Send calibration command to server
     * label: 0 = balanced, 1 = unbalanced
     */
    const userId = userIdInput.value.trim();
    
    if (!userId) {
        showCalibMessage('Please enter and sync user ID first', 'error');
        return;
    }
    
    const duration = parseInt(calibDuration.value) || 10;
    
    const cmd = {
        user_id: userId,
        label: label,
        duration: duration
    };
    
    socket.emit('start_calibration', cmd);
    
    const labelText = label === 0 ? 'Balanced (Label 0)' : 'Unbalanced (Label 1)';
    showCalibMessage(`Recording ${labelText} for ${duration}s...`, 'success');
    console.log('[Calibration] Started:', cmd);
}

function showCalibMessage(message, type = 'info') {
    /**
     * Display message in calibration status area
     */
    calibMessage.textContent = message;
    calibMessage.className = 'status-message ' + type;
}

// ============ Global User ID Control ============
function setupGlobalUserIdControls() {
    /**
     * Setup global user ID input and sync button
     */
    btnSyncGlobalUser.addEventListener('click', syncGlobalUserID);
    globalUserIdInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            syncGlobalUserID();
        }
    });
}

function syncGlobalUserID() {
    /**
     * Sync user ID from the main global input
     */
    const userId = globalUserIdInput.value.trim();
    
    if (!userId) {
        showUserSyncStatus('Please enter a user ID', 'error');
        return;
    }
    
    currentUserId = userId;
    currentUserIdSpan.textContent = userId;
    userIdInput.value = userId; // Sync to calibration tab input
    
    // Emit user_id update to server
    socket.emit('set_user_id', { user_id: userId });
    
    showUserSyncStatus('✓ Synced', 'success');
    console.log('[User ID] Synced globally:', userId);
}

function showUserSyncStatus(message, type = 'info') {
    /**
     * Display user sync status
     */
    userSyncStatus.textContent = message;
    userSyncStatus.className = 'sync-status ' + type;
    
    if (type === 'success') {
        setTimeout(() => {
            userSyncStatus.textContent = '';
            userSyncStatus.className = 'sync-status';
        }, 3000);
    }
}

// ============ Initialization ============
document.addEventListener('DOMContentLoaded', () => {
    console.log('[Init] Chair Posture Monitor UI initialized');
    
    // Initially set MQTT status to connecting
    mqttStatus.textContent = '●';
    mqttStatus.classList.remove('connected', 'disconnected');
    mqttStatus.style.opacity = '0.6'; // Semi-transparent while waiting
    
    // Request initial data
    socket.emit('request_data');
    
    // Update status indicators
    updateConnectionStatus('ws', socket.connected);
    updateLastUpdateTime();
    
    // Start signal timeout check
    startSignalTimeoutCheck();
    
    // Initialize tab navigation
    setupTabNavigation();
    
    // Initialize calibration controls
    setupCalibrationControls();
    
    // Initialize global user ID controls
    setupGlobalUserIdControls();
});

// ============ Periodic Status Check ============
setInterval(() => {
    if (!socket.connected) {
        updateConnectionStatus('ws', false);
    }
}, 5000);
