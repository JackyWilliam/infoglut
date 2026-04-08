@echo off
start "Projector 1" cmd /k "cd /d %~dp0 && python projector.py 12345"
start "Projector 2" cmd /k "cd /d %~dp0 && python projector.py 12346"
start "Server"      cmd /k "cd /d %~dp0 && python server.py"
start "Tunnel"      cmd /k "cd /d %~dp0 && python tunnel_qr.py"
