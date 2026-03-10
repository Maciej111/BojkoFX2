import sys; sys.path.insert(0, r'C:\dev\projects\BojkoFx')
from src.core.config import Config

c = Config.from_env('config/config.yaml')
print('=== Symbols ===')
for s, cfg in c.symbols.items():
    print(f'  {s:8s}  LTF={cfg.ltf:4s}  HTF={cfg.htf}  session={str(cfg.session_filter):5s}  enabled={cfg.enabled}')

print()
print('=== Strategy ===')
print(f'  RR={c.strategy.risk_reward}  entry_offset={c.strategy.entry_offset_atr_mult}  sl_buf={c.strategy.sl_buffer_atr_mult}')

print()
sc = c.get_symbol_config('GBPJPY')
print(f'GBPJPY: ltf={sc.ltf} htf={sc.htf} ltf_resample={sc.ltf_resample} htf_resample={sc.htf_resample}')

sc2 = c.get_symbol_config('EURUSD')
print(f'EURUSD: ltf={sc2.ltf} htf={sc2.htf} ltf_resample={sc2.ltf_resample} htf_resample={sc2.htf_resample}')

print()
print('enabled_symbols:', c.enabled_symbols())
print('OK')


