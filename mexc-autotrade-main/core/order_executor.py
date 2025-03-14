import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
from loguru import logger
from config.config import (
    MAX_ORDER_RETRY,
)

class OrderExecutor:
    """
    MEXC 웹페이지에서 포지션 오픈/청산(롱/숏) 버튼을 클릭하는 클래스.
    UI 변경 시 XPATH 수정 필요.
    """

    def __init__(self, driver, symbol="BTC_USDT", risk_manager=None):
        self.driver = driver
        self.symbol = symbol
        self.risk_manager = risk_manager

        logger.info("[OrderExecutor] DOM 요소를 한 번만 찾아서 캐싱합니다. (주문/청산용)")
        # 주문/청산 탭 버튼
        self.open_tab = self._find_element_quick('//span[@data-testid="contract-trade-order-form-tab-open"]')
        self.close_tab = self._find_element_quick('//span[@data-testid="contract-trade-order-form-tab-close"]')

        # '포지션 오픈' 탭의 수량 입력창
        self.open_qty_input = self._find_element_quick(
            '//div[@class="component_container___navi"]'
            '//div[@class="component_inputWrapper__PxwkC"]'
            '//div[contains(@class,"component_numberInput")]'
            '//input[@class="ant-input"]'
        )

        # 롱/숏 버튼 (포지션 오픈)
        self.open_long_btn = self._find_element_quick('//button[@data-testid="contract-trade-open-long-btn"]')
        self.open_short_btn = self._find_element_quick('//button[@data-testid="contract-trade-open-short-btn"]')

        # '포지션 청산' 탭의 수량 입력창
        # (주의: '포지션 청산' 탭은 초기 로딩 시 숨겨져 있을 수 있으므로, 탭 클릭 후 찾음)
        if self.close_tab:
            self.close_tab.click()
            time.sleep(0.3)  # 탭 전환 잠깐 대기

        self.close_qty_input = self._find_element_quick(
            '//div[@style="display: block;"]'
            '//div[@class="InputNumberHandle_inputOuterWrapper__8w_l1"]'
            '//input[@class="ant-input"]'
        )

        # 롱 청산 / 숏 청산 버튼
        self.close_long_btn = self._find_element_quick(
            '//div[@style="display: block;"]//button[@data-testid="contract-trade-close-long-btn"]'
        )
        self.close_short_btn = self._find_element_quick(
            '//div[@style="display: block;"]//button[@data-testid="contract-trade-close-short-btn"]'
        )

        # 다시 '포지션 오픈' 탭으로 복귀
        if self.open_tab:
            self.open_tab.click()
            time.sleep(0.3)

        logger.info("[OrderExecutor] 캐싱 완료. 주문/청산 시에는 이미 찾은 요소를 그대로 씁니다.")


    def place_market_order(self, side: str, quantity: float) -> bool:
        """
        side: "LONG" or "SHORT"
        quantity: 예) 50, 2 (이미 'base_unit*곱' 형태로 계산된 값)

        [포지션 오픈 시도]
        """
        logger.info(f"[OrderExecutor] 시장가 {side}, 수량={quantity:.4f} 주문 시도")
        attempt = 0
        success = False

        while attempt < MAX_ORDER_RETRY and not success:
            attempt += 1

            if self.risk_manager:
                self.risk_manager.close_popups()

            try:
                # (1) '포지션 오픈' 탭 클릭
                if self.open_tab:
                    self.open_tab.click()

                # (2) 수량 입력창
                if self.open_qty_input:
                    self.open_qty_input.clear()
                    self.open_qty_input.send_keys(str(quantity))

                # (3) 롱/숏 버튼
                if side.upper() == "LONG" and self.open_long_btn:
                    self.open_long_btn.click()
                elif side.upper() == "SHORT" and self.open_short_btn:
                    self.open_short_btn.click()
                else:
                    logger.warning("[OrderExecutor] 올바른 side가 아니거나 버튼 없음.")
                    return False

                # (4) 주문 확인 모달 처리
                self._handle_order_confirm_modal(side)

                logger.info(f"[OrderExecutor] 시장가 {side} {quantity:.4f} 주문 완료.")
                success = True

            except Exception as e:
                logger.warning(f"[OrderExecutor] place_market_order() 재시도({attempt}) 실패: {e}")
                time.sleep(0.1)

        return success

    def close_position(self, side: str, quantity: float) -> bool:
        """
        side: "LONG" -> 롱 포지션 청산
              "SHORT"-> 숏 포지션 청산
        quantity: 코인 수량(이미 base_unit*곱 형태)

        1) '포지션 청산' 탭 클릭
        2) 수량 입력창에 quantity 입력
        3) 롱 청산 or 숏 청산 버튼 클릭
        4) 주문 확인 모달 처리
        5) 실패 시 최대 MAX_ORDER_RETRY번 재시도
        """
        logger.info(f"[OrderExecutor] {side} 포지션 청산 시도, 수량={quantity:.4f}")
        attempt = 0
        success = False

        while attempt < MAX_ORDER_RETRY and not success:
            attempt += 1

            if self.risk_manager:
                self.risk_manager.close_popups()

            try:
                # (1) '포지션 청산' 탭 클릭
                if self.close_tab:
                    self.close_tab.click()

                # (2) 수량 입력창
                if self.close_qty_input:
                    self.close_qty_input.clear()
                    self.close_qty_input.send_keys(str(quantity))

                # (3) '롱 청산' / '숏 청산' 버튼
                if side.upper() == "LONG" and self.close_long_btn:
                    self.close_long_btn.click()
                elif side.upper() == "SHORT" and self.close_short_btn:
                    self.close_short_btn.click()
                else:
                    logger.warning("[OrderExecutor] 올바른 side가 아니거나 청산 버튼 없음.")
                    return False

                # (4) 주문 확인 모달 처리
                self._handle_order_confirm_modal(side, is_close=True)

                logger.info(f"[OrderExecutor] {side} 청산 {quantity:.4f} 완료.")
                success = True

            except (TimeoutException, ElementClickInterceptedException, NoSuchElementException) as e:
                logger.warning(
                    f"[OrderExecutor] close_position() 재시도({attempt}) 실패(인터랙션 문제): {e}"
                )
                time.sleep(0.1)
            except Exception as e:
                logger.warning(
                    f"[OrderExecutor] close_position() 재시도({attempt}) 실패: {e}"
                )
                time.sleep(0.1)

        return success

    # -----------------------------------------------------
    # [주문 확인 모달] "더 이상 표시하지 않기" 체크 & 버튼 클릭
    # -----------------------------------------------------
    def _handle_order_confirm_modal(self, side: str, is_close=False):
        """
        주문(오픈/청산) 직후 뜨는 '주문 확인' 모달 처리.
        - '더 이상 표시하지 않기' 체크
        - 최종 확인 버튼(롱 오픈, 숏 오픈, 롱 청산, 숏 청산) 클릭
        - 이후 모달이 안 뜰 수도 있으므로, 실패해도 그냥 스킵
        """
        try:
            modal_xpath = (
                '//div[contains(@class,"ant-modal-content")]'
                '//div[@class="ant-modal-title" and contains(text(),"주문 확인")]'
            )
            confirm_btn_xpath = (
                '//div[@class="ForcedReminder_buttonWrapper__p_dYb"]'
                '//button[contains(@class,"ant-btn-primary")]'
            )

            # 모달이 매우 짧게 뜨고 사라질 수 있으므로, 짧게만 검사
            modal = WebDriverWait(self.driver, 0.1).until(
                EC.visibility_of_element_located((By.XPATH, modal_xpath))
            )

            # '더 이상 표시하지 않기' 체크 등은 생략
            confirm_btn = modal.find_element(By.XPATH, confirm_btn_xpath)
            confirm_btn.click()
            logger.debug("[OrderExecutor] 주문 확인 모달 확인 버튼 클릭.")
        except:
            # 모달 안 뜨면 그냥 스킵
            pass

    def _find_element_quick(self, xpath: str):
        """
        WebDriverWait 대신 즉시 한 번 시도해보고,
        실패하면 None 반환 (지연 최소화).
        """
        try:
            return self.driver.find_element(By.XPATH, xpath)
        except (NoSuchElementException, ElementClickInterceptedException, TimeoutException):
            return None
        