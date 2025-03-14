import sys
import time
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from loguru import logger
from config.config import SELENIUM_HEADLESS

class BrowserStealth:
    """
    undetected-chromedriver 기반 Selenium 스텔스 브라우저 세팅.
    MEXC 로그인 기능 포함.
    """

    def init_driver(self):
        options = Options()
        if SELENIUM_HEADLESS:
            options.add_argument("--headless")

        # 비밀번호 저장 팝업 비활성화 옵션 추가
        options.add_argument("--guest")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-infobars")
        options.add_argument("--log-level=3")

        driver = uc.Chrome(options=options)
        driver.maximize_window()
        return driver

    def login_mexc(self, driver):
        """
        브라우저에서 사용자가 직접 MEXC에 로그인하도록 유도하고,
        로그인 완료를 감지할 때까지 기다린다.
        """
        logger.info("[BrowserStealth] 브라우저가 열렸습니다. MEXC 로그인 페이지로 이동합니다.")
        driver.get("https://www.mexc.com/ko-KR/login")
        time.sleep(2)

        # 이미 로그인된 상태(예: 쿠키 유지)라면, /login이 아닐 수 있음
        if "login" not in driver.current_url.lower():
            logger.info("[BrowserStealth] 이미 로그인된 상태로 보이므로 절차를 생략합니다.")
            return

        logger.info("[BrowserStealth] 사용자께서 직접 로그인해 주세요. 로그인 완료 시 자동으로 진행됩니다.")

        # 최대 300초(5분) 기다린다고 가정
        timeout_seconds = 300
        start_time = time.time()

        while True:
            # URL에 "login"이 사라졌다면, 로그인 성공으로 간주
            if "login" not in driver.current_url.lower():
                logger.info("[BrowserStealth] 로그인 완료를 감지했습니다. 다음 단계로 진행합니다.")
                break

            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.error(f"[BrowserStealth] 로그인 대기 {timeout_seconds}초를 초과했습니다. 프로그램을 종료합니다.")
                sys.exit(1)

            logger.trace("[BrowserStealth] 로그인 대기 중... (Ctrl + C로 강제 종료 가능)")
            time.sleep(5)

    def hover_and_click(self, driver):
        """
        특정 아이콘에 마우스를 올린 후, 나타나는 메뉴에서 특정 버튼 클릭
        (예시 메서드)
        """
        try:
            icon = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="globalNav"]/div[1]/div/div/div[4]/svg'))
            )

            actions = ActionChains(driver)
            actions.move_to_element(icon).perform()
            logger.info("[BrowserStealth] 네비게이션 아이콘에 마우스 오버 완료.")
            time.sleep(3)

            menu_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//*[@id="globalNav"]/div[4]/div/div/div/div/div/div/div/ul/li[1]/a/div/div[2]/div[1]/span[1]'
                ))
            )
            menu_button.click()
            logger.info("[BrowserStealth] 메뉴 내부 버튼 클릭 완료.")

        except Exception as e:
            logger.error(f"[BrowserStealth] 마우스 오버 + 버튼 클릭 실패: {e}")

    def go_to_usdt_m_futures(self, driver):
        """
        상단 '선물' 탭에 마우스를 올린 후 'USDT-M 선물' 메뉴 클릭하여 이동.
        실패 시 여러 번 재시도 후, 마지막에는 직접 URL로 진입도 시도.
        """
        attempts = 3
        for i in range(attempts):
            try:
                futures_tab = WebDriverWait(driver, 1).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//span[@class="FirstLevelMenuItem_title__hCudf" and text()="선물"]')
                    )
                )
                actions = ActionChains(driver)
                actions.move_to_element(futures_tab).perform()
                time.sleep(1)

                usdtm_menu = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//span[@class="MenuItem_titleContent__wtpD4" and text()="USDT-M 선물"]')
                    )
                )
                usdtm_menu.click()

                logger.info("[BrowserStealth] 'USDT-M 선물' 페이지로 이동 완료.")
                time.sleep(10)

                self.close_web_swiper_modal(driver)
                self.close_novice_guidance_popup(driver)
                return

            except Exception as e:
                logger.error(f"[BrowserStealth] 'USDT-M 선물' 이동 실패 (시도 {i+1}/{attempts}): {e}")
                time.sleep(1)

    def close_novice_guidance_popup(self, driver):
        """
        '신규 사용자 전용!' 팝업이 뜨는 경우 닫는 함수.
        """
        try:
            trade_now_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//button[contains(@class,"NoviceGuidance_modalCancel__") and span[text()="지금 거래하기"]'
                ))
            )
            trade_now_button.click()
            logger.trace("[BrowserStealth] 초보자 팝업 '지금 거래하기' 버튼 클릭.")
            time.sleep(1)
        except:
            try:
                close_btn = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="Close"]'))
                )
                close_btn.click()
                logger.trace("[BrowserStealth] 초보자 팝업 X 버튼 클릭.")
                time.sleep(1)
            except:
                pass

    def select_symbol(self, driver, symbol: str, max_retries=3):
        """
        선물 페이지 드롭다운에서 해당 심볼("BTCUSDT 무기한" 등)을 찾아 클릭.
        선택 실패 시 재시도하고, max_retries번 실패하면 예외로 중단.
        """
        mexc_symbol = symbol.replace("_", "")
        symbol_perpetual_text = f"{mexc_symbol} 무기한"

        for attempt in range(1, max_retries + 1):
            try:
                # (1) 현재 선택된 심볼 박스 클릭 -> 드롭다운 열림
                contract_name_box = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                        "div.ant-dropdown-trigger.contractDetail_contractNameBox__IcVlT"
                    ))
                )
                contract_name_box.click()
                time.sleep(2)

                # (2) 드롭다운 리스트에서 "BTCUSDT 무기한" 같은 항목 찾기
                symbol_elem = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        f'//div[@title="{symbol_perpetual_text}" and contains(@class,"ListSymbolName_showName__")]'
                    ))
                )
                symbol_elem.click()

                logger.info(
                    f"[BrowserStealth] 심볼 '{symbol}' => '{symbol_perpetual_text}' 선택 완료."
                )
                time.sleep(1)
                return  # 선택 성공 시 함수 종료

            except Exception as e:
                logger.warning(
                    f"[BrowserStealth] 심볼 '{symbol}' 선택 실패 (시도 {attempt}/{max_retries}): {e}"
                )
                # 아직 재시도 횟수가 남았다면 잠시 대기 후 다시 시도
                if attempt < max_retries:
                    time.sleep(2)
                else:
                    # 마지막 시도까지 실패 -> 더 이상 진행하지 않음
                    logger.error(
                        f"[BrowserStealth] 심볼 '{symbol}' 선택 {max_retries}회 모두 실패. "
                        "프로그램을 종료합니다."
                    )
                    raise e  

    def set_futures_unit_coin(self, driver, symbol):
        """
        '수량' 단위 설정 모달을 열어,
        테더(USDT) 대신 코인(BTC, ETH 등) 단위로 거래하도록 설정.
        symbol = "BTC_USDT"인 경우 -> base_coin="BTC"
        """
        base_coin = symbol.split("_")[0]  # ex) "BTC_USDT" -> "BTC"

        try:
            # (1) "수량" 선택 영역 클릭 -> 모달 오픈
            wrapper = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".UnitSelect_wrapper__KdK6n"))
            )
            wrapper.click()
            time.sleep(1)

            # (2) "수량별 주문" 라디오 클릭 (기본이 선택되어 있을 수 있지만 재확인)
            try:
                radio = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        '//label[@class="ant-radio-wrapper"]//span[@class="ant-radio-input" and @type="radio"]'
                    ))
                )
                radio.click()
                time.sleep(1)
            except:
                pass

            # (3) 코인 단추 클릭 (ex: BTC)
            coin_button = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    f'//button[contains(@class,"UnitSelectModal_buttonItem__nVwAb") and span[text()="{base_coin}"]]'
                ))
            )
            coin_button.click()
            time.sleep(1)

            # (4) 하단 '확인' 버튼 클릭
            confirm_btn = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//div[@class="ant-modal-footer"]//button[@class="ant-btn ant-btn-primary ant-btn-lg" and span[text()="확인"]]'
                ))
            )
            confirm_btn.click()
            logger.info(f"[BrowserStealth] '{base_coin}' 코인 단위로 거래 설정 완료.")
            time.sleep(1)

        except Exception as e:
            logger.warning(f"[BrowserStealth] 코인 단위 설정 실패: {e}")

    def close_web_swiper_modal(self, driver):
        """
        '웹 스와이퍼' 형태의 이벤트/배너 모달을 닫는 함수.
        1) '오늘은 더 이상 표시하지 않기' 체크
        2) 우측 상단 X 버튼 클릭

        이미 체크되어 있거나, 모달이 없으면 그냥 스킵.
        """
        try:
            # (A) 모달이 표시될 때까지 기다림 (최대 3초)
            modal_content = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.ant-modal-content"))
            )

            # (B) "오늘은 더 이상 표시하지 않기" 체크박스가 있으면 체크
            try:
                dont_show_label = modal_content.find_element(
                    By.CSS_SELECTOR,
                    'label.ant-checkbox-wrapper.cont-view_checkoutBtn__e3BX_'
                )
                # 체크박스 input
                checkbox_input = dont_show_label.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                # 만약 체크 안되어 있다면 클릭
                if not checkbox_input.is_selected():
                    dont_show_label.click()
                    logger.trace("[close_web_swiper_modal] '오늘은 더 이상 표시하지 않기' 체크 완료.")
            except Exception as e:
                logger.trace("[close_web_swiper_modal] 체크박스 탐색 실패 (무시)")

            # (C) 우측 상단 닫기 버튼 클릭
            close_btn = modal_content.find_element(By.CSS_SELECTOR, "button.ant-modal-close")
            close_btn.click()
            logger.trace("[close_web_swiper_modal] 팝업 닫기 버튼 클릭 완료.")

        except Exception as e:
            # 모달이 없거나, 이미 닫혀 있으면 무시
            logger.trace("[close_web_swiper_modal] 모달이 없거나 이미 닫힘")
            
