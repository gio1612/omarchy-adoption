#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Static-check every .qml file in this plugin against the REAL Omarchy shell
# type definitions, using Qt's own qmllint.
#
# Why this exists: the plugin once shipped `borderSpec: ...` on a plain
# QtQuick Rectangle. `borderSpec` is a property of the shell's BorderSurface,
# not of Rectangle, so StatsPanel.qml failed to load, BarWidget.qml's Loader
# reported "Type StatsPanel unavailable", and the whole bar widget silently
# disappeared. Nothing in the test suite could see it -- the QML front end has
# no unit tests, and the failure only surfaced at shell-reload time.
#
# qmllint catches exactly that, but only if it can resolve `qs.Ui` /
# `qs.Commons`, which means it needs an Omarchy shell tree. Point
# OMARCHY_SHELL_DIR at one:
#
#   ./tools/lint-qml.sh                       # uses /usr/share/omarchy/shell
#   OMARCHY_SHELL_DIR=/path/to/omarchy/shell ./tools/lint-qml.sh
#
# In CI that tree comes from a shallow clone of basecamp/omarchy.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SHELL_DIR="${OMARCHY_SHELL_DIR:-/usr/share/omarchy/shell}"

QMLLINT="${QMLLINT:-}"
if [[ -z $QMLLINT ]]; then
  for candidate in qmllint qmllint6 /usr/lib/qt6/bin/qmllint /usr/lib/qt6/bin/qmllint6; do
    if command -v "$candidate" >/dev/null 2>&1; then QMLLINT=$candidate; break; fi
  done
fi

if [[ -z $QMLLINT ]]; then
  echo "lint-qml: qmllint not found (install qt6-declarative / qt6-declarative-dev-tools)" >&2
  exit 127
fi

if [[ ! -d $SHELL_DIR/Ui || ! -d $SHELL_DIR/Commons ]]; then
  echo "lint-qml: no Omarchy shell at $SHELL_DIR (expected Ui/ and Commons/)" >&2
  echo "lint-qml: set OMARCHY_SHELL_DIR to an omarchy checkout's shell/ folder" >&2
  exit 127
fi

# Quickshell exposes the shell tree under the `qs` module prefix, so qmllint
# needs an import root that *contains* a directory named `qs`.
IMPORT_ROOT=$(mktemp -d)
trap 'rm -rf "$IMPORT_ROOT"' EXIT
ln -s "$SHELL_DIR" "$IMPORT_ROOT/qs"

# Known qmllint limitations that the Omarchy shell's own sources trip too --
# verified by running qmllint over shell/Ui/Toggle.qml, which reports the same
# things. Filtering these by MESSAGE TEXT (not by category) is deliberate: the
# `missing-property` category is exactly what catches a bad property
# assignment, so the category must stay live.
#
#   * 'not found on type "QObject"' -- Style.font / Style.spacing are inline
#     `QtObject { ... }` sub-objects, which qmllint types as bare QObject and
#     therefore cannot see the tokens inside.
#   * 'Unqualified access' -- referring to an outer id from inside a
#     Component, which is legal and used throughout the shell.
#   * 'inheritance cycle' / 'not resolved' for BarWidget -- our BarWidget.qml
#     extends the shell type of the same name, which confuses the resolver.
#   * Quickshell's own C++ types are not introspectable from qmllint.
IGNORE_RE='not found on type "QObject"|Unqualified access|inheritance-cycle|is part of an inheritance cycle|Type BarWidget is used but it is not resolved|Quickshell|QLocalSocket|signal-handler-parameters|unknown grouped property scope anchors'

status=0
shopt -s nullglob
files=("$REPO_ROOT"/*.qml)
if (( ${#files[@]} == 0 )); then
  echo "lint-qml: no .qml files found in $REPO_ROOT" >&2
  exit 1
fi

for f in "${files[@]}"; do
  # -I . so sibling plugin components (SplitBar, Sparkline, ...) resolve.
  out=$("$QMLLINT" -I "$IMPORT_ROOT" -I "$REPO_ROOT" "$f" 2>&1 \
        | grep -E '^(Error|Warning)' \
        | grep -Ev "$IGNORE_RE")
  if [[ -n $out ]]; then
    echo "--- $(basename "$f")"
    echo "$out"
    status=1
  fi
done

if (( status == 0 )); then
  echo "lint-qml: ${#files[@]} file(s) clean against $SHELL_DIR"
else
  echo "lint-qml: FAILED -- see above" >&2
fi
exit $status
