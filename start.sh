#!/bin/bash

DIR="$(cd "$(dirname "$0")" && pwd)"

# 弹出可视化选择窗口（列表 + Cancel / Confirm）
PROJ_COUNT=$(osascript <<'APPLESCRIPT'
set chosen to choose from list {"1", "2"} ¬
    with title "Infoglut Launcher" ¬
    with prompt "How many Projectors would you like to launch?" ¬
    default items {"1"} ¬
    OK button name "Confirm" ¬
    cancel button name "Cancel" ¬
    without multiple selections allowed and empty selection allowed
if chosen is false then
    return ""
else
    return item 1 of chosen
end if
APPLESCRIPT
)

# 用户点 Cancel 则退出
if [[ -z "$PROJ_COUNT" ]]; then
    exit 0
fi

open -a Terminal "$DIR"
sleep 0.5

if [[ "$PROJ_COUNT" == "2" ]]; then
    osascript <<EOF
tell application "Terminal"
    do script "cd \"$DIR\" && python3 projector.py 12345"
    do script "cd \"$DIR\" && python3 projector.py 12346"
    do script "cd \"$DIR\" && python3 server.py 2"
    do script "cd \"$DIR\" && python3 tunnel_qr.py"
end tell
EOF
else
    osascript <<EOF
tell application "Terminal"
    do script "cd \"$DIR\" && python3 projector.py 12345"
    do script "cd \"$DIR\" && python3 server.py 1"
    do script "cd \"$DIR\" && python3 tunnel_qr.py"
end tell
EOF
fi
