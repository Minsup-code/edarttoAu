import sys
from loguru import logger
from config.secrets import ALLOWED_UIDS

def check_user_uid(uid: str) -> bool:
    """
    UID 화이트리스트 확인.
    """
    return uid in ALLOWED_UIDS

def prompt_uid_and_auth():
    """
    실행 시 사용자 UID 입력 받고, 화이트리스트 내 존재하는지 체크.
    """
    logger.info("[UID Auth] 프로그램 사용을 위해 UID 인증이 필요합니다.")
    uid = input("MEXC UID를 입력하세요: ").strip()
    if not check_user_uid(uid):
        logger.error("[UID Auth] 등록되지 않은 UID. 프로그램을 종료합니다.")
        sys.exit(1)
    logger.info("[UID Auth] UID 인증 통과.")
    return uid
