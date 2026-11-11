#!/usr/bin/env bash
# One-time setup of a fresh Oracle Cloud Ubuntu 24.04 (ARM / Ampere A1) VM.
#
# Run on the VM as the default `ubuntu` user:
#   curl -fsSL https://raw.githubusercontent.com/bacobax/chess_insighter/main/deploy/setup-vm.sh -o setup-vm.sh
#   less setup-vm.sh   # read it first
#   bash setup-vm.sh
#
# Prerequisites in the Oracle console (cannot be done from inside the VM):
#   - Subnet Security List: ingress rules for TCP 80 and TCP 443 (and UDP 443 for HTTP/3) from 0.0.0.0/0
#   - A DNS A record for your domain pointing at the VM's public IP
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/bacobax/chess_insighter.git}"
APP_DIR="${APP_DIR:-$HOME/chess_insighter}"

echo "==> Installing Docker Engine + compose plugin (official Docker apt repository)"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git iptables-persistent
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

echo "==> Opening ports 80/443 in the VM firewall (Oracle images REJECT everything but SSH by default)"
for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
  # shellcheck disable=SC2086
  sudo iptables -C INPUT $rule -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 1 $rule -m conntrack --ctstate NEW -j ACCEPT
done
sudo netfilter-persistent save

echo "==> Cloning the app into $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo
  echo "!! Created $APP_DIR/.env from .env.example — edit it now (SITE_ADDRESS, secrets, MongoDB URI)."
fi

cat <<EOF

Done. Next steps:
  1. Log out and back in (so your user can run docker without sudo).
  2. Edit $APP_DIR/.env
  3. cd $APP_DIR && docker compose up -d --build
  4. docker compose logs -f     # watch Caddy obtain the certificate
EOF
