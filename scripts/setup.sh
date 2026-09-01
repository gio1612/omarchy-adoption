#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Manual, one-time install step for the Omarchy Adoption Tracker daemon.
#
# The Omarchy plugin installer never runs plugin code, install hooks, or sudo,
# so nothing here happens automatically when you `omarchy plugin add` or enable
# this plugin. Run it yourself, once:
#
#   bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/setup.sh
#
#   --check    verify prerequisites and exit; changes nothing
#   --force    recreate the venv from scratch
#
# What it touches -- and nothing else:
#   ~/.local/lib/omarchy-adoption-tracker/     daemon code
#   ~/.local/share/omarchy-adoption-tracker/   venv + SQLite database
#   ~/.config/systemd/user/                    the user service unit
#
# It deliberately does NOT edit your Hyprland config. SUPER+K is detected from
# the raw keyboard stream via evdev, matched against the allowlist the daemon
# reads out of `hyprctl binds -j`, so ~/.config/hypr/ stays exactly as you left
# it. (Earlier versions of this script edited bindings.lua to remove a legacy
# tracking block; that is gone. If you are upgrading from such an install, see
# "Upgrading" in the README for the one-line manual cleanup.)
# ---------------------------------------------------------------------------
set -euo pipefail

source_root=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
slug="omarchy-adoption-tracker"

check_only=false
force_venv=false
for arg in "$@"; do
  case "$arg" in
    --check) check_only=true ;;
    --force) force_venv=true ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "setup.sh: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

lib_dir="$HOME/.local/lib/$slug"
data_dir="$HOME/.local/share/$slug"
venv_dir="$data_dir/venv"
unit_dir="$HOME/.config/systemd/user"
unit_file="$unit_dir/$slug.service"

problems=0
note_problem() { echo "setup.sh: $*" >&2; problems=$((problems + 1)); }

# --- prerequisites -----------------------------------------------------------

for cmd in python3 systemctl install; do
  command -v "$cmd" >/dev/null 2>&1 || note_problem "required command is missing: $cmd"
done

if ! python3 -c 'import venv' >/dev/null 2>&1; then
  note_problem "python3 is missing the 'venv' module (install python-virtualenv / python3-venv)"
fi

# Reading /dev/input/event* needs group membership, never root or setuid.
#
# Two separate facts, and conflating them is genuinely confusing:
#   * the group DATABASE   -- `id -nG "$USER"`, what usermod edits
#   * this SESSION's creds -- `id -nG`, stamped at login and never refreshed
# `usermod -aG input` updates the first immediately and the second not at all,
# so a user who has "already done it" still measures nothing until they log
# out and back in. Report those two states differently.
in_group_db=false
in_session=false
id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx input && in_group_db=true
id -nG          2>/dev/null | tr ' ' '\n' | grep -qx input && in_session=true

if ! $in_group_db; then
  note_problem "$USER is not in the 'input' group (needed to read /dev/input/event*).
  Run:  sudo usermod -aG input $USER
  then log out and back in, and re-run this script."
elif ! $in_session; then
  note_problem "$USER is in the 'input' group, but this login session predates it.
  Group membership is stamped at login, so nothing running right now -- including
  systemd --user and the tracker daemon -- can read /dev/input/event*.
  Log out and back in (or reboot), then re-run this script."
fi

# A user service needs a running `systemd --user` instance.
if ! systemctl --user show-environment >/dev/null 2>&1; then
  note_problem "no systemd --user session is available; cannot install the daemon service"
fi

if $check_only; then
  if (( problems == 0 )); then
    echo "setup.sh: all prerequisites satisfied."
    exit 0
  fi
  echo "setup.sh: $problems prerequisite problem(s); see above." >&2
  exit 1
fi

if (( problems > 0 )); then
  echo "setup.sh: refusing to install with $problems unmet prerequisite(s)." >&2
  exit 1
fi

# --- install -----------------------------------------------------------------

install -d -m 700 -- "$lib_dir" "$data_dir" "$unit_dir"

install -m 644 -- "$source_root"/backend/*.py "$lib_dir/"
chmod 755 -- "$lib_dir/daemon.py"

if $force_venv; then
  rm -rf -- "$venv_dir"
fi
if [[ ! -x $venv_dir/bin/python ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --quiet --upgrade pip
"$venv_dir/bin/pip" install --quiet -r "$source_root/backend/requirements.txt"

sed "s|ExecStart=.*|ExecStart=$venv_dir/bin/python $lib_dir/daemon.py|" \
  "$source_root/systemd/$slug.service" > "$unit_file"
chmod 644 -- "$unit_file"

systemctl --user daemon-reload
systemctl --user enable --now "$slug.service"

# --- verify ------------------------------------------------------------------

if ! "$venv_dir/bin/python" "$lib_dir/daemon.py" --self-test; then
  echo "setup.sh: self-test reported problems (see above) -- the daemon may still work" >&2
fi

if systemctl --user is-active --quiet "$slug.service"; then
  echo "Installed. Daemon: $slug.service (enabled at login, running now)."
else
  echo "setup.sh: $slug.service is not active. Check:" >&2
  echo "  journalctl --user -u $slug.service -n 50 --no-pager" >&2
  exit 1
fi

echo "Add the 'Adoption Tracker' bar widget from Omarchy's plugin/widget picker to see stats."