def set_cross_and_leverage_50(driver):
    """
    교차모드 + 레버리지 50배로 자동 설정
    팝업에 막히면 element click intercepted가 날 수 있으므로,
    반드시 팝업을 다 닫은 후 시도해야 함.
    """
    attempt = 0
    while attempt < 3:  # 최대 3회 재시도
        try:
            # 혹시 남아있는 가이드 팝업 닫기 (매 시도마다)
            try:
                guide_popup_confirm = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        '//div[contains(@class,"GuidePopupModal_Button__0VIdm") and text()="확인"]'
                    ))
                )
                driver.execute_script("arguments[0].click();", guide_popup_confirm)
                time.sleep(1)
                logger.trace("[BrowserStealth] 가이드 팝업 '확인' 클릭.")
            except:
                pass

            # (1) "격리/교차" 버튼
            cross_margin_toggle = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//*[@id="mexc-web-inspection-futures-exchange-orderForm"]/div[2]/div[1]/section/div[1]'
                ))
            )
            driver.execute_script("arguments[0].click();", cross_margin_toggle)
            time.sleep(1)

            # 드롭다운에서 "교차 마진" 항목 클릭
            cross_option = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.XPATH, '//span[text()="교차 마진"]/ancestor::label'))
            )
            driver.execute_script("arguments[0].click();", cross_option)
            time.sleep(1)

            # 교차마진 '확인' 버튼
            cross_confirm_btn = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//button[@class="ant-btn ant-btn-primary" and span[text()="확인"]]'
                ))
            )
            driver.execute_script("arguments[0].click();", cross_confirm_btn)
            logger.info("[BrowserStealth] 교차마진 '확인' 버튼 클릭 완료.")
            time.sleep(1)

            # (2) 레버리지 설정 버튼
            leverage_button = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//*[@id="mexc-web-inspection-futures-exchange-orderForm"]/div[2]/div[1]/section/div[2]'
                ))
            )
            driver.execute_script("arguments[0].click();", leverage_button)
            time.sleep(1)

            # (3) "50x" 항목 클릭
            fifty_selector = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//div[@class="LeverageTag_tagItem__dEU_B" and text()="50x"]'
                ))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", fifty_selector)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", fifty_selector)
            time.sleep(1)

            # 레버리지 '확인'
            confirm_btn_2 = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//button[@class="ant-btn ant-btn-primary" and span[text()="확인"]]'
                ))
            )
            driver.execute_script("arguments[0].click();", confirm_btn_2)
            time.sleep(1)

            logger.info("[BrowserStealth] 교차모드 + 레버리지 50배 설정 완료.")
            return  # 설정 성공 시 종료

        except Exception as e:
            attempt += 1
            logger.warning(f"[BrowserStealth] 교차모드/레버리지 설정 실패, 재시도 {attempt}/3: {e}")
            time.sleep(1)

    logger.error("[BrowserStealth] 교차모드/레버리지 설정 3회 이상 실패.")

