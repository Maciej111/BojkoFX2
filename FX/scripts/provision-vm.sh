#!/usr/bin/env bash
# =============================================================================
#  BojkoFx - VM Provisioning Script
#  Run on fresh Ubuntu 22.04 LTS GCP VM
#  Usage: bash provision-vm.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK] $1${NC}"; }
step() { echo -e "\n${CYAN}==> $1${NC}"; }

# ---------------------------------------------------------------------------
# 1. System update + essentials
# ---------------------------------------------------------------------------
step "System update"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q
apt-get install -y -q git curl wget unzip htop screen
ok "System updated and essentials installed"

# ---------------------------------------------------------------------------
# 2. Python 3.12
# ---------------------------------------------------------------------------
step "Python 3.12 setup"
apt-get install -y -q software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -q
apt-get install -y -q python3.12 python3.12-venv python3.12-dev python3-pip
ok "Python installed: $(python3.12 --version)"

# ---------------------------------------------------------------------------
# 3. Java 11 (required for IB Gateway)
# ---------------------------------------------------------------------------
step "Java 11 setup"
apt-get install -y -q openjdk-11-jre
ok "Java installed: $(java -version 2>&1 | head -1)"

# ---------------------------------------------------------------------------
# 4. Project directory structure
# ---------------------------------------------------------------------------
step "Creating project directories"
mkdir -p /home/macie/bojkofx/logs
mkdir -p /home/macie/bojkofx/venv
mkdir -p /home/macie/bojkofx/config
mkdir -p /home/macie/bojkofx/data
ok "Directories created: bojkofx/ logs/ venv/ config/ data/"

# ---------------------------------------------------------------------------
# 5. Python virtual environment
# ---------------------------------------------------------------------------
step "Creating Python virtual environment"
python3.12 -m venv /home/macie/bojkofx/venv
/home/macie/bojkofx/venv/bin/pip install --upgrade pip --quiet
ok "Venv created: $(/home/macie/bojkofx/venv/bin/python --version)"
ok "Pip version:  $(/home/macie/bojkofx/venv/bin/pip --version)"

# ---------------------------------------------------------------------------
# 6. Health check script
# ---------------------------------------------------------------------------
step "Creating health check script"
cat > /home/macie/bojkofx/healthcheck.sh << 'EOF'
#!/usr/bin/env bash
# BojkoFx VM Health Check

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}======================================${NC}"
echo -e "${CYAN}  BojkoFx VM Health Check${NC}"
echo -e "${CYAN}======================================${NC}"

echo -e "\n${YELLOW}Python:${NC}"
/home/macie/bojkofx/venv/bin/python --version 2>&1 && echo -e "${GREEN}  [OK] venv active${NC}"

echo -e "\n${YELLOW}Java:${NC}"
java -version 2>&1 | head -1

echo -e "\n${YELLOW}Disk space:${NC}"
df -h / | awk 'NR==2 {printf "  Total: %s  Used: %s  Free: %s  (%s used)\n", $2, $3, $4, $5}'

echo -e "\n${YELLOW}Memory:${NC}"
free -h | awk 'NR==2 {printf "  Total: %s  Used: %s  Free: %s\n", $2, $3, $4}'

echo -e "\n${YELLOW}Uptime:${NC}  $(uptime -p)"

echo -e "\n${YELLOW}Logs directory:${NC}"
ls -lh /home/macie/bojkofx/logs/ 2>/dev/null || echo "  (empty)"

echo -e "\n${CYAN}======================================${NC}"
EOF

chmod +x /home/macie/bojkofx/healthcheck.sh
ok "Health check script created at /home/macie/bojkofx/healthcheck.sh"

# ---------------------------------------------------------------------------
# 7. Ownership
# ---------------------------------------------------------------------------
step "Setting ownership"
chown -R macie:macie /home/macie/bojkofx
ok "Ownership set: macie:macie -> /home/macie/bojkofx"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Provisioning complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "  Python  : $(python3.12 --version)"
echo -e "  Java    : $(java -version 2>&1 | awk -F '"' '/version/ {print $2}')"
echo -e "  Venv    : /home/macie/bojkofx/venv"
echo -e "  Logs    : /home/macie/bojkofx/logs"
echo -e ""
echo -e "  Run health check:"
echo -e "  bash /home/macie/bojkofx/healthcheck.sh"
echo -e "${GREEN}============================================================${NC}"

