#!/usr/bin/env bash
# Installed at ~/.local/lib/omarchy-adoption-tracker/cheatsheet-wrapper.sh by
# setup.sh, and bound to SUPER+K in place of the default `omarchy-menu-keybindings`
# (see install-keybind.sh). Notifies the tracker daemon, then immediately execs
# the real cheatsheet -- tracking must never delay or break it opening, even if
# the daemon is down.
set -u

slug="omarchy-adoption-tracker"
sock="${XDG_RUNTIME_DIR:-/tmp}/$slug/daemon.sock"
venv_py="$HOME/.local/share/$slug/venv/bin/python"
notifier="$HOME/.local/lib/$slug/notify_cheatsheet.py"

if [[ -S $sock && -x $venv_py ]]; then
  ( "$venv_py" "$notifier" "$sock" & disown ) 2>/dev/null
fi

exec /usr/bin/omarchy-menu-keybindings "$@"
