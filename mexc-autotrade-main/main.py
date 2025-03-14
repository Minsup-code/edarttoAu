import csv
import time
from datetime import datetime
from loguru import logger
from config.config import DEFAULT_SYMBOL
from config.secrets import UIDS_PER_SYMBOL
from utils.license_manager import check_program_expiry, check_uid_valid
from core.uid_auth import prompt_uid_and_auth
from web_selenium.browser_stealth import BrowserStealth, set_cross_and_leverage_50
from core.order_executor import OrderExecutor
from core.position_tracker import PositionTracker
from core.risk_manager import RiskManager
from core.strategy import TradingStrategy
from core.websocket_feed import MexcRestPollingFeed


def get_symbol_by_uid(uid: str) -> str:
    for symbol, uid_list in UIDS_PER_SYMBOL.items():
        if uid in uid_list:
            return symbol
    return DEFAULT_SYMBOL

def on_data_received(data_dict, strategy: TradingStrategy, risk_manager: RiskManager):
    """
    MexcRestPollingFeed로부터 받은 시세 데이터 처리:
    data_dict = {
      "lastPrice": float or None,
      "deals": [...],
      "kline": [...]
    }
    - 여기서는 'lastPrice'만 이용해 전략 실행 (체결/캔들은 참조용)
    """
    last_price = data_dict.get("lastPrice")
    if last_price is None:
        return

    # 팝업 닫기 
    risk_manager.close_popups()

    # 전략에 "현재가" 전달 -> on_new_price()
    # 1분봉 마감 여부(candle_closed)는 알 수 없으므로 False로 넣음
    strategy.on_new_price(float(last_price), candle_closed=False)

    # 시세와 EMA 값을 로그로 출력
    logger.info(
        f"[시세] lastPrice={float(last_price):.4f}, "
        f"EMA1={strategy.ema1:.4f}, EMA2={strategy.ema2:.4f}, EMA3={strategy.ema3:.4f}"
    )

    # 목표 거래량 달성 체크
    risk_manager.check_volume_goal_and_sleep()

def prompt_user_seed() -> float:
    """사용자로부터 운용시드(USDT) 입력받기"""
    while True:
        val = input("운용 시드(USDT)를 입력하세요: ")
        try:
            seed = float(val)
            if seed <= 0:
                logger.warning("0 이하 금액은 불가합니다. 다시 입력.")
                continue
            return seed
        except ValueError:
            logger.warning("잘못된 입력입니다. 숫자를 입력하세요.")

def main():
    logger.info("=== MEXC 무손실 거래량 쌓기 (REST 폴링 버전) 시작 ===")

    # 1) 프로그램 만료일 확인
    check_program_expiry()

    # 2) UID 인증(화이트리스트)
    uid = prompt_uid_and_auth()
    check_uid_valid(uid)

    # UID → 심볼 매핑
    user_symbol = get_symbol_by_uid(uid)
    logger.info(f"[main] UID={uid} => 심볼: {user_symbol}")

    # 3) 사용자 운용시드 입력
    user_seed = prompt_user_seed()

    # 4) 브라우저 초기화 + MEXC 로그인
    stealth = BrowserStealth()
    driver = stealth.init_driver()
    stealth.login_mexc(driver)
    stealth.go_to_usdt_m_futures(driver)

    # 5) RiskManager, PositionTracker, OrderExecutor, Strategy 초기화
    risk_manager = RiskManager(driver=driver, position_tracker=None, user_seed=user_seed)
    risk_manager.close_popups()

    # 선물 진입 후 원하는 심볼 선택 + 교차/레버리지 50배 + 코인 단위로 거래
    stealth.select_symbol(driver, user_symbol)
    set_cross_and_leverage_50(driver)
    stealth.set_futures_unit_coin(driver, user_symbol)

    risk_manager.close_popups()

    position_tracker = PositionTracker(symbol=user_symbol, driver=driver)
    # 초기 자산 세팅
    position_tracker.set_initial_balance()

    risk_manager.position_tracker = position_tracker
    order_executor = OrderExecutor(driver, symbol=user_symbol, risk_manager=risk_manager)

    # position_tracker에 임시 executor 연결 -> 포지션 정리용
    position_tracker.temp_order_executor = order_executor

    # 이미 포지션 있으면 전부 청산
    logger.info("[main] 기존 오픈 포지션이 있으면 청산합니다.")
    position_tracker.close_all_positions()

    strategy = TradingStrategy(symbol=user_symbol, position_tracker=position_tracker, risk_manager=risk_manager)
    strategy.set_order_executor(order_executor)
    strategy.set_user_seed(user_seed)

    # 6) REST 폴링 피드 시작
    feed = MexcRestPollingFeed(
        symbol=user_symbol,
        on_data_callback=lambda d: on_data_received(d, strategy, risk_manager),
        poll_interval=0.5,       # 0.5초마다 호출
        kline_interval="Min1"
    )
    feed.start()

    last_reset_date = None

    # 주기적으로 CSV에 기록
    csv_filename = "trading_log.csv"
    with open(csv_filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "AccumulatedVolume", "RealizedPnL"])

    last_log_time = time.time()

    try:
        while True:
            # (1) 매일 15:00에 거래량=0으로 리셋
            now = datetime.now()
            if now.hour == 15 and last_reset_date != now.date():
                position_tracker._accumulated_volume = 0.0
                position_tracker._realized_pnl = 0.0
                last_reset_date = now.date()
                logger.info("[main] 15:00 거래량/손익 초기화.")

            # 1시간 간격으로 CSV 로그 기록
            if time.time() - last_log_time >= 60:
                acc_vol = position_tracker.get_accumulated_volume()
                # a) 현재 순 PnL (=미실현+실현 모두 포함)
                current_pnl = position_tracker.get_current_profit()
                # b) 현재 미실현 PnL
                ur_pnl = position_tracker.get_unrealized_pnl()
                # c) 새 방식으로 뽑은 '현재 실현 PnL' = (current_pnl - ur_pnl)
                realized_pnl_new = position_tracker.get_realized_pnl_by_balance()

                logger.info(
                    f"[main] current_pnl={current_pnl:.4f}, "
                    f"unrealized_pnl={ur_pnl:.4f}, "
                    f"realized_pnl={realized_pnl_new:.4f}"
                )

                with open(csv_filename, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                        f"{acc_vol:.4f}",
                        f"{realized_pnl_new:.4f}"
                    ])

                logger.info(f"[main] 1분 로그 => 거래량={acc_vol:.4f}, 실현손익={current_pnl:.4f}")
                last_log_time = time.time()

            # (2) 세션 만료 체크 -> 재로그인
            risk_manager.check_session_and_relogin()
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("사용자 Ctrl+C 종료.")
    finally:
        logger.info("[main] 프로그램 종료 전, 모든 포지션 강제 청산 시도.")
        position_tracker.close_all_positions()
        feed.stop()
        driver.quit()
        logger.info("=== 프로그램 종료 ===")


