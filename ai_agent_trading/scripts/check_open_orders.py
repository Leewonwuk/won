import sys, os, requests, hmac, hashlib, time
from urllib.parse import urlencode

os.chdir('/home/ubuntu/arb')

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"')

API_KEY = env['BINANCE_API_KEY']
API_SECRET = env['BINANCE_API_SECRET']
BASE = 'https://api.binance.com'

def signed_get(path, params={}):
    p = {**params, 'timestamp': int(time.time()*1000), 'recvWindow': 5000}
    q = urlencode(p)
    sig = hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    r = requests.get(f"{BASE}{path}", params={**p, 'signature': sig},
                     headers={'X-MBX-APIKEY': API_KEY}, timeout=5)
    r.raise_for_status()
    return r.json()

print("=== 미체결 주문 (전체) ===")
orders = signed_get('/api/v3/openOrders')
if orders:
    for o in orders:
        print(f"  {o['symbol']}: {o['side']} {o['origQty']} @ {o['price']} (id={o['orderId']})")
else:
    print("  없음 - 미체결 주문 없음")

print()
print("=== 현재 잔고 ===")
acc = signed_get('/api/v3/account')
for b in acc['balances']:
    free = float(b['free'])
    locked = float(b['locked'])
    if free + locked > 0.0001:
        asset = b['asset']
        if asset in ['USDT','USDC','BNB','TRX','DOGE','XRP','SOL','ADA']:
            print(f"  {asset}: free={free}, locked={locked}")
