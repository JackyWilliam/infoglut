#!/bin/bash

DIR="$(cd "$(dirname "$0")" && pwd)"

open -a Terminal "$DIR"
sleep 0.5

osascript <<EOF
tell application "Terminal"
    do script "cd \"$DIR\" && python3 projector.py 12345"
    do script "cd \"$DIR\" && python3 projector.py 12346"
    do script "cd \"$DIR\" && python3 server.py"
    do script "cd \"$DIR\" && python3 tunnel_qr.py"
end tell
EOF
