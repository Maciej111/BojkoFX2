#!/usr/bin/env bash
# =============================================================================
#  BojkoFx — Status Monitor
#  Uruchamiaj przez Git Bash:
#    "C:\Program Files\Git\bin\bash.exe" status.sh
#  LUB przez wrapper:
#    status.cmd
#  NIE uruchamiaj przez WSL (bash.exe z System32) — WSL nie ma gcloud w PATH.
# =============================================================================

# Wymuś UTF-8 — bez tego Git Bash na Windows pokazuje Γö zamiast —
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8

VM="bojkofx-vm"
ZONE="us-central1-a"
PROJECT="sandbox-439719"
SSH="gcloud compute ssh macie@${VM} --zone ${ZONE} --project ${PROJECT} --command"

# Kolory ANSI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

divider() { echo -e "${CYAN}$(printf '═%.0s' {1..70})${NC}"; }
section() { echo; divider; echo -e "  ${BOLD}${CYAN}$1${NC}"; divider; }

echo
echo -e "${BOLD}  BojkoFx — Status Monitor  $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
divider

# ─── 1. SERWISY ──────────────────────────────────────────────────────────────
section "1/6  SERWISY SYSTEMD"
$SSH "
ibgw=\$(systemctl is-active ibgateway)
bot=\$(systemctl is-active bojkofx)
echo \"  ibgateway : \$ibgw\"
echo \"  bojkofx   : \$bot\"
echo
echo '  Ostatnie zdarzenia ibgateway:'
journalctl -u ibgateway -n 4 --no-pager -o short | sed 's/^/    /'
echo
echo '  Ostatnie zdarzenia bojkofx:'
journalctl -u bojkofx -n 4 --no-pager -o short | sed 's/^/    /'
" 2>/dev/null

