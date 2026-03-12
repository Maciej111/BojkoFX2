"""Temporary exploration script - timeframe trade count diagnostics."""
import sys, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_backtest_idx import run_backtest, _calc_r_drawdown

def run_one(label, ltf, htf, rr, start, end, sess=True, bos=True, ltf_lb=3, htf_lb=5):
    params={
        'pivot_lookback_ltf':ltf_lb,'pivot_lookback_htf':htf_lb,
        'confirmation_bars':1,'require_close_break':True,
        'entry_offset_atr_mult':0.3,'pullback_max_bars':20,
        'sl_anchor':'last_pivot','sl_buffer_atr_mult':0.5,
        'risk_reward':rr,'use_session_filter':sess,
        'session_start_hour_utc':13,'session_end_hour_utc':20,
        'use_bos_momentum_filter':bos,
        'bos_min_range_atr_mult':1.2,'bos_min_body_to_range_ratio':0.6,
        'use_flag_contraction_setup':False,
        'flag_impulse_lookback_bars':8,'flag_contraction_bars':5,
        'flag_min_impulse_atr_mult':2.5,'flag_max_contraction_atr_mult':1.2,
        'flag_breakout_buffer_atr_mult':0.1,'flag_sl_buffer_atr_mult':0.3,
    }
    td, m = run_backtest(symbol='usatechidxusd', start=start, end=end, params=params, ltf=ltf, htf=htf)
    if m is None:
        print(f'XRES|{label}|0|0|0|0|0|0|0|0', flush=True); return
    n = m.get('trades_count',0)
    er = m.get('expectancy_R',0); pf = m.get('profit_factor',0)
    wr = m.get('win_rate',0); streak = m.get('max_losing_streak',0)
    r_dd = _calc_r_drawdown(td); setups = m.get('total_setups',0)
    score = er * math.sqrt(n) if n >= 5 else -999
    print(f'XRES|{label}|n={n}|wr={wr:.1f}|er={er:+.3f}|pf={pf:.2f}|dd={r_dd:.1f}|str={streak}|setups={setups}|score={score:.2f}', flush=True)

F='2021-01-01'; T='2026-03-07'
combos = [
    ('5m/4h +sess',  '5min', '4h', True),
    ('5m/4h -sess',  '5min', '4h', False),
    ('5m/1h +sess',  '5min', '1h', True),
    ('5m/1h -sess',  '5min', '1h', False),
    ('15m/4h +sess', '15min','4h', True),
    ('15m/1h +sess', '15min','1h', True),
    ('30m/4h +sess', '30min','4h', True),
]
for label, ltf, htf, sess in combos:
    print(f'--- Running {label} ---', flush=True)
    run_one(label, ltf, htf, 2.0, F, T, sess=sess)

print('ALL_DONE', flush=True)
