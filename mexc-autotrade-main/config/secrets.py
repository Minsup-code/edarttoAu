"""
민감 정보 파일.
"""

UIDS_PER_SYMBOL = {
    "BTC_USDT": [
    ],
    "ETH_USDT": [

    ],
    "XRP_USDT": [
        "65408556",
        "41247374",
        "79813437"
    ],
    "SOL_USDT": [
        "18523343"
    ],
}

# 전체 화이트리스트
ALLOWED_UIDS = []
for uid_list in UIDS_PER_SYMBOL.values():
    ALLOWED_UIDS.extend(uid_list)