# ─── 2. PORT 4002 ────────────────────────────────────────────────────────────
section "2/6  POŁĄCZENIE GATEWAY (port 4002)"
$SSH "
port=\$(ss -tlnp | grep 4002)
if [ -n \"\$port\" ]; then
  echo -e '  ✅  Port 4002: LISTENING'
  echo \"  \$port\"
else
  echo '  ❌  Port 4002: NOT LISTENING'
fi
" 2>/dev/null

# ─── 3. EQUITY & KONTO ───────────────────────────────────────────────────────
section "3/6  EQUITY & KONTO (z logów bota)"
$SSH "
# Ostatni wpis z equity
eq=\$(grep 'Account equity' /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null | tail -1)
if [ -n \"\$eq\" ]; then
  echo \"  \$eq\"
else
  echo '  (brak wpisu equity w logu)'
fi
# Ostatni wpis z kontem
acc=\$(grep 'DUP' /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null | tail -1)
[ -n \"\$acc\" ] && echo \"  \$acc\"
" 2>/dev/null

# ─── 4. OSTATNIE LOGI BOTA ───────────────────────────────────────────────────
section "4/6  OSTATNIE LOGI BOTA (bojkofx.log — 20 linii)"
$SSH "tail -20 /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null | sed 's/^/  /'" 2>/dev/null

# ─── 5. TRANSAKCJE / ZLECENIA ────────────────────────────────────────────────
section "5/6  POZYCJE & TRANSAKCJE"
$SSH '
csv=$(find /home/macie/bojkofx -name "paper_trading_ibkr.csv" 2>/dev/null | head -1)
if [ -z "$csv" ] || [ ! -f "$csv" ]; then
  echo "  (brak pliku paper_trading_ibkr.csv)"
  exit 0
fi

total=$(( $(wc -l < "$csv") - 1 ))
echo "  Lacznie eventow w CSV: $total"
echo

# Kolumny CSV (1-based):
# 1=timestamp  2=symbol  3=signal_id  4=event_type  5=side  6=entry_type
# 7=entry_price_intent  8=sl_price  9=tp_price  10=ttl_bars
# 11=parentOrderId  12=tpOrderId  13=slOrderId  14=order_create_time
# 15=fill_time  16=fill_price  17=exit_time  18=exit_price  19=exit_reason
# 20=latency_ms  21=slippage_entry_pips  22=slippage_exit_pips
# 23=realized_R  24=commissions  25=spread_at_entry

awk -F"," "
NR==1 { next }

{
  sid   = \$3   # signal_id — klucz deduplicacji
  etype = \$4

  # Zbierz dane dla kazdego signal_id
  # Nadpisujemy — wiersz EXIT ma wiecej danych niz FILL
  sym[sid]  = \$2
  side[sid] = \$5
  sl[sid]   = \$8
  tp[sid]   = \$9

  if (\$16 != \"\") {
    fp[sid]       = \$16   # fill_price (entry)
    fill_ts[sid]  = \$15   # fill_time
    sub(/T/, \" \", fill_ts[sid]); sub(/:[0-9][0-9]\$/, \"\", fill_ts[sid])
  }
  if (\$18 != \"\") {
    ep[sid]       = \$18   # exit_price
    er[sid]       = \$19   # exit_reason
    exit_ts[sid]  = \$17
    sub(/T/, \" \", exit_ts[sid]); sub(/:[0-9][0-9]\$/, \"\", exit_ts[sid])
    rR[sid]       = \$23
    comm[sid]     = \$24
  }
}

END {
  # Drukuj w kolejnosci signal_id (sort numeryczny po ostatnim _)
  n = asorti(sym, sorted)
  printed = 0

  for (i = 1; i <= n; i++) {
    sid = sorted[i]
    s   = sym[sid]
    d   = side[sid]
    f   = fp[sid]
    if (f == \"\") continue   # brak fill — pomijamy

    # Formatowanie ceny wejscia
    if (s ~ /JPY/) { fmt_f = sprintf(\"%.3f\", f+0) }
    else           { fmt_f = sprintf(\"%.5f\", f+0) }

    # Ikona strony
    side_lbl = (d == \"LONG\") ? \"BUY \" : \"SELL\"

    # Czas wejscia (skrocony)
    fte = fill_ts[sid]; if (fte == \"\") fte = \"?\"

    if (ep[sid] != \"\") {
      # --- POZYCJA ZAMKNIETA ---
      e = ep[sid]+0
      if (s ~ /JPY/) { fmt_e = sprintf(\"%.3f\", e) }
      else           { fmt_e = sprintf(\"%.5f\", e) }

      diff = e - f
      if (d == \"SHORT\") diff = f - e
      pips = diff * 10000
      if (s ~ /JPY/) pips = diff * 100

      if (pips >= 0) { pnl_sign = \"+\"; pnl_icon = \"ZYSK \" }
      else           { pnl_sign = \"\";  pnl_icon = \"STRATA\" }

      pnl_str = sprintf(\"%s%.1f pips\", pnl_sign, pips)
      r_str   = (rR[sid]   != \"\") ? sprintf(\"  R=%+.2f\",  rR[sid]+0)   : \"\"
      c_str   = (comm[sid] != \"\") ? sprintf(\"  kom=%.2f\", comm[sid]+0) : \"\"
      ete     = exit_ts[sid]; if (ete == \"\") ete = \"?\"

      printf \"  [%s] %-7s %s  wej: %s @ %s\\n\", \
             pnl_icon, s, side_lbl, fte, fmt_f
      printf \"               wyj: %s @ %s  [%s]\\n\", \
             ete, fmt_e, er[sid]
      printf \"               PnL: %-14s%s%s\\n\", pnl_str, r_str, c_str
      print  \"\"
    } else {
      # --- POZYCJA OTWARTA ---
      if (s ~ /JPY/) { fmt_sl = sprintf(\"%.3f\", sl[sid]+0); fmt_tp = sprintf(\"%.3f\", tp[sid]+0) }
      else           { fmt_sl = sprintf(\"%.5f\", sl[sid]+0); fmt_tp = sprintf(\"%.5f\", tp[sid]+0) }

      printf \"  [OTWARTA] %-7s %s  wej: %s @ %s\\n\", s, side_lbl, fte, fmt_f
      printf \"               SL: %s   TP: %s\\n\", fmt_sl, fmt_tp
      print  \"\"
    }
    printed++
    if (printed >= 10) break
  }

  if (printed == 0) print \"  (brak transakcji z wypelnieniem — bot jeszcze nie zlozyl zlecen)\"
}
" "$csv"
' 2>/dev/null

# ─── 6. ZASOBY VM ────────────────────────────────────────────────────────────
section "6/6  ZASOBY VM"
$SSH "
echo '  --- CPU / uptime ---'
uptime | sed 's/^/  /'
echo
echo '  --- Pamięć (MB) ---'
free -m | sed 's/^/  /'
echo
echo '  --- Dysk ---'
df -h / | sed 's/^/  /'
echo
echo '  --- Procesy Java / Python ---'
ps aux --no-header | grep -E 'java|python' | grep -v grep | awk '{printf \"  %-8s %-6s %-5s  %s\n\",\$1,\$2,\$3,substr(\$0,index(\$0,\$11),60)}' | head -5
" 2>/dev/null

# ─── PODSUMOWANIE ─────────────────────────────────────────────────────────────
section "PODSUMOWANIE"
$SSH "
ibgw=\$(systemctl is-active ibgateway)
bot=\$(systemctl is-active bojkofx)
port=\$(ss -tlnp | grep 4002 | wc -l)
eq=\$(grep 'Account equity' /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null | tail -1 | grep -oP '\\\$[\d,.]+')
errs=\$(grep -c 'ERROR\|CRITICAL' /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null || echo 0)

[ \"\$ibgw\" = 'active' ] && gw_icon='✅' || gw_icon='❌'
[ \"\$bot\"  = 'active' ] && bot_icon='✅' || bot_icon='❌'
[ \"\$port\" -ge 1 ]      && port_icon='✅' || port_icon='❌'

echo \"  \${gw_icon}  ibgateway   : \$ibgw\"
echo \"  \${bot_icon}  bojkofx     : \$bot\"
echo \"  \${port_icon}  port 4002   : \$([ \$port -ge 1 ] && echo LISTENING || echo NOT_LISTENING)\"
echo \"      equity      : \${eq:-(brak)}\"
echo \"      błędy w logu: \$errs\"
" 2>/dev/null

echo
divider
echo -e "  Wygenerowano: $(date '+%Y-%m-%d %H:%M:%S')"
divider
echo


