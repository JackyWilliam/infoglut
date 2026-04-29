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
# AI 小方框最新内容 + 情感
# =========================
latest_ai_text = "..."
latest_ai_mood = "numb"
latest_ai_lock = threading.Lock()

ALLOWED_MOODS = {
    "numb", "tired", "sad", "anxious",
    "angry", "amused", "curious", "disgusted",
}
DEFAULT_MOOD = "numb"

# =========================
# 气量状态（0.0 ~ 1.0）
# 由 PUMP 累加、VALVE 衰减、自然漏气慢慢回到 0
# =========================
air_level = 0.0
air_lock = threading.Lock()

PUMP_FULL_MS = 30000          # 累计 PUMP 多少 ms 把屏幕从空充满（拉大 = 屏幕膨胀更慢，匹配气球物理速度）
VALVE_FULL_MS = 80000         # 累计 VALVE 多少 ms 把屏幕从满放空（缩屏比 PUMP 膨胀略小一点）
NATURAL_LEAK_PER_SEC = 0.0    # 气球本身不漏；屏幕只在脏话/idle 自动放气时缩
AIR_BROADCAST_INTERVAL = 0.2  # 广播周期（秒）

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>INFOGLUT</title>
    <style>
        * { box-sizing: border-box; }
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background: #000;
            color: #fff;
            font-family: "SF Mono", "JetBrains Mono", "Menlo", "Consolas", monospace;
            overflow: hidden;
            user-select: none;
            -webkit-user-select: none;
            -webkit-tap-highlight-color: transparent;
            -webkit-touch-callout: none;
        }
        /* iOS：input 必须显式允许选中/输入，否则 user-select:none 父级会让它失焦 */
        input, textarea, button {
            user-select: text;
            -webkit-user-select: text;
            touch-action: manipulation;
        }
        button {
            user-select: none;
            -webkit-user-select: none;
        }
        body {
            background-image: radial-gradient(ellipse at center, #0a0a0a 0%, #000 70%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            padding: 56px 24px 40px;
        }
        /* 极弱 SVG 噪点：信息粒子感 */
        body::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.6'/></svg>");
            opacity: 0.05;
            mix-blend-mode: screen;
            z-index: 1;
        }

        .top, .mid, .bottom {
            position: relative;
            z-index: 2;
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .logo {
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 10px;
            color: #888;
            margin-bottom: 10px;
        }
        .sub {
            font-size: 10px;
            letter-spacing: 3px;
            color: #3a3a3a;
            text-transform: uppercase;
        }

        .mid {
            max-width: 360px;
        }

        input[type="text"] {
            width: 100%;
            padding: 16px 0;
            font-size: 18px;
            color: #fff;
            background: transparent;
            border: none;
            border-bottom: 1px solid #2a2a2a;
            text-align: center;
            outline: none;
            font-family: inherit;
            transition: border-color 250ms ease;
            caret-color: #fff;
        }
        input[type="text"]:focus {
            border-bottom-color: #ddd;
        }
        input::placeholder {
            color: #2f2f2f;
            letter-spacing: 1px;
        }

        button {
            margin-top: 22px;
            width: 100%;
            background: #fff;
            color: #000;
            padding: 14px 0;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 6px;
            border: none;
            cursor: pointer;
            font-family: inherit;
            text-transform: uppercase;
            transition: opacity 200ms ease, transform 80ms ease;
        }
        button:active {
            transform: scale(0.985);
        }
        button:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }

        #aiBox {
            width: 100%;
            max-width: 440px;
            min-height: 180px;
            padding: 22px 0 8px;
            border-top: 1px solid #161616;
            text-align: center;
        }
        .ai-label {
            font-size: 10px;
            letter-spacing: 6px;
            color: #3a3a3a;
            margin-bottom: 18px;
            text-transform: uppercase;
            transition: color 600ms ease;
        }
        #aiText {
            font-size: 26px;
            line-height: 1.45;
            color: #b8b8b8;
            letter-spacing: 0.4px;
            min-height: 38px;
            word-break: break-word;
            opacity: 0.95;
            transition: opacity 350ms ease, color 600ms ease;
        }
        #aiText.refresh {
            opacity: 0;
        }
        /* mood → 颜色 */
        body.mood-numb       #aiText { color: #b8b8b8; }
        body.mood-tired      #aiText { color: #8a8aa0; }
        body.mood-sad        #aiText { color: #6f9eff; }
        body.mood-anxious    #aiText { color: #ff9c50; }
        body.mood-angry      #aiText { color: #ff5252; }
        body.mood-amused     #aiText { color: #f5d76e; }
        body.mood-curious    #aiText { color: #c490ff; }
        body.mood-disgusted  #aiText { color: #9bb84a; }
        /* mood label 同色但暗 */
        body.mood-numb       .ai-label { color: #555; }
        body.mood-tired      .ai-label { color: #555568; }
        body.mood-sad        .ai-label { color: #3d5a96; }
        body.mood-anxious    .ai-label { color: #8a5530; }
        body.mood-angry      .ai-label { color: #8a3030; }
        body.mood-amused     .ai-label { color: #8a7838; }
        body.mood-curious    .ai-label { color: #6a4f8a; }
        body.mood-disgusted  .ai-label { color: #5a6a30; }
        /* 闪烁光标，呼应"还在想" */
        #aiText::after {
            content: "_";
            color: #555;
            margin-left: 4px;
            animation: blink 1.1s steps(1) infinite;
        }
        @keyframes blink {
            0%, 50% { opacity: 1; }
            50.01%, 100% { opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="top">
        <div class="logo">INFOGLUT</div>
        <div class="sub">say something. anything.</div>
    </div>

    <div class="mid">
        <input type="text" id="msg" placeholder="..." autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
        <button id="sendBtn" onclick="sendData()">SEND</button>
    </div>

    <div class="bottom">
        <div id="aiBox">
            <div class="ai-label" id="aiLabel">THOUGHT</div>
            <div id="aiText">...</div>
        </div>
    </div>

    <script>
        const aiTextEl = document.getElementById('aiText');
        const aiLabelEl = document.getElementById('aiLabel');
        let lastAiText = "";
        let lastMood = "numb";
        document.body.classList.add("mood-numb");

        function sendData() {
            const input = document.getElementById('msg');
            const btn = document.getElementById('sendBtn');
            const text = input.value.trim();
            if (!text) return;

            btn.disabled = true;
            const original = btn.innerText;
            btn.innerText = "···";

            fetch('/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'message=' + encodeURIComponent(text)
            }).then(() => {
                input.value = '';
                btn.innerText = "OK";
                setTimeout(() => {
                    btn.innerText = original;
                    btn.disabled = false;
                }, 700);
            }).catch(() => {
                btn.innerText = "RETRY";
                setTimeout(() => {
                    btn.innerText = original;
                    btn.disabled = false;
                }, 1200);
            });
        }

        const ALL_MOODS = ["numb","tired","sad","anxious","angry","amused","curious","disgusted"];

        function applyMood(mood) {
            const m = ALL_MOODS.includes(mood) ? mood : "numb";
            if (m === lastMood) return;
            ALL_MOODS.forEach(x => document.body.classList.remove("mood-" + x));
            document.body.classList.add("mood-" + m);
            aiLabelEl.innerText = m.toUpperCase();
            lastMood = m;
        }

        function refreshAIText() {
            fetch('/ai_latest')
                .then(res => res.json())
                .then(data => {
                    if (data.text === undefined) return;
                    const newMood = data.mood || "numb";
                    if (data.text === lastAiText && newMood === lastMood) return;
                    lastAiText = data.text;
                    aiTextEl.classList.add('refresh');
                    setTimeout(() => {
                        aiTextEl.innerText = data.text || "...";
                        applyMood(newMood);
                        aiTextEl.classList.remove('refresh');
                    }, 350);
                })
                .catch(() => {});
        }

        document.addEventListener("DOMContentLoaded", function () {
            const input = document.getElementById("msg");
            input.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    sendData();
                }
            });
            refreshAIText();
            setInterval(refreshAIText, 1500);
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


def set_latest_ai(text: str, mood: str):
    global latest_ai_text, latest_ai_mood
    with latest_ai_lock:
        latest_ai_text = text
        latest_ai_mood = mood if mood in ALLOWED_MOODS else DEFAULT_MOOD


def get_latest_ai():
    with latest_ai_lock:
        return latest_ai_text, latest_ai_mood


def add_air(duration_ms: int):
    global air_level
    with air_lock:
        air_level = min(1.0, air_level + duration_ms / PUMP_FULL_MS)


def release_air(duration_ms: int):
    global air_level
    with air_lock:
        air_level = max(0.0, air_level - duration_ms / VALVE_FULL_MS)


def get_air_level() -> float:
    with air_lock:
        return air_level


def air_loop():
    global air_level
    while True:
        time.sleep(AIR_BROADCAST_INTERVAL)
        with air_lock:
            air_level = max(0.0, air_level - NATURAL_LEAK_PER_SEC * AIR_BROADCAST_INTERVAL)
            level = air_level
        send_to_all_projectors(f"AIR::{level:.4f}")


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


def generate_ai_text(user_text: str):
    """Returns (text, mood)."""
    if not client:
        return ("whatever", DEFAULT_MOOD)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You're someone whose brain has been melted by endless scrolling. "
                        "Each time someone speaks, you blurt out a short fragment that loosely relates, "
                        "along with the emotional color of that fragment.\n\n"
                        "Output format (exactly two lines, nothing else):\n"
                        "<mood>\n"
                        "<fragment>\n\n"
                        "<mood> is one word, picked from: numb, tired, sad, anxious, angry, amused, curious, disgusted.\n"
                        "<fragment> is 1-6 English words. No emoji, no quotes, no end punctuation.\n\n"
                        "Stay loosely on topic. Don't fully answer, don't comfort, don't summarize, don't make a point."
                    )
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            max_tokens=20,
            temperature=1.1
        )

        raw = response.choices[0].message.content.strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        if len(lines) >= 2:
            mood = lines[0].lower().strip(" .:-")
            text = lines[1].strip(" \"'")
        elif len(lines) == 1:
            mood = DEFAULT_MOOD
            text = lines[0].strip(" \"'")
        else:
            return ("whatever", DEFAULT_MOOD)

        if mood not in ALLOWED_MOODS:
            mood = DEFAULT_MOOD
        if not text:
            text = "whatever"

        return (text, mood)

    except Exception as e:
        print(f"OpenAI 生成失败: {e}")
        return ("whatever", DEFAULT_MOOD)


def trigger_ai_once_from_message(user_msg: str, trigger_pump: bool = True):
    def worker():
        time.sleep(1.0)  # 稍微停一下，更像"想了一下"

        ai_text, ai_mood = generate_ai_text(user_msg)
        set_latest_ai(ai_text, ai_mood)

        print(f"[AI] {ai_mood} :: {ai_text}")

        send_to_all_projectors(f"AI::{ai_mood}::{ai_text}")

        if trigger_pump:
            send_to_arduino("PUMP:300\n")
            add_air(300)

    threading.Thread(target=worker, daemon=True).start()


@app.route('/')
def index():
    return render_template_string(HTML_PAGE)


@app.route('/ai_latest', methods=['GET'])
def ai_latest():
    text, mood = get_latest_ai()
    return jsonify({
        "text": text,
        "mood": mood,
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
        release_air(duration)

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
    add_air(duration)

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
        release_air(duration)


if __name__ == '__main__':
    print("服务器已启动")

    # 后台持续尝试重连 Arduino
    threading.Thread(target=reconnect_arduino_loop, daemon=True).start()

    # 3小时展览计时，自动偶发放气
    threading.Thread(target=idle_valve_loop, daemon=True).start()

    # 气量广播：每 200ms 衰减 + UDP 广播 air_level 给 projector
    threading.Thread(target=air_loop, daemon=True).start()

    app.run(host='0.0.0.0', port=8080)
