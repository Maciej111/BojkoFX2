import urllib.request, json

req = urllib.request.Request(
    'http://34.31.64.224:8080/api/status',
    headers={'X-API-Key': '0ea9522009779654decab58134a352e6'}
)
try:
    d = json.load(urllib.request.urlopen(req, timeout=10))
    print('alive=%s svc=%s eq=%s update=%s' % (
        d['bot_alive'], d.get('service_state'),
        d['portfolio']['equity'], d['last_update'][:19]
    ))
    # also test candles
    req2 = urllib.request.Request(
        'http://34.31.64.224:8080/api/candles/EURUSD',
        headers={'X-API-Key': '0ea9522009779654decab58134a352e6'}
    )
    bars = json.load(urllib.request.urlopen(req2, timeout=10))
    print('candles EURUSD: %d bars' % len(bars))
    if bars:
        print('last bar:', bars[-1])
except Exception as e:
    print('ERR:', e)

