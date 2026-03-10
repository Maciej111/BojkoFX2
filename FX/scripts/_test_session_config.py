import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.core.config import Config
c = Config.from_yaml('config/config.yaml')
print('=== Session config per symbol ===')
for s, sc in c.symbols.items():
    if sc.session_filter:
        window = f'{sc.session_start_h:02d}:00-{sc.session_end_h:02d}:00 UTC'
    else:
        window = '24h (no filter)'
    print(f'  {s:8s}  filter={str(sc.session_filter):5s}  window={window:22s}  LTF={sc.ltf}  HTF={sc.htf}')

print()
print('=== in_session() tests (hours 02, 08, 13, 21, 22) ===')
for s, sc in c.symbols.items():
    results = [(h, sc.in_session(h)) for h in [2, 8, 13, 21, 22]]
    print(f'  {s:8s}', '  '.join(f'h{h:02d}={"Y" if v else "N"}' for h, v in results))


