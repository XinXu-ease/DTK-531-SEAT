#!/usr/bin/env python3
import subprocess
import sys

print("\n妫€鏌i鏁版嵁搴撲腑鐨勬暟鎹?..\n")

# 查询记录总数
cmd = """ssh dti@172.28.54.209 "sqlite3 /home/dti/Desktop/DTK-531-SEAT/pi/chair.db 'SELECT COUNT(*) FROM sensor_data;'" """
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
count = result.stdout.strip()
print(f"鏁版嵁搴撲腑鐨勮褰曟€绘暟: {count}")

# 查询最近的几条记录
cmd = """ssh dti@172.28.54.209 "sqlite3 /home/dti/Desktop/DTK-531-SEAT/pi/chair.db 'SELECT user_id, seattype, sit_duration FROM sensor_data ORDER BY timestamp DESC LIMIT 5;'" """
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
if result.stdout.strip():
    print("\n鏈€杩戠殑5鏉¤褰?")
    print("user_id | seattype | sit_duration")
    print("-" * 40)
    print(result.stdout)
else:
    print("娌℃湁鏁版嵁")

# 查询所有用户
cmd = """ssh dti@172.28.54.209 "sqlite3 /home/dti/Desktop/DTK-531-SEAT/pi/chair.db 'SELECT DISTINCT user_id FROM sensor_data;'" """
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
if result.stdout.strip():
    print("\n鎵€鏈夌敤鎴?")
    print(result.stdout)
else:
    print("娌℃湁鐢ㄦ埛鏁版嵁")
