import sys
sys.path.insert(0, '.')
from scripts.run_backtest_idx import load_ltf, build_htf_from_ltf, filter_by_date
from src.strategies.trend_following_v1 import run_trend_backtest

SYMBOL = 'usatechidxusd'
HTF = '4h'
YEARS = [2021, 2022, 2023, 2024]
TIMEFRAMES = ['30min', '1h']

BASE = dict(
    pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
    require_close_break=True, entry_offset_atr_mult=0.3, pullback_max_bars=20,
    sl_anchor='last_pivot', sl_buffer_atr_mult=0.5, risk_reward=2.0,
    use_session_filter=False, use_bos_momentum_filter=True,
    bos_min_range_atr_mult=1.2, bos_min_body_to_range_ratio=0.6,
)
FLAG_EXTRAS = dict(
    use_flag_contraction_setup=True,
    flag_impulse_lookback_bars=8, flag_contraction_bars=5,
    flag_min_impulse_atr_mult=2.5, flag_max_contraction_atr_mult=1.2,
    flag_breakout_buffer_atr_mult=0.1, flag_sl_buffer_atr_mult=0.3,
)

def calc_dd(df):
    eq = [0.0]
    for r in df['R']:
        eq.append(eq[-1] + r)
    pk = eq[0]; mx = 0.0
    for v in eq:
        if v > pk: pk = v
        if pk - v > mx: mx = pk - v
    return mx

def run_one(ltf_df, htf_df, s, e, params):
    lf = filter_by_date(ltf_df, s, e)
    hf = filter_by_date(htf_df, s, e)
    if len(lf) < 100:
        return None
    td, m = run_trend_backtest(SYMBOL, lf, hf, params, 10000.)
    if td is None or len(td) == 0:
        return None
    bc = int((td['setup_type'] == 'BOS').sum()) if 'setup_type' in td.columns else len(td)
    fc = int((td['setup_type'] == 'FLAG_CONTRACTION').sum()) if 'setup_type' in td.columns else 0
    return dict(n=len(td), wr=m['win_rate'], er=m['expectancy_R'],
                pf=m['profit_factor'], d=calc_dd(td), b=bc, f=fc)

def fmt(r):
    if r is None:
        return 'N/A'
    er = r['er']; wr = r['wr']; pf = r['pf']; d = r['d']; n = r['n']
    sign = '+' if er >= 0 else ''
    return "E=%s%.3fR WR=%d%% PF=%.2f DD=%.1fR n=%d" % (sign, er, int(wr), pf, d, n)

def split_info(r):
    if r and r['f'] > 0:
        return "  (BOS:%d FLAG:%d)" % (r['b'], r['f'])
    return ''

for ltf in TIMEFRAMES:
    ltf_df = load_ltf(SYMBOL, ltf)
    htf_df = build_htf_from_ltf(ltf_df, HTF)
    pb = dict(BASE)
    pf = dict(BASE)
    pf.update(FLAG_EXTRAS)

    rb = run_one(ltf_df, htf_df, '2021-01-01', '2024-12-31', pb)
    rf = run_one(ltf_df, htf_df, '2021-01-01', '2024-12-31', pf)
    de = (rf['er'] - rb['er']) if (rb and rf) else 0.0
    sign = 'UP' if de > 0 else 'DN'
    print("%s FULL: BOS=%s  |  FLAG=%s  delta=%s%.3fR%s" % (ltf, fmt(rb), fmt(rf), sign, abs(de), split_info(rf)))

    for yr in YEARS:
        rb = run_one(ltf_df, htf_df, '%d-01-01' % yr, '%d-12-31' % yr, pb)
        rf = run_one(ltf_df, htf_df, '%d-01-01' % yr, '%d-12-31' % yr, pf)
        de = (rf['er'] - rb['er']) if (rb and rf) else 0.0
        sign = 'UP' if de > 0 else 'DN'
        print("  %d: BOS=%s  |  FLAG=%s  delta=%s%.3fR%s" % (yr, fmt(rb), fmt(rf), sign, abs(de), split_info(rf)))
