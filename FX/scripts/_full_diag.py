"""
Simulates exactly what index.html JS does:
1. GET /api/status  → check bot_alive, equity, symbols
2. GET /api/candles/EURUSD → check bars
3. GET /api/log_tail → check lines
Prints pass/fail for each check.
"""
import urllib.request, json

API = 'http://34.31.64.224:8080/api'
KEY = '0ea9522009779654decab58134a352e6'

def get(path):
    req = urllib.request.Request(API + path, headers={'X-API-Key': KEY})
    return json.load(urllib.request.urlopen(req, timeout=10))

print("=" * 50)

# 1. Status
s = get('/status')
print(f"bot_alive     : {s['bot_alive']}  ({'✅' if s['bot_alive'] else '❌'})")
print(f"service_state : {s.get('service_state')}")
print(f"last_update   : {s['last_update'][:19]}")
p = s['portfolio']
print(f"equity        : {p['equity']}  ({'✅' if p['equity'] else '❌'})")
print(f"open_positions: {p['open_positions']}")
print()
print("Symbols:")
for sym, sd in s['symbols'].items():
    print(f"  {sym}: equity={sd['equity']} pos={sd['pos']}")

print()

# 2. Candles
for sym in ['EURUSD', 'USDJPY', 'USDCHF']:
    bars = get(f'/candles/{sym}')
    ok = len(bars) > 0
    print(f"candles/{sym}: {len(bars)} bars {'✅' if ok else '❌'}")
    if bars:
        b = bars[-1]
        print(f"  last: {b['ts'][:16]}  O={b['open']} H={b['high']} L={b['low']} C={b['close']}")

print()

# 3. Log tail
lt = get('/log_tail')
lines = lt.get('lines', [])
print(f"log_tail: {len(lines)} lines {'✅' if lines else '⚠ (empty)'}")
if lines:
    print(f"  last: {lines[-1][-100:]}")

print()
print("=" * 50)
print("If all ✅ above — API is fine. Problem is in browser cache.")
print("Open NEW tab: http://localhost:8890  (not file://, not port 8888)")

