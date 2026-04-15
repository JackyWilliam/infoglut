from flask import Flask, request, render_template_string, jsonify
import socket
import sys
import serial
import time
import threading
import random
import os
from safetext import SafeText
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

# =========================
# OpenAI 配置
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# =========================
# Arduino 串口配置
# =========================
BAUD_RATE = 9600

def find_arduino_port():
    import serial.tools.list_ports
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        name = (p.device or "").lower()
        if "usbmodem" in name or "arduino" in desc or "usbmodem" in desc:
            print(f"自动识别到 Arduino 端口: {p.device} ({p.description})")
            return p.device
    print("未找到 Arduino 端口，已扫描端口如下:")
    for p in ports:
        print(f"  {p.device} - {p.description}")
    return None

ARDUINO_PORT = find_arduino_port()

arduino = None
arduino_lock = threading.Lock()

# =========================
# UDP 配置（端口数量由命令行参数决定，默认2个）
# =========================
UDP_IP = "127.0.0.1"
_proj_count = int(sys.argv[1]) if len(sys.argv) > 1 else 2
PROJECTOR_PORTS = [12345] if _proj_count == 1 else [12345, 12346]
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# =========================
# SafeText：只保留英文
# =========================
st_en = SafeText(language='en')

# 中文和补充英文词库继续手动维护
CUSTOM_HARM_WORDS = [
    # English
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard",
    "kill", "die", "idiot", "moron", "stupid", "trash",
    "kill yourself", "go die",

    # Chinese
    "操", "草", "妈的", "他妈", "你妈", "傻逼", "傻b", "傻比",
    "智障", "弱智", "废物", "去死", "滚", "白痴", "贱人"
]

# =========================
# AI 小方框最新内容
# =========================
latest_ai_text = "..."
latest_ai_lock = threading.Lock()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Infoglut Interactive</title>
    <style>
        body {
            background-color: #000;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            overflow: hidden;
        }
        .logo {
            font-size: 28px;
            font-weight: bold;
            letter-spacing: 6px;
            margin-bottom: 50px;
            color: #aaa;
        }
        input {
            width: 80%;
            max-width: 320px;
            padding: 18px 24px;
            font-size: 20px;
            border-radius: 16px;
            border: 1px solid #333;
            background-color: #111;
            color: white;
            text-align: center;
            outline: none;
            margin-bottom: 30px;
            transition: all 0.3s ease;
        }
        input:focus {
            border-color: #888;
            background-color: #1a1a1a;
        }
        input::placeholder {
            color: #555;
        }
        button {
            background-color: #fff;
            color: #000;
            padding: 18px 48px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 16px;
            border: none;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.3s;
        }
        button:active {
            transform: scale(0.96);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        #aiBox {
            margin-top: 28px;
            width: 80%;
            max-width: 420px;
            min-height: 88px;
            padding: 16px 18px;
            border-radius: 10px;
            border: 1px solid #1f3552;
            background-color: #05080d;
            color: #9ec5ff;
            box-shadow: inset 0 0 12px rgba(80, 140, 255, 0.08);
            box-sizing: border-box;
            text-align: left;
        }

        .ai-label {
            font-size: 12px;
            letter-spacing: 2px;
            color: #666;
            margin-bottom: 10px;
        }

        #aiText {
            font-size: 16px;
            line-height: 1.5;
            color: #6fa8ff;
            word-break: break-word;
            min-height: 24px;
        }
    </style>
