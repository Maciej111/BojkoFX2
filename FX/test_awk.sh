#!/bin/bash
csv=/tmp/test_trades.csv
total=$(( $(wc -l < "$csv") - 1 ))
echo "Lacznie wierszy: $total"
echo

awk -F"," '
NR==1 { next }
{
  ts     = $1; sub(/T.*/, "", ts)
  sym    = $2
  side   = $5
  fp     = $16
  ep     = $18
  er     = $19
  rR     = $23
  comm   = $24
  sl     = $8
  tp     = $9

  if (fp == "") next

  side_icon = (side == "LONG") ? "LONG " : "SHORT"

  if (ep != "") {
    diff = ep - fp
    if (side == "SHORT") diff = fp - ep
    pips = diff * 10000
    if (sym ~ /JPY/) pips = diff * 100

    pnl_str = sprintf("%.1f pips", pips)
    if (pips > 0) pnl_str = "+" pnl_str
    r_str = (rR != "") ? sprintf("  R=%.2f", rR) : ""
    c_str = (comm != "") ? sprintf("  kom=%.2f", comm) : ""

    status = sprintf("ZAMKNIETA [%-3s]  exit=%.5f  PnL: %s%s%s", er, ep+0, pnl_str, r_str, c_str)
  } else {
    status = sprintf("OTWARTA          SL=%.5f  TP=%.5f", sl+0, tp+0)
  }

  printf "  %-10s  %-8s  %s  entry=%.5f  %s\n", ts, sym, side_icon, fp+0, status
}
' "$csv"

