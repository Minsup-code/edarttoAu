import websocket
import json
import time

class TradingViewWebSocket:
    def __init__(self, symbol="BINANCE:BTCUSDT"):
        self.tv_socket = "wss://prodata.tradingview.com/socket.io/websocket"
        self.chart_session = self._generate_session()
        self.symbol = symbol
        self.ws = None
        self.data = {}

    def _generate_session(self):
        """랜덤한 세션 ID 생성"""
        import random
        return "cs_" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=12))

    def _send_message(self, ws, message):
        """웹소켓 메시지 전송"""
        ws.send(json.dumps(message))

    def _get_chart_data(self):
        """트레이딩뷰 웹소켓 초기 메시지 전송 (차트 데이터 + 보조지표 요청)"""
        self._send_message(self.ws, {"m": "set_auth_token", "p": ["unauthorized_user_token"]})
        self._send_message(self.ws, {"m": "chart_create_session", "p": [self.chart_session, ""]})
        self._send_message(self.ws, {"m": "resolve_symbol", "p": [self.chart_session, "s1", self.symbol, ""]})
        self._send_message(self.ws, {"m": "create_series", "p": [self.chart_session, "s1", "s1", "1", 300, ""]})  # 1분봉

        # RSI 보조지표 추가
        self._send_message(self.ws, {"m": "create_study", "p": [self.chart_session, "s1", "st1", "RSI@tv-basicstudies", {"length": 14}]})

        # MACD 보조지표 추가
        self._send_message(self.ws, {"m": "create_study", "p": [self.chart_session, "s1", "st2", "MACD@tv-basicstudies", {"fastLength": 12, "slowLength": 26, "signalSmoothing": 9}]})

    def _on_message(self, ws, message):
        """웹소켓 메시지 수신"""
        try:
            msg = json.loads(message)
            for item in msg:
                if "m" in item:
                    if item["m"] == "timescale_update":
                        # 차트 데이터 업데이트
                        data = item["p"][1]["s1"]
                        self.data["price"] = data
                        print(f"📈 가격 데이터 업데이트: {data}")

                    elif item["m"] == "study_completed":
                        # 보조지표 데이터 업데이트
                        study_id = item["p"][0]
                        values = item["p"][1]
                        
                        if study_id == "st1":  # RSI
                            self.data["RSI"] = values
                            print(f"📊 RSI 데이터: {values}")

                        elif study_id == "st2":  # MACD
                            self.data["MACD"] = values
                            print(f"📉 MACD 데이터: {values}")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")

    def _on_open(self, ws):
        """웹소켓 연결 시 실행"""
        print("✅ WebSocket 연결 완료. 데이터 요청 중...")
        self._get_chart_data()

    def _on_error(self, ws, error):
        """웹소켓 에러 처리"""
        print(f"❌ WebSocket 오류: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """웹소켓 종료"""
        print("⚠️ WebSocket 연결 종료됨")

    def start(self):
        """웹소켓 시작"""
        self.ws = websocket.WebSocketApp(
            self.tv_socket,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever()

if __name__ == "__main__":
    symbol = "BINANCE:BTCUSDT"  # 원하는 종목 선택 가능 (SOLUSDT, ETHUSDT, XRPUSDT 등)
    tv_ws = TradingViewWebSocket(symbol)
    tv_ws.start()