</head>
<body>
    <div class="logo">INFOGLUT</div>
    <input type="text" id="msg" placeholder="Type your message..." autocomplete="off">
    <button id="sendBtn" onclick="sendData()">Send</button>

    <div id="aiBox">
        <div class="ai-label">THOUGHT</div>
        <div id="aiText">...</div>
    </div>

    <script>
        function sendData() {
            let input = document.getElementById('msg');
            let btn = document.getElementById('sendBtn');
            let text = input.value.trim();
            if (!text) return;

            btn.disabled = true;
            let originalText = btn.innerText;
            btn.innerText = "Sending...";

            fetch('/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'message=' + encodeURIComponent(text)
            }).then(async (res) => {
                const data = await res.json();

                input.value = '';

                if (data.arduino_connected) {
                    btn.innerText = "Sent!";
                } else {
                    btn.innerText = "No Arduino";
                }

                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.disabled = false;
                }, 1500);
            }).catch(err => {
                btn.innerText = "Error";
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.disabled = false;
                }, 1500);
            });
        }

        function refreshAIText() {
            fetch('/ai_latest')
                .then(res => res.json())
                .then(data => {
                    const aiTextEl = document.getElementById('aiText');
                    if (aiTextEl && data.text !== undefined) {
                        aiTextEl.innerText = data.text;
                    }
                })
                .catch(err => {
                    console.log("AI text fetch error:", err);
                });
        }

        document.addEventListener("DOMContentLoaded", function () {
            const input = document.getElementById("msg");
            input.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    sendData();
                }
            });

            refreshAIText();
            setInterval(refreshAIText, 1200);
        });
    </script>
