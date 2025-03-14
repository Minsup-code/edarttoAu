import sys
from datetime import datetime
from loguru import logger
from config.secrets import ALLOWED_UIDS

EXPIRY_DATE = datetime(2026, 3, 1)  # 예시 만료일

def check_program_expiry():
    if datetime.now() > EXPIRY_DATE:
        logger.error("프로그램 사용 기간이 만료되었습니다.")
        sys.exit(1)

def check_uid_valid(uid: str):
    if uid not in ALLOWED_UIDS:
        logger.error("해당 UID는 더 이상 사용할 수 없습니다.")
        sys.exit(1)
