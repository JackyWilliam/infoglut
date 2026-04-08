# Infoglut

一个互动艺术装置——观众通过手机发送文字，消息实时投影到物理表面，并触发 AI 生成反应和 Arduino 控制的气动装置。

> **平台：macOS / Windows。** macOS 使用 `start.sh`，Windows 使用 `start.bat`。

## 架构

```
观众（手机） → Flask 服务器 (server.py) → UDP → 投影仪 × 2 (projector.py)
                                         ↓
                                     Arduino（气泵 / 阀门）
                                         ↓
                                     AI 反应 (GPT-4o-mini)
```

- **server.py** — Flask Web 服务器（端口 8080）。接收观众文字，判断是否有害，通过 UDP 发送给两台投影仪，触发 Arduino，并调用 AI 生成反应。
- **projector.py** — Pygame 全屏显示端。接收 UDP 消息，将浮动文字渲染到 Coons patch 曲面变形的投影画面上。每台投影仪运行一个实例。
- **tunnel_qr.py** — 启动 Cloudflare 隧道将本地服务器暴露到公网，自动生成并打开二维码供观众扫码。

## 环境配置

### 1. 前置工具

| 工具 | 版本 | 备注 |
|------|------|------|
| Python | 3.11+ | 开发环境使用 3.14 |
| Node.js | 18+ | 运行 `npx cloudflared` 需要 |
| Arduino IDE | 任意 | 仅烧录固件时需要 |

**macOS** — 通过 [Homebrew](https://brew.sh) 安装

```bash
brew install python node
```

**Windows** — 通过 [winget](https://learn.microsoft.com/zh-cn/windows/package-manager/) 安装

```powershell
winget install Python.Python.3 OpenJS.NodeJS
```

---

### 2. Python 虚拟环境

**macOS**
```bash
cd /path/to/Infoglut
python3 -m venv venv
source venv/bin/activate
```

**Windows**
```powershell
cd C:\path\to\Infoglut
python -m venv venv
venv\Scripts\activate
```

> 每次打开新终端，都需要先激活虚拟环境再启动项目。

---

### 3. 安装 Python 依赖

```bash
pip install flask pygame-ce numpy pyserial openai python-dotenv safetext
```

主要依赖说明：

| 包名 | 用途 |
|------|------|
| `flask` | 观众输入页面的 Web 服务器 |
| `pygame-ce` | 投影仪渲染（社区版） |
| `numpy` | Coons patch 曲面数学计算 |
| `pyserial` | Arduino 串口通信 |
| `openai` | GPT-4o-mini AI 反应生成 |
| `python-dotenv` | 读取 `.env` 配置文件 |
| `safetext` | 英文脏话检测 |

---

### 4. Cloudflare 隧道

```bash
# 全局安装一次（需要 Node.js）
npm install -g cloudflared

# 验证安装
cloudflared --version
```

如果 `npx cloudflared` 失败，也可以直接从 [Cloudflare 官网](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 下载二进制文件安装。

---

### 5. OpenAI API Key

在项目根目录创建 `.env` 文件：

**macOS**
```bash
echo "OPENAI_API_KEY=sk-..." > .env
```

**Windows**
```powershell
"OPENAI_API_KEY=sk-..." | Out-File .env -Encoding utf8
```

或者直接用任意文本编辑器新建 `.env`，写入：
```
OPENAI_API_KEY=sk-...
```

没有此 Key 服务器仍可运行，AI 反应会退回固定文本 `"I kept thinking about that."`。

---

### 6. Arduino

- 启动服务器前先通过 USB 连接 Arduino。
- 端口自动识别（搜索描述中含 `usbmodem` 或 `arduino` 的端口）。
- 若识别失败，启动时终端会打印所有可用端口，可在 `server.py` 的 `find_arduino_port()` 中手动指定。
- 波特率：**9600**

---

### 7. 首次运行

**macOS**
```bash
chmod +x start.sh
source venv/bin/activate
./start.sh
```
通过 AppleScript 自动打开四个 Terminal 标签页。

**Windows**
```powershell
venv\Scripts\activate
start.bat
```
自动打开四个命令提示符窗口。

---

## 快速启动

**macOS**
```bash
source venv/bin/activate
python3 projector.py 12345   # 终端 1 — 投影仪 1
python3 projector.py 12346   # 终端 2 — 投影仪 2
python3 server.py            # 终端 3 — 服务器
python3 tunnel_qr.py         # 终端 4 — 隧道 + 二维码
```

**Windows**
```powershell
venv\Scripts\activate
python projector.py 12345    # 终端 1 — 投影仪 1
python projector.py 12346    # 终端 2 — 投影仪 2
python server.py             # 终端 3 — 服务器
python tunnel_qr.py          # 终端 4 — 隧道 + 二维码
```

观众扫描弹出的二维码，在手机上打开输入页面即可参与。

Arduino 自动检测，若未找到则仅投影文字，不触发气动装置。

## 投影仪快捷键

| 按键 | 功能 |
|------|------|
| `F` | 切换全屏 / 窗口模式 |
| `C` | 显示 / 隐藏编辑器叠加层 |
| `S` | 打印当前控制点坐标到终端 |
| `H` | 水平镜像 |
| `V` | 垂直镜像 |
| `[` / `]` | 增大 / 减小条带宽度（越小越精细，越吃 CPU） |
| `ESC` | 退出 |

在编辑器叠加层中拖拽蓝色控制点，可将投影画面变形以贴合物理投影表面。

## 消息行为

- **普通消息** → 白色浮动文字随机出现在某台投影仪上，气泵脉冲（时长随消息长度变化）
- **有害消息** → 红色抖动文字 + 阀门放气（消息越长放气越久）
- **AI 反应** → GPT-4o-mini 生成简短直接的回应，显示在两台投影仪的「THOUGHT」框中

---

© 2026 Yijie Ding. All rights reserved.
