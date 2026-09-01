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
#
# WHAT FAILS THE BUILD
# --------------------
# Only the diagnostics that mean "this file will not load in the shell":
# syntax errors, and the `missing-property` / `missing-type` / `missing-enum`
# families. Everything else is printed as advisory and does not fail.
#
# That distinction is deliberate. qmllint's warning set changes between Qt
# releases -- a developer machine on Qt 6.11 and an ubuntu-latest runner on
# Qt 6.4 do not agree on the advisory categories -- so gating on "zero
# warnings" makes the check fail for reasons that have nothing to do with this
# plugin. The load-blocking categories are stable, and are the ones that would
# have caught the bug above.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SHELL_DIR="${OMARCHY_SHELL_DIR:-/usr/share/omarchy/shell}"

QMLLINT="${QMLLINT:-}"
if [[ -z $QMLLINT ]]; then
  for candidate in qmllint qmllint6 /usr/lib/qt6/bin/qmllint \
                   /usr/lib/qt6/bin/qmllint6 /usr/lib/qt6/libexec/qmllint; do
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

echo "lint-qml: $QMLLINT ($("$QMLLINT" --version 2>&1 | head -1))"
echo "lint-qml: shell types from $SHELL_DIR"

# Quickshell exposes the shell tree under the `qs` module prefix, so qmllint
# needs an import root that *contains* a directory named `qs`.
IMPORT_ROOT=$(mktemp -d)
trap 'rm -rf "$IMPORT_ROOT"' EXIT
ln -s "$SHELL_DIR" "$IMPORT_ROOT/qs"

# Diagnostics that mean the file will not load. These fail the build.
FATAL_RE='\[(missing-property|missing-type|missing-enum)\]|^Error:'

# Known-good noise, excluded even from the fatal set. Each of these is
# reproduced by the Omarchy shell's OWN sources -- verified by running qmllint
# over shell/Ui/Toggle.qml -- so they are qmllint limitations, not defects:
#
#   * 'not found on type "QObject"' -- Style.font / Style.spacing are inline
#     `QtObject { ... }` sub-objects, which qmllint types as bare QObject and
#     therefore cannot see the tokens inside. This is a `missing-property`,
#     which is why it has to be excluded by MESSAGE rather than by category.
#   * BarWidget -- our BarWidget.qml extends the shell type of the same name,
#     which the resolver reads as an inheritance cycle.
#   * 'Unqualified access' -- referring to an outer id from inside a Component
#     or a Repeater delegate. Legal QML, used throughout the shell's own code.
#   * Quickshell's own C++ types are not introspectable from qmllint.
IGNORE_RE='not found on type "QObject"|Unqualified access|inheritance cycle|Type BarWidget is used but it is not resolved|Quickshell|QLocalSocket'

status=0
advisory=0
shopt -s nullglob
files=("$REPO_ROOT"/*.qml)
if (( ${#files[@]} == 0 )); then
  echo "lint-qml: no .qml files found in $REPO_ROOT" >&2
  exit 1
fi

for f in "${files[@]}"; do
  raw=$("$QMLLINT" -I "$IMPORT_ROOT" -I "$REPO_ROOT" "$f" 2>&1 \
        | grep -E '^(Error|Warning)' | grep -Ev "$IGNORE_RE")
  [[ -z $raw ]] && continue

  fatal=$(echo "$raw" | grep -E "$FATAL_RE")
  if [[ -n $fatal ]]; then
    echo "FAIL $(basename "$f")"
    echo "$fatal" | sed 's/^/     /'
    status=1
  fi

  rest=$(echo "$raw" | grep -Ev "$FATAL_RE")
  if [[ -n $rest ]]; then
    advisory=$((advisory + $(echo "$rest" | wc -l)))
    echo "note $(basename "$f")"
    echo "$rest" | sed 's/^/     /'
  fi
done

echo
if (( status == 0 )); then
  echo "lint-qml: OK -- ${#files[@]} file(s), no load-blocking diagnostics${advisory:+ ($advisory advisory)}"
else
  echo "lint-qml: FAILED -- load-blocking diagnostics above" >&2
fi
exit $status
