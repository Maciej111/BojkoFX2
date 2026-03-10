#!/bin/bash
# Test nowego formatu transakcji z test_trades.csv
csv=/tmp/test_trades.csv
total=$(( $(wc -l < "$csv") - 1 ))
echo "  Lacznie eventow w CSV: $total"
echo

awk -F"," "
NR==1 { next }
{
  sid   = \$3
  etype = \$4
  sym[sid]  = \$2
  side[sid] = \$5
  sl[sid]   = \$8
  tp[sid]   = \$9

  if (\$16 != \"\") {
    fp[sid]       = \$16
    fill_ts[sid]  = \$15
    sub(/T/, \" \", fill_ts[sid]); sub(/:[0-9][0-9]\$/, \"\", fill_ts[sid])
  }
  if (\$18 != \"\") {
    ep[sid]       = \$18
    er[sid]       = \$19
    exit_ts[sid]  = \$17
    sub(/T/, \" \", exit_ts[sid]); sub(/:[0-9][0-9]\$/, \"\", exit_ts[sid])
    rR[sid]       = \$23
    comm[sid]     = \$24
  }
}

END {
  n = asorti(sym, sorted)
  printed = 0

  for (i = 1; i <= n; i++) {
    sid = sorted[i]
    s   = sym[sid]
    d   = side[sid]
    f   = fp[sid]
    if (f == \"\") continue

    if (s ~ /JPY/) { fmt_f = sprintf(\"%.3f\", f+0) }
    else           { fmt_f = sprintf(\"%.5f\", f+0) }

    side_lbl = (d == \"LONG\") ? \"BUY \" : \"SELL\"
    fte = fill_ts[sid]; if (fte == \"\") fte = \"?\"

    if (ep[sid] != \"\") {
      e = ep[sid]+0
      if (s ~ /JPY/) { fmt_e = sprintf(\"%.3f\", e) }
      else           { fmt_e = sprintf(\"%.5f\", e) }

      diff = e - f
      if (d == \"SHORT\") diff = f - e
      pips = diff * 10000
      if (s ~ /JPY/) pips = diff * 100

      if (pips >= 0) { pnl_sign = \"+\"; pnl_icon = \"ZYSK  \" }
      else           { pnl_sign = \"\";  pnl_icon = \"STRATA\" }

      pnl_str = sprintf(\"%s%.1f pips\", pnl_sign, pips)
      r_str   = (rR[sid]   != \"\") ? sprintf(\"  R=%+.2f\",  rR[sid]+0)   : \"\"
      c_str   = (comm[sid] != \"\") ? sprintf(\"  kom=%.2f\", comm[sid]+0) : \"\"
      ete     = exit_ts[sid]; if (ete == \"\") ete = \"?\"

      printf \"  [%s] %-7s %s  wej: %s @ %s\n\", pnl_icon, s, side_lbl, fte, fmt_f
      printf \"               wyj: %s @ %s  [%s]\n\", ete, fmt_e, er[sid]
      printf \"               PnL: %-14s%s%s\n\", pnl_str, r_str, c_str
      print  \"\"
    } else {
      if (s ~ /JPY/) { fmt_sl = sprintf(\"%.3f\", sl[sid]+0); fmt_tp = sprintf(\"%.3f\", tp[sid]+0) }
      else           { fmt_sl = sprintf(\"%.5f\", sl[sid]+0); fmt_tp = sprintf(\"%.5f\", tp[sid]+0) }

      printf \"  [OTWARTA] %-7s %s  wej: %s @ %s\n\", s, side_lbl, fte, fmt_f
      printf \"               SL: %s   TP: %s\n\", fmt_sl, fmt_tp
      print  \"\"
    }
    printed++
    if (printed >= 10) break
  }

  if (printed == 0) print \"  (brak transakcji z wypelnieniem)\"
}
" "$csv"