if __name__ == "__main__":
    main()




# def get_resource_path(relative_path):
#     """패키징된 실행 파일에서 리소스를 찾는 함수"""
#     if getattr(sys, 'frozen', False):  # 실행 파일에서 실행 중인지 확인
#         base_path = sys._MEIPASS  # 실행 파일 경로 (PyInstaller가 만든 임시 디렉터리)
#     else:
#         base_path = os.path.dirname(os.path.abspath(__file__))  # 소스 코드 경로

#     return os.path.join(base_path, relative_path)

# # config 폴더 내부의 파일 경로 얻기
# bitflow_autoD_file = get_resource_path("config/Bitflow_autoD.py")
# config_file = get_resource_path("config/config.py")
# secrets_file = get_resource_path("config/secrets.py")

# # core 폴더 내부의 파일 경로 얻기
# order_executor_file = get_resource_path("core/order_executor.py")
# position_tracker_file = get_resource_path("core/position_tracker.py")
# risk_manager_file = get_resource_path("core/risk_manager.py")
# strategy_file = get_resource_path("core/strategy.py")
# uid_auth_file = get_resource_path("core/uid_auth.py")
# websocket_feed_file = get_resource_path("core/websocket_feed.py")

# # utils 폴더 내부의 파일 경로 얻기
# init_file = get_resource_path("utils/__init__.py")
# license_manager_file = get_resource_path("utils/license_manager.py")

# # backtest 폴더 내부의 파일 경로 얻기
# backtest_simulator_file = get_resource_path("backtest/backtest_simulator.py")

# # web_selenium 폴더 내부의 파일 경로 얻기
# browser_stealth_file = get_resource_path("web_selenium/browser_stealth.py")

# # 파일 읽기 예시
# def read_file(file_path):
#     try:
#         with open(file_path, 'r') as file:
#             return file.read()
#     except Exception as e:
#         print(f"파일을 읽는 도중 오류가 발생했습니다: {file_path}")
#         print(e)
#         return None

# # 각 파일의 내용을 읽어오기
# bitflow_autoD_data = read_file(bitflow_autoD_file)
# config_data = read_file(config_file)
# secrets_data = read_file(secrets_file)

# order_executor_data = read_file(order_executor_file)
# position_tracker_data = read_file(position_tracker_file)
# risk_manager_data = read_file(risk_manager_file)
# strategy_data = read_file(strategy_file)
# uid_auth_data = read_file(uid_auth_file)
# websocket_feed_data = read_file(websocket_feed_file)

# init_data = read_file(init_file)
# license_manager_data = read_file(license_manager_file)

# backtest_simulator_data = read_file(backtest_simulator_file)

# browser_stealth_data = read_file(browser_stealth_file)

# # 읽은 데이터 출력 (원하는 방식에 맞게 사용)
# if bitflow_autoD_data:
#     print("Bitflow_autoD.py data loaded:")
#     print(bitflow_autoD_data)

# if config_data:
#     print("config.py data loaded:")
#     print(config_data)

# if secrets_data:
#     print("secrets.py data loaded:")
#     print(secrets_data)

# if order_executor_data:
#     print("order_executor.py data loaded:")
#     print(order_executor_data)

# if position_tracker_data:
#     print("position_tracker.py data loaded:")
#     print(position_tracker_data)

# if risk_manager_data:
#     print("risk_manager.py data loaded:")
#     print(risk_manager_data)

# if strategy_data:
#     print("strategy.py data loaded:")
#     print(strategy_data)

# if uid_auth_data:
#     print("uid_auth.py data loaded:")
#     print(uid_auth_data)

# if websocket_feed_data:
#     print("websocket_feed.py data loaded:")
#     print(websocket_feed_data)

# if init_data:
#     print("__init__.py data loaded:")
#     print(init_data)

# if license_manager_data:
#     print("license_manager.py data loaded:")
#     print(license_manager_data)

# if backtest_simulator_data:
#     print("backtest_simulator.py data loaded:")
#     print(backtest_simulator_data)

# if browser_stealth_data:
#     print("browser_stealth.py data loaded:")
#     print(browser_stealth_data)

# pyinstaller --onefile --console --icon=bitflow.ico --name=BitFlow --add-data "config;config" --add-data "backtest;backtest" --add-data "core;core" --add-data "utils;utils" --add-data "web_selenium;web_selenium" main.py