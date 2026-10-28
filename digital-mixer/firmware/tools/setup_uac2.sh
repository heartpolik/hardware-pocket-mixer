#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Local copy of the Teensy Arduino framework with the UAC2 core files of grrrr/teensy-4-usbAudio
# (MIT, fork of alex6679) for `pio run -e uac2`: 8 USB channels, 48 kHz. The global PlatformIO
# framework stays untouched. Usage (from firmware/):  sh tools/setup_uac2.sh [framework dir]
set -e
cd "$(dirname "$0")/.."
REV=e84237913bc8848f239d7994d812606bcb30f7c2          # tested revision
FW=${1:-$HOME/.platformio/packages/framework-arduinoteensy}
EXT=tools/ext
[ -d "$EXT/teensy-4-usbAudio/.git" ] || git clone -q https://github.com/grrrr/teensy-4-usbAudio.git "$EXT/teensy-4-usbAudio"
(cd "$EXT/teensy-4-usbAudio" && git fetch -q --depth 1 origin "$REV" 2>/dev/null; git checkout -q "$REV")
rm -rf "$EXT/framework-teensy-uac2"
cp -Rc "$FW" "$EXT/framework-teensy-uac2" 2>/dev/null || cp -R "$FW" "$EXT/framework-teensy-uac2"
cp -R "$EXT/teensy-4-usbAudio/changedCorefiles/"* "$EXT/framework-teensy-uac2/cores/teensy4/"
echo "UAC2 framework: $EXT/framework-teensy-uac2 (from $FW, usbAudio $REV)"
