==================================================
File: test_ui_flow.py
==================================================

# test_ui_flow.py

import time
from loguru import logger
from config import config
from web_selenium.browser_stealth import BrowserStealth, set_cross_and_leverage_50
from core.order_executor import OrderExecutor
from core.position_tracker import PositionTracker
from core.risk_manager import RiskManager

def test_ui_flow():
    logger.info("=== UI 기능 순차 테스트 시작 ===")
    
    # 1) 브라우저 초기화 (Chrome 열기)
    stealth = BrowserStealth()
    driver = stealth.init_driver()
    logger.info("1) undetected-chromedriver 브라우저 초기화 완료.")
    
    # 2) MEXC 로그인
    stealth.login_mexc(driver)
    logger.info("2) MEXC 로그인 테스트 완료.")
    
    # 3) 선물 페이지로 이동 (USDT-M 선물)
    stealth.go_to_usdt_m_futures(driver)
    logger.info("3) USDT-M 선물 페이지 이동 테스트 완료.")
    
    # 4) 선물 페이지에서 '초보자 팝업' 닫기 시도
    stealth.close_novice_guidance_popup(driver)
    logger.info("4) 초보자 안내 팝업 닫기 테스트 완료.")
    
    # 5) 웹 스와이퍼(이벤트/배너) 모달 닫기 시도
    stealth.close_web_swiper_modal(driver)
    logger.info("5) 웹 스와이퍼 모달 닫기 테스트 완료.")
    
    # 6) 심볼 선택 
    test_symbol = config.DEFAULT_SYMBOL
    logger.info(f"6) 심볼 선택({test_symbol}) 테스트 완료.")
    
    # 7) 코인 단위로 거래 설정
    stealth.set_futures_unit_coin(driver, test_symbol)
    logger.info("7) '수량 단위'를 코인 단위로 설정 테스트 완료.")
    
    # 8) 교차마진 + 레버리지 50배 설정
    set_cross_and_leverage_50(driver)
    logger.info("8) 교차모드 + 레버리지 50배 설정 테스트 완료.")
    
    # 9) 팝업 닫기 테스트(RiskManager의 close_popups)
    risk_manager = RiskManager(driver=driver, position_tracker=None)
    risk_manager.close_popups()
    logger.info("9) RiskManager 팝업 닫기 테스트 완료.")
    
    # 10) 주문/청산 테스트 
    position_tracker = PositionTracker(symbol=test_symbol, driver=driver)
    order_executor = OrderExecutor(driver, symbol=test_symbol, risk_manager=risk_manager)
    
    # (10-1) 롱 포지션 진입 예시
    test_qty = 0.0001
    logger.info(f"10-1) 시장가 롱 주문 테스트 - 수량={test_qty}")
    success_long = order_executor.place_market_order("LONG", test_qty)
    if success_long:
        logger.info("롱 포지션 진입 성공.")
    else:
        logger.info("롱 포지션 진입 실패.")
    time.sleep(5)
    
    # (10-2) 롱 포지션 청산 예시
    logger.info(f"10-2) 롱 포지션 청산 테스트 - 수량={test_qty}")
    success_close_long = order_executor.close_position("LONG", test_qty)
    if success_close_long:
        logger.info("롱 포지션 청산 성공.")
    else:
        logger.info("롱 포지션 청산 실패.")
    time.sleep(3)

    # (10-3) 숏 포지션 진입 예시
    logger.info(f"10-3) 시장가 숏 주문 테스트 - 수량={test_qty}")
    success_short = order_executor.place_market_order("SHORT", test_qty)
    if success_short:
        logger.info("숏 포지션 진입 성공.")
    else:
        logger.info("숏 포지션 진입 실패.")
    time.sleep(5)

    # (10-4) 숏 포지션 청산 예시
    logger.info(f"10-4) 숏 포지션 청산 테스트 - 수량={test_qty}")
    success_close_short = order_executor.close_position("SHORT", test_qty)
    if success_close_short:
        logger.info("숏 포지션 청산 성공.")
    else:
        logger.info("숏 포지션 청산 실패.")
    time.sleep(3)
    
    logger.info("10) 실제 주문(롱/숏) 테스트 완료.")
    
    # 모든 테스트 후 브라우저 종료
    driver.quit()
    logger.info("=== UI 기능 순차 테스트 종료 ===")

if __name__ == "__main__":
    test_ui_flow()
