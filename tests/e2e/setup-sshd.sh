#!/usr/bin/env bash
# Starts an sshd the browser e2e suite deploys keys to. Run as root on a
# throwaway Debian/Ubuntu host: the CI runner, or the container in tests/README.md.
# Deploy to Server logs in with a password, so this user (and only this user)
# may use password auth.
set -euo pipefail
PS4='+ $(date +%T) '
set -x

E2E_SSH_USER="${E2E_SSH_USER:-borge2e}"
E2E_SSH_PASSWORD="${E2E_SSH_PASSWORD:-borg-e2e-password}"
E2E_SSH_PORT="${E2E_SSH_PORT:-2222}"

id "$E2E_SSH_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$E2E_SSH_USER"
echo "$E2E_SSH_USER:$E2E_SSH_PASSWORD" | chpasswd
install -d -o "$E2E_SSH_USER" -g "$E2E_SSH_USER" -m 700 "/home/$E2E_SSH_USER/.ssh"

if ! grep -q "Match User $E2E_SSH_USER" /etc/ssh/sshd_config; then
  printf '\nMatch User %s\n  PasswordAuthentication yes\n  KbdInteractiveAuthentication yes\n' \
    "$E2E_SSH_USER" >> /etc/ssh/sshd_config
fi

mkdir -p /run/sshd
ssh-keygen -A >/dev/null
/usr/sbin/sshd -p "$E2E_SSH_PORT"
