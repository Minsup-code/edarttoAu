# core/websocket_feed.py

import threading
import time
import random
import requests
from loguru import logger

class MexcRestPollingFeed:
    """
    MEXC 선물 REST API를 일정 간격(poll_interval)으로 호출해
    실시간-like 데이터를 가져오는 클래스.

    - 백오프(429, 5xx 오류 시) 적용
    - poll_interval마다 + 무작위 지연(jitter) 0~0.5초
    """

    def __init__(
        self,
        symbol: str,
        on_data_callback,
        poll_interval=1,
        kline_interval="Min1",
        max_retries=3,
        session=None
    ):
        """
        symbol: "BTC_USDT", "ETH_USDT" 등
        on_data_callback: 폴링된 데이터를 전달받을 콜백 함수
        poll_interval: 매 루프마다 기본 대기 시간(초)
        kline_interval: K라인 주기("Min1","Min5"등)
        max_retries: API 호출 실패 시 재시도 횟수
        session: requests.Session() (없으면 새로 만듦)
        """
        self.symbol = symbol
        self.on_data_callback = on_data_callback
        self.poll_interval = poll_interval
        self.kline_interval = kline_interval
        self.max_retries = max_retries

        # 세션 재사용 (커스텀 헤더 포함) -> User-Agent 지정
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        })

        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            logger.warning("[MexcRestPollingFeed] 이미 실행 중.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[MexcRestPollingFeed] 폴링 스레드 시작.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[MexcRestPollingFeed] 폴링 스레드 종료.")

    def _run(self):
        """
        poll_interval + 무작위 지연(jitter)을 섞어
        REST API를 반복 호출 => 콜백 전달.
        """
        while not self._stop_event.is_set():
            data_dict = {}
            data_dict["lastPrice"] = self._get_last_price()
            data_dict["deals"] = self._get_recent_deals(limit=5)
            data_dict["kline"] = self._get_kline_data(limit=5)

            if self.on_data_callback:
                self.on_data_callback(data_dict)

            # 기본 주기 + 무작위 0~0.5초
            sleep_time = self.poll_interval + random.uniform(0, 0.5)
            time.sleep(sleep_time)

    # ------------------------------------------------------------
    # GET helpers (with retry/backoff)
    # ------------------------------------------------------------
    def _safe_get(self, url, params=None):
        """
        GET 호출에 대해:
         - 429 / 5xx 에러 시 백오프 + 재시도
         - max_retries번 시도 후 실패 => None 반환
        """
        attempt = 0
        backoff_sec = 2  # 첫 백오프 2초 (단순 예시)

        while attempt < self.max_retries:
            attempt += 1
            try:
                resp = self.session.get(url, params=params, timeout=5)

                if resp.status_code == 429:
                    # 레이트 리밋 초과 => 백오프 후 재시도
                    logger.warning(f"[MexcRestPollingFeed] 429 Too Many Requests. 백오프 {backoff_sec}s 후 재시도.")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2  # 지수 배수 증가
                    continue

                if 500 <= resp.status_code < 600:
                    # 서버 오류 => 백오프 후 재시도
                    logger.warning(f"[MexcRestPollingFeed] 서버 오류({resp.status_code}). "
                                   f"백오프 {backoff_sec}s 후 재시도.")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2
                    continue

                if not resp.ok:
                    # 그 밖의 오류(400~499 등)
                    logger.warning(f"[MexcRestPollingFeed] HTTP {resp.status_code} 오류. 재시도 불가.")
                    return None

                # 성공 시
                return resp.json()

            except requests.exceptions.RequestException as e:
                logger.warning(f"[MexcRestPollingFeed] 연결 에러({e}). 백오프 {backoff_sec}s 후 재시도.")
                time.sleep(backoff_sec)
                backoff_sec *= 2

        logger.error(f"[MexcRestPollingFeed] {self.max_retries}번 재시도 후 실패 => None 반환.")
        return None

    # ------------------------------------------------------------
    # 실제 API 호출 함수들
    # ------------------------------------------------------------
    def _get_recent_deals(self, limit=1):
        url = f"https://futures.mexc.com/api/v1/contract/deals/{self.symbol}"
        js = self._safe_get(url)
        if not js or not js.get("success"):
            return []
        deals = js.get("data", [])
        return deals[:limit]

    def _get_last_price(self):
        url = f"https://futures.mexc.com/api/v1/contract/ticker?symbol={self.symbol}"
        js = self._safe_get(url)
        if not js or not js.get("success"):
            return None
        ticker_data = js.get("data", {})
        return ticker_data.get("lastPrice")

    def _get_kline_data(self, limit=1):
        base = "https://futures.mexc.com/api/v1/contract/kline"
        url = f"{base}/{self.symbol}?interval={self.kline_interval}&limit={limit}"
        js = self._safe_get(url)
        if not js or not js.get("success"):
            return []
        return js.get("data", [])