</body>
</html>
"""

def get_pump_duration(text: str) -> int:
    length = len(text)

    if length <= 5:
        return 500
    elif length <= 15:
        return 1000
    elif length <= 30:
        return 1800
    else:
        return 2500


def get_valve_duration(text: str) -> int:
    length = len(text)

    if length <= 5:
        return 1500
    elif length <= 15:
        return 2500
    elif length <= 30:
        return 3500
    else:
        return 5000


def contains_custom_harm_word(text: str) -> bool:
    lower_text = text.lower()
    for word in CUSTOM_HARM_WORDS:
        if word in lower_text:
            return True
    return False


def sdk_detect_harmful_text(text: str) -> bool:
    if contains_custom_harm_word(text):
        return True

    try:
        en_result = st_en.check_profanity(text=text)
        if en_result:
            return True
    except Exception as e:
        print(f"SafeText detection error: {e}")

    return False


def set_latest_ai_text(text: str):
    global latest_ai_text
    with latest_ai_lock:
        latest_ai_text = text


def get_latest_ai_text():
    with latest_ai_lock:
        return latest_ai_text


def connect_arduino():
    global arduino

    with arduino_lock:
        if arduino is not None:
            try:
                if arduino.is_open:
                    return True
            except Exception:
                arduino = None

        port = find_arduino_port()
        if port is None:
            print("Arduino 未找到，跳过连接")
            return False

        try:
            print(f"尝试连接 Arduino: {port}")
            arduino = serial.Serial(port, BAUD_RATE, timeout=1)
            time.sleep(2)  # 给 Arduino 重启时间
            print("成功连接到 Arduino 气泵执行器")
            return True
        except Exception as e:
            arduino = None
            print(f"Arduino 未连接: {e}")
            return False


def reconnect_arduino_loop():
    while True:
        if arduino is None:
            connect_arduino()
        time.sleep(3)


def send_to_projector(payload: str, port: int):
    try:
        sock.sendto(payload.encode('utf-8'), (UDP_IP, port))
    except Exception as e:
        print(f"发送到投影端失败 (port {port}): {e}")


def send_to_all_projectors(payload: str):
    for port in PROJECTOR_PORTS:
        send_to_projector(payload, port)


def send_to_random_projector(payload: str):
    port = random.choice(PROJECTOR_PORTS)
    print(f"[UDP] -> projector:{port} {payload}")
    send_to_projector(payload, port)


def send_to_arduino(command: str) -> bool:
    global arduino

    # 如果当前没连上，先尝试连一次
    if arduino is None:
        connect_arduino()

    if arduino is None:
        print("Arduino 未连接，消息只发送到投影端")
        return False

    with arduino_lock:
        try:
            print(f"发送给 Arduino 的命令: {command.strip()}")
            arduino.write(command.encode('utf-8'))
            arduino.flush()
            return True
        except Exception as e:
            print(f"发送到 Arduino 失败: {e}")
            try:
                arduino.close()
            except Exception:
                pass
            arduino = None
            return False


def generate_ai_text(user_text: str) -> str:
    if not client:
        return "I kept thinking about that."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You've seen too much online and you can't stop reacting. "
                        "When someone says something, you just blurt out the first thing that comes to mind — "
                        "direct, blunt, casual. "
                        "Reply with one short reaction: specific, under 10 words. "
                        "Mostly just honest and unfiltered. Swear only rarely, when it really fits. "
                        "No poetic bullshit. No full sentences needed. "
                        "Just the raw reaction."
                    )
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            max_tokens=25,
            temperature=1.1
        )

        ai_text = response.choices[0].message.content.strip()
        ai_text = ai_text.replace("\\n", " ").strip()

        if not ai_text:
            return "I kept thinking about that."

        return ai_text

    except Exception as e:
        print(f"OpenAI 生成失败: {e}")
        return "I kept thinking about that."


def trigger_ai_once_from_message(user_msg: str, trigger_pump: bool = True):
    def worker():
        time.sleep(1.0)  # 稍微停一下，更像"想了一下"

        ai_text = generate_ai_text(user_msg)
        set_latest_ai_text(ai_text)

        print(f"[AI] {ai_text}")

        send_to_all_projectors(f"AI::{ai_text}")

        if trigger_pump:
            duration = get_pump_duration(ai_text)
            send_to_arduino(f"PUMP:{duration}\n")

    threading.Thread(target=worker, daemon=True).start()


@app.route('/')
def index():
    return render_template_string(HTML_PAGE)


@app.route('/ai_latest', methods=['GET'])
def ai_latest():
    return jsonify({
        "text": get_latest_ai_text()
    })


@app.route('/send', methods=['POST'])
def send():
    msg = request.form.get('message', '').strip()

    if not msg:
        return jsonify({
            "status": "empty",
            "message": "No content",
            "arduino_connected": arduino is not None
        })

    print(f"Web 端收到观众文字: {msg}")

    is_bad = sdk_detect_harmful_text(msg)

    if is_bad:
        duration = get_valve_duration(msg)
        print("检测到脏话/伤害性语言")
        send_to_random_projector(f"BAD::{msg}")
        arduino_ok = send_to_arduino(f"VALVE:{duration}\n")

        trigger_ai_once_from_message(msg, trigger_pump=False)

        return jsonify({
            "status": "success",
            "type": "bad",
            "duration": duration,
            "arduino_connected": arduino_ok
        })

    duration = get_pump_duration(msg)
    send_to_random_projector(f"NORMAL::{msg}")
    arduino_ok = send_to_arduino(f"PUMP:{duration}\n")

    # 每条用户消息后，AI 只触发一次
    trigger_ai_once_from_message(msg)

    return jsonify({
        "status": "success",
        "type": "normal",
        "duration": duration,
        "arduino_connected": arduino_ok
    })


SHOW_DURATION = 3 * 60 * 60  # 3小时，单位秒
show_start_time = None


def idle_valve_loop():
    global show_start_time
    # 等服务器完全启动后再开始计时
    time.sleep(5)
    show_start_time = time.time()
    print("[计时器] 展览开始，3小时计时启动")

    while True:
        elapsed = time.time() - show_start_time
        if elapsed >= SHOW_DURATION:
            print("[计时器] 3小时展览结束，停止自动放气")
            break

        # 随机等待 45~75 秒后悄悄放一次气
        wait = random.uniform(45, 75)
        time.sleep(wait)

        # 再次确认还在展览时间内
        if time.time() - show_start_time >= SHOW_DURATION:
            break

        # 短暂放气，300~800ms，悄悄的
        duration = random.randint(1000, 2000)
        print(f"[自动放气] 静默释放 {duration}ms")
        send_to_arduino(f"VALVE:{duration}\n")


if __name__ == '__main__':
    print("服务器已启动")

    # 后台持续尝试重连 Arduino
    threading.Thread(target=reconnect_arduino_loop, daemon=True).start()

    # 3小时展览计时，自动偶发放气
    threading.Thread(target=idle_valve_loop, daemon=True).start()

    app.run(host='0.0.0.0', port=8080)
