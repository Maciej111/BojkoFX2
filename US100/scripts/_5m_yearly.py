import sys
sys.path.insert(0, '.')
from scripts.run_backtest_idx import load_ltf, build_htf_from_ltf, filter_by_date
from src.strategies.trend_following_v1 import run_trend_backtest

SYMBOL = 'usatechidxusd'
ltf_df = load_ltf(SYMBOL, '5min')
htf_df = build_htf_from_ltf(ltf_df, '4h')

params = dict(
    pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
    require_close_break=True, entry_offset_atr_mult=0.3, pullback_max_bars=20,
    sl_anchor='last_pivot', sl_buffer_atr_mult=0.5, risk_reward=2.0,
    use_session_filter=True, session_start_hour_utc=13, session_end_hour_utc=20,
    use_bos_momentum_filter=True, bos_min_range_atr_mult=1.2,
    bos_min_body_to_range_ratio=0.6, use_flag_contraction_setup=False,
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

print("\n5m BOS+Pullback | Session 13-20 UTC | Year-by-year\n")
print("%-10s  %5s  %5s  %6s  %5s  %6s" % ("Period", "n", "WR%", "E(R)", "PF", "MaxDD"))
print("-" * 54)

for label, s, e in [
    ("2021-2024", "2021-01-01", "2024-12-31"),
    ("2021",      "2021-01-01", "2021-12-31"),
    ("2022",      "2022-01-01", "2022-12-31"),
    ("2023",      "2023-01-01", "2023-12-31"),
    ("2024",      "2024-01-01", "2024-12-31"),
]:
    lf = filter_by_date(ltf_df, s, e)
    hf = filter_by_date(htf_df, s, e)
    td, m = run_trend_backtest(SYMBOL, lf, hf, params, 10000.)
    if td is None or len(td) == 0:
        print("%-10s  no trades" % label)
        continue
    dd = calc_dd(td)
    print("%-10s  %5d  %4.0f%%  %+6.3fR  %5.2f  %6.1fR" % (
        label, len(td), m['win_rate'], m['expectancy_R'], m['profit_factor'], dd))
