import time
from loguru import logger

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

class PositionTracker:
    """
    MEXC 웹페이지 직접 파싱으로 포지션/잔고/누적 거래금액을 조회하는 클래스.
    """

    def __init__(self, symbol="BTC_USDT", driver=None):
        self.symbol = symbol
        self.driver = driver
        self._accumulated_volume = 0.0
        self._realized_pnl = 0.0
        self.temp_order_executor = None
        self._initial_balance = 0.0

    def add_trade_volume(self, volume_usdt: float):
        """
        주문 체결 시, 체결금액(= price * quantity) 등을 USDT로 환산해서 누적.
        """
        self._accumulated_volume += volume_usdt

    def get_open_positions(self):
        """
        웹 UI의 '포지션 청산' 탭에서 '포지션 청산 가능' 행 정보를 파싱하여 
        현재 보유 포지션(롱/숏) 수량을 읽어 옵니다.

        - 기본 탭이 '포지션 오픈'일 경우:
          1) '포지션 청산' 탭 클릭 -> 파싱
          2) 파싱 후, 다시 '포지션 오픈' 탭으로 복귀
        """
        results = []
        short_amt = 0.0
        long_amt = 0.0

        revert_to_open_tab = False

        try:
            # (A) 현재 어느 탭이 활성화되어 있는지 확인
            open_tab = self.driver.find_element(
                By.XPATH,
                '//span[@data-testid="contract-trade-order-form-tab-open"]'
            )
            close_tab = self.driver.find_element(
                By.XPATH,
                '//span[@data-testid="contract-trade-order-form-tab-close"]'
            )

            is_close_tab_active = "handle_active__" in close_tab.get_attribute("class")
            is_open_tab_active = "handle_active__" in open_tab.get_attribute("class")

            # 만약 현재 '포지션 청산' 탭이 아니라면, 클릭해서 전환
            if not is_close_tab_active:
                revert_to_open_tab = True
                close_tab.click()

            # (B) '포지션 청산 가능' 행(롱/숏)에 접근
            row_xpath = '//div[contains(@class,"component_closeAvaibleRow__htwY_")]'
            row_elem = WebDriverWait(self.driver, 0.1).until(
                EC.presence_of_element_located((By.XPATH, row_xpath))
            )

            # (C) 해당 행 내부의 'div' 2개 가져오기
            #     - [0] => 숏 포지션 청산 가능 수량
            #     - [1] => 롱 포지션 청산 가능 수량
            divs = row_elem.find_elements(By.XPATH, './div')
            if len(divs) >= 2:
                # (1) 첫 번째 div → 숏 수량
                short_text_elem = divs[0].find_element(
                    By.XPATH, './/span[@class="component_itemValue__O8fBA"]'
                )
                short_raw = short_text_elem.text  # 예: "0.50 ETH"

                # (2) 두 번째 div → 롱 수량
                long_text_elem = divs[1].find_element(
                    By.XPATH, './/span[@class="component_itemValue__O8fBA"]'
                )
                long_raw = long_text_elem.text  # 예: "0.50 ETH"

                short_amt = self._parse_amount(short_raw)
                long_amt  = self._parse_amount(long_raw)

                # 0보다 큰 값만 결과에 추가
                if short_amt > 0:
                    results.append({
                        "symbol": self.symbol,
                        "positionSide": "SHORT",
                        "size": short_amt
                    })
                if long_amt > 0:
                    results.append({
                        "symbol": self.symbol,
                        "positionSide": "LONG",
                        "size": long_amt
                    })

            logger.info(f"[PositionTracker] get_open_positions() => 숏={short_amt}, 롱={long_amt}")

        except Exception as e:
            logger.warning(f"[PositionTracker] get_open_positions() DOM 파싱 실패: {e}")

        finally:
            # (D) 원래 '포지션 오픈' 탭이 활성화되어 있었다면, 되돌아가기
            #     (get_open_positions() 후 다시 매매 로직이 on_new_price에서 동작할 때
            #      '포지션 오픈' 탭이 필요할 수 있으므로 복귀)
            if revert_to_open_tab:
                try:
                    open_tab.click()
                except Exception as e:
                    logger.debug(f"[PositionTracker] '포지션 오픈' 탭 복귀 실패(무시): {e}")

        return results

    def _parse_amount(self, raw_str: str) -> float:
        """
        포지션 수량 문자열에서 숫자만 뽑아 float 변환.
        예) "‎0.50 ETH" → 0.50
        """
        clean = raw_str.replace("\u200B", "").replace("\u3000", "")
        clean = clean.replace("BTC", "").replace("ETH", "").replace("USDT", "")
        clean = clean.replace(",", "").strip()

        clean = re.sub(r"[^0-9.]+", "", clean)
        if not clean:
            clean = "0"
        return float(clean)

    def get_accumulated_volume(self) -> float:
        """
        누적 거래금액(USDT)을 반환.
        """
        return self._accumulated_volume

    def close_all_positions(self):
        """
        모든 포지션(롱/숏)을 전부 청산.
        """
        if not self.temp_order_executor:
            logger.warning("[PositionTracker] close_all_positions() -> temp_order_executor가 없습니다.")
            return

        positions = self.get_open_positions()
        for pos in positions:
            side = pos.get("positionSide", "")
            size = pos.get("size", 0.0)
            if size > 0:
                logger.info(f"[PositionTracker] 기존 포지션 청산 시도: {side}, size={size}")
                if side.upper() == "LONG":
                    self.temp_order_executor.close_position("LONG", size)
                else:
                    self.temp_order_executor.close_position("SHORT", size)

    # 실현손익 관련 함수 
    def add_realized_pnl(self, pnl: float):
        """
        부분/전량 청산 시 계산된 실현 손익(pnl)을 누적.
        (롱 청산 시: (청산가격 - 진입가격) * 수량, 
         숏 청산 시: (진입가격 - 청산가격) * 수량)
        """
        self._realized_pnl += pnl
        logger.info(f"[PositionTracker] add_realized_pnl={pnl:.4f} => total_realized_pnl={self._realized_pnl:.4f}")

    def get_realized_pnl(self) -> float:
        """
        누적 실현손익을 반환.
        """
        return self._realized_pnl
    
    # --------------------------------------------
    # 1) '총 자산' 파싱 함수 예시
    # --------------------------------------------
    def get_total_balance(self) -> float:
        """
        자산 카드에서 '총 자산' 항목(예: '175.1783 USDT')을 파싱하여 float 변환.
        """
        try:
            # 1) 자산 카드 자체를 찾아 화면에 보이도록 스크롤
            asset_card = self.driver.find_element(By.CSS_SELECTOR, 'div._symbol__gridLayoutAssetsCard__wLdUx')
            self.driver.execute_script("arguments[0].scrollIntoView(true);", asset_card)
            time.sleep(0.5)  # 필요 시 조정

            # 2) "총 자산"이 들어간 라벨(div) 바로 옆의 값(div)을 찾음
            #    - XPATH에서 현재 asset_card 아래(.)에서만 검색하도록 '.' prefix 사용
            row_elem = asset_card.find_element(
                By.XPATH,
                './/div[contains(@class,"assets_walletRow__")]'
                '   //div[@class="ant-col assets_walletLabel__w3vaw" and span[text()="총 자산"]]'
                '/following-sibling::div[@class="ant-col assets_walletVal__7l0C2"]'
            )
            
            # 3) 텍스트 추출 => 예) "175.1783 USDT"
            raw_text = row_elem.get_attribute("innerText").strip()
            # 혹은 row_elem.text.strip() 으로도 가능

            # 4) "USDT" 등 문자 제거 후 숫자+소수점만 남김
            balance_str = re.sub(r'[^0-9.]+', '', raw_text)
            if not balance_str:
                return 0.0

            balance_val = float(balance_str)
            return balance_val

        except Exception as e:
            logger.warning(f"[PositionTracker] 총 자산 파싱 실패: {e}")
            return 0.0

    # --------------------------------------------
    # 2) 미실현 손익 파싱 함수 예시
    # --------------------------------------------
    def get_unrealized_pnl(self) -> float:
        """
        자산 카드에서 '미실현 손익' 값(예: "0.0000 USDT") 파싱
        """
        try:
            asset_card = self.driver.find_element(By.CSS_SELECTOR, 'div._symbol__gridLayoutAssetsCard__wLdUx')
            self.driver.execute_script("arguments[0].scrollIntoView(true);", asset_card)
            time.sleep(0.1)

            pnl_parent = self.driver.find_element(
                By.XPATH,
                '//div[contains(@class,"assets_pnlItem__")]'
                '//span[text()="미실현 손익"]/ancestor::span'
            )
            pnl_value_elem = pnl_parent.find_element(
                By.XPATH,
                './/span[contains(@class,"assets_pnl__")]'
            )
            raw_text = pnl_value_elem.get_attribute("innerText")
            # 예: "0.0000 USDT\n≈ 0.00 USD"

            lines = raw_text.splitlines()
            if not lines:
                return 0.0
            top_line = lines[0].strip()  # "0.0000 USDT"
            usdt_val = re.sub(r"[^0-9.]+", "", top_line)
            if not usdt_val:
                return 0.0
            return float(usdt_val)

        except Exception as e:
            logger.warning(f"[PositionTracker] 미실현 손익 파싱 실패: {e}")
            return 0.0

    # --------------------------------------------
    # 3) 초기 자산(시작 자산) 세팅
    # --------------------------------------------
    def set_initial_balance(self):
        self._initial_balance = self.get_total_balance()
        logger.info(f"[PositionTracker] 초기 자산(시작 자산) 설정: {self._initial_balance:.4f} USDT")

    # --------------------------------------------
    # 4) 현재 손익(= 현재 총 자산 - 초기 자산)
    # --------------------------------------------
    def get_current_profit(self) -> float:
        return self.get_total_balance() - self._initial_balance

    # --------------------------------------------
    # 5) (★) 현재 실현 PnL = (총 자산 - 초기 자산) - 미실현손익
    # --------------------------------------------
    def get_realized_pnl_by_balance(self) -> float:
        """
        현재 시점의 실현 손익을
          (현재 총 자산 - 초기 자산) - 미실현 손익
        으로 계산해 반환.
        
        ※ 입출금이 없는 상태라는 전제에서만 정확.
        ※ 부분 청산/부분 진입의 경우에도, 최종적으로는 
           '총 자산' 변화분에서 '미실현'을 뺀 값이 실현 손익이 됨.
        """
        total_pnl = (self.get_total_balance() - self._initial_balance)
        unrealized = self.get_unrealized_pnl()
        realized_pnl = total_pnl - unrealized
        return realized_pnl