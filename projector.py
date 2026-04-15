import sys
import socket
import threading
import random
import math
import time
import queue

import pygame
import pygame.freetype
import numpy as np

# =========================
# UDP 配置（端口可通过命令行参数指定）
# =========================
UDP_IP = "0.0.0.0"
UDP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 12345

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.setblocking(False)

# =========================
# Pygame 初始化
# =========================
pygame.init()
pygame.freetype.init()

# 调试时你可以改成 False
USE_FULLSCREEN = True

info = pygame.display.Info()
SCREEN_W = info.current_w
SCREEN_H = info.current_h

# Retina HiDPI：用 CoreGraphics 读取实际物理像素（无需额外依赖）
try:
    import ctypes
    _cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    _cg.CGMainDisplayID.restype = ctypes.c_uint32
    _cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
    _cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
    _cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
    _cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
    _display = _cg.CGMainDisplayID()
    SCREEN_W = int(_cg.CGDisplayPixelsWide(_display))
    SCREEN_H = int(_cg.CGDisplayPixelsHigh(_display))
    print(f"[HiDPI] CoreGraphics render resolution={SCREEN_W}x{SCREEN_H}")
except Exception as e:
    print(f"[HiDPI] CoreGraphics unavailable ({e}), using {SCREEN_W}x{SCREEN_H}")

if USE_FULLSCREEN:
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
else:
    SCREEN_W, SCREEN_H = 1280, 720
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

pygame.display.set_caption("Infoglut Projector - CPU Warp Stable")

clock = pygame.time.Clock()

# =========================
# 内容画布（2x 超采样：以双倍分辨率渲染，warp 时缩回屏幕尺寸，提升清晰度）
# =========================
SUPERSAMPLE = 2
CONTENT_W = SCREEN_W * SUPERSAMPLE
CONTENT_H = SCREEN_H * SUPERSAMPLE
CONTENT_SCALE = CONTENT_W / 1024  # 字体/间距缩放系数
content_surface = pygame.Surface((CONTENT_W, CONTENT_H), pygame.SRCALPHA)

# =========================
# 曲面控制点
# 4个角点 + 4条边各一个中心手柄（Coons patch）
# =========================
control_points = {
    "TL": [140.0, 160.0],
    "TR": [SCREEN_W - 140.0, 160.0],
    "BL": [140.0, SCREEN_H - 160.0],
    "BR": [SCREEN_W - 140.0, SCREEN_H - 160.0],

    "TC": [SCREEN_W * 0.5, 60.0],
    "BC": [SCREEN_W * 0.5, SCREEN_H - 40.0],
    "LC": [80.0, SCREEN_H * 0.5],
    "RC": [SCREEN_W - 80.0, SCREEN_H * 0.5],
}

point_order = ["TL", "TR", "BL", "BR", "TC", "BC", "LC", "RC"]

editor_visible = True
selected_point = None
POINT_PICK_RADIUS = 24
is_dragging = False

# 是否镜像，现场可按键切换
FLIP_U = False
FLIP_V = False

# warp 条带宽度
# 数值越小越精细，但越吃 CPU
STRIP_W = 2

# 每条竖条在垂直方向的分段数
# 分段越多越能体现 LC/RC 手柄的左右弯曲，但更吃 CPU
V_SEGS = 4

# =========================
# 消息系统
# =========================
MAX_TEXTS = 30
texts = []
latest_ai_text = "..."
latest_ai_lock = threading.Lock()
message_queue = queue.Queue()

# =========================
# 字体
# =========================
def get_font(size, bold=False):
    font = pygame.freetype.SysFont("Helvetica Neue", size, bold=bold)
    font.antialiased = True
    return font


# =========================
# 工具函数
# =========================
def quadratic_bezier(p0, p1, p2, t):
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
    return np.array([x, y], dtype=np.float32)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def surface_map(u, v):
    cp = control_points
    top    = quadratic_bezier(cp["TL"], cp["TC"], cp["TR"], u)
    bottom = quadratic_bezier(cp["BL"], cp["BC"], cp["BR"], u)
    left   = quadratic_bezier(cp["TL"], cp["LC"], cp["BL"], v)
    right  = quadratic_bezier(cp["TR"], cp["RC"], cp["BR"], v)
    tl = np.array(cp["TL"], dtype=np.float32)
    tr = np.array(cp["TR"], dtype=np.float32)
    bl = np.array(cp["BL"], dtype=np.float32)
    br = np.array(cp["BR"], dtype=np.float32)
    bilinear = tl * (1-u) * (1-v) + tr * u * (1-v) + bl * (1-u) * v + br * u * v
    return top * (1-v) + bottom * v + left * (1-u) + right * u - bilinear

def uv_to_content_xy(u, v):
    return int(u * CONTENT_W), int(v * CONTENT_H)

def wrap_text_lines(text, font, max_width):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for w in words[1:]:
        test = current + " " + w
        if font.get_rect(test).width <= max_width:
            current = test
        else:
            lines.append(current)
            current = w

    lines.append(current)
    return lines

def render_wrapped_text(surface, text, font, color, rect, line_spacing=6, align_center=True):
    x, y, w, h = rect
    lines = wrap_text_lines(text, font, w)

    line_height = font.get_sized_height()
    total_h = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing

    yy = y
    if align_center:
        yy = y + max(0, (h - total_h) // 2)

    for line in lines:
        text_rect = font.get_rect(line)
        if align_center:
            xx = x + (w - text_rect.width) // 2
        else:
            xx = x
        font.render_to(surface, (xx, yy), line, color)
        yy += line_height + line_spacing

def find_nearest_control(mx, my):
    best_name = None
    best_d = 999999
    for name in point_order:
        px, py = control_points[name]
        d = distance((mx, my), (px, py))
        if d < best_d:
            best_d = d
            best_name = name
    if best_d <= POINT_PICK_RADIUS:
        return best_name
    return None

def print_control_points():
    print("control_points = {")
    for k in point_order:
        p = control_points[k]
        print(f'    "{k}": [{int(p[0])}, {int(p[1])}],')
    print("}")

def set_latest_ai_text(text):
    global latest_ai_text
    with latest_ai_lock:
        latest_ai_text = text

def get_latest_ai_text():
    with latest_ai_lock:
        return latest_ai_text

def rects_overlap(r1, r2, padding=10):
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return not (
        x1 + w1 + padding < x2 or
        x2 + w2 + padding < x1 or
        y1 + h1 + padding < y2 or
        y2 + h2 + padding < y1
    )

def estimate_text_rect(text, font, center_x, center_y, max_width=300, line_spacing=4):
    lines = wrap_text_lines(text, font, max_width)
    line_h = font.get_sized_height()
    total_h = len(lines) * line_h + max(0, len(lines) - 1) * line_spacing

    real_w = 0
    for line in lines:
        real_w = max(real_w, font.get_rect(line).width)

    box_w = min(max_width, max(real_w + 24, 120))
    box_h = max(total_h + 20, 56)

    x = int(center_x - box_w / 2)
    y = int(center_y - box_h / 2)
    return (x, y, box_w, box_h)

def get_ai_box_rect():
    ai_x = int(CONTENT_W * 0.66)
    ai_y = int(CONTENT_H * 0.72)
    ai_w = int(CONTENT_W * 0.28)
    ai_h = int(CONTENT_H * 0.20)
    return (ai_x, ai_y, ai_w, ai_h)

def lerp(a, b, t):
    return a + (b - a) * t


# =========================
# UDP 接收
# =========================
def udp_listener():
    while True:
        try:
            data, _ = sock.recvfrom(4096)
            msg = data.decode("utf-8", errors="ignore").strip()
            print("[UDP]", msg)

            if msg.startswith("AI::"):
                set_latest_ai_text(msg[4:].strip())

            elif msg.startswith("BAD::"):
                content = msg[5:].strip()
                message_queue.put(("bad", content))

            elif msg.startswith("NORMAL::"):
                content = msg[8:].strip()
                message_queue.put(("normal", content))

            else:
                message_queue.put(("normal", msg))

        except BlockingIOError:
            time.sleep(0.01)
        except Exception as e:
            print("UDP error:", e)
            time.sleep(0.05)

threading.Thread(target=udp_listener, daemon=True).start()


# =========================
# 浮动文字对象
# =========================
class FloatingText:
    def __init__(self, kind, text):
        self.kind = kind
        self.text = text

        if kind == "bad":
            self.base_color = (255, 45, 45)
            self.size = int(random.randint(36, 58) * CONTENT_SCALE)
        else:
            self.base_color = (255, 255, 255)
            self.size = int(random.randint(30, 52) * CONTENT_SCALE)

        self.font = get_font(self.size, bold=True)
        self.life = 0
        self.fading = False
        self.fade_life = 0
        self.fade_duration = 90  # 淡出约1.5秒
        self.offset_x = 0
        self.offset_y = 0

        ai_rect = get_ai_box_rect()
        placed = False
        fallback_rect = (CONTENT_W // 2 - 100, CONTENT_H // 2 - 40, 200, 80)

        for _ in range(120):
            u = random.uniform(0.08, 0.90)
            v = random.uniform(0.08, 0.70)

            x, y = uv_to_content_xy(u, v)
            rect = estimate_text_rect(text, self.font, x, y, max_width=int(320 * CONTENT_SCALE), line_spacing=4)

            # 边界限制
            if rect[0] < 8 or rect[1] < 8 or rect[0] + rect[2] > CONTENT_W - 8 or rect[1] + rect[3] > CONTENT_H - 8:
                continue

            # 避开 AI box
            if rects_overlap(rect, ai_rect, padding=14):
                continue

            collide = False
            for t in texts:
                if rects_overlap(rect, t.rect, padding=14):
                    collide = True
                    break

            if collide:
                continue

            self.u = u
            self.v = v
            self.rect = rect
            placed = True
            break

        if not placed:
            self.u = 0.5
            self.v = 0.5
            self.rect = fallback_rect

    def alive(self):
        if self.fading:
            return self.fade_life < self.fade_duration
        return True

    def start_fade(self):
        self.fading = True
        self.fade_life = 0

    def update(self):
        self.life += 1
        if self.fading:
            self.fade_life += 1
        if self.kind == "bad" and self.life < 18:
            self.offset_x = random.randint(-7, 7)
            self.offset_y = random.randint(-7, 7)
        else:
            self.offset_x = 0
            self.offset_y = 0

    def current_color(self):
        if self.fading:
            factor = 1.0 - self.fade_life / self.fade_duration
            factor = clamp(factor, 0.0, 1.0)
        else:
            factor = 1.0

        return (
            int(self.base_color[0] * factor),
            int(self.base_color[1] * factor),
            int(self.base_color[2] * factor),
        )

    def draw(self, surface):
        draw_rect = (
            int(self.rect[0] + self.offset_x),
            int(self.rect[1] + self.offset_y),
            int(self.rect[2]),
            int(self.rect[3]),
        )

        render_wrapped_text(
            surface,
            self.text,
            self.font,
            self.current_color(),
            draw_rect,
            line_spacing=4,
            align_center=True
        )


# =========================
# 内容画到 2D Surface
# =========================
def draw_content_surface():
    content_surface.fill((0, 0, 0, 0))

    for t in texts:
        t.draw(content_surface)

    ai_x, ai_y, ai_w, ai_h = get_ai_box_rect()

    pygame.draw.rect(content_surface, (5, 8, 13), (ai_x, ai_y, ai_w, ai_h), border_radius=8)
    pygame.draw.rect(content_surface, (36, 68, 102), (ai_x, ai_y, ai_w, ai_h), width=1, border_radius=8)

    label_font = get_font(int(12 * CONTENT_SCALE), bold=True)
    text_font = get_font(int(18 * CONTENT_SCALE), bold=True)

    label_font.render_to(content_surface, (ai_x + 12, ai_y + 10), "THOUGHT", (92, 111, 136))

    render_wrapped_text(
        content_surface,
        get_latest_ai_text() if get_latest_ai_text() else "...",
        text_font,
        (111, 168, 255),
        (ai_x + 12, ai_y + 28, ai_w - 24, ai_h - 38),
        line_spacing=4,
        align_center=False
    )


# =========================
# CPU warp 渲染
# 用竖条近似把 content_surface 映射到曲面区域
# =========================
def draw_warped_content_cpu():
    screen.fill((0, 0, 0))

    strip_count = max(1, CONTENT_W // STRIP_W)
    overlap = 2

    for i in range(strip_count):
        src_x = i * STRIP_W
        src_w = STRIP_W
        if src_x + src_w > CONTENT_W:
            src_w = CONTENT_W - src_x
        if src_w <= 0:
            continue

        # 归一化 u
        u0 = src_x / CONTENT_W
        u1 = (src_x + src_w) / CONTENT_W
        u = (u0 + u1) * 0.5

        if FLIP_U:
            u = 1.0 - u

        # 将每条竖条分成 V_SEGS 段，用完整 surface_map 定位
        # 这样 LC/RC 控制点的左右弯曲也会被正确渲染
        for seg in range(V_SEGS):
            fv0 = seg / V_SEGS
            fv1 = (seg + 1) / V_SEGS

            # 来源内容行范围
            sy0 = int(fv0 * CONTENT_H)
            sy1 = int(fv1 * CONTENT_H)
            seg_src_h = sy1 - sy0
            if seg_src_h <= 0:
                continue

            # 映射到屏幕上的 v 坐标（考虑镜像）
            sv0 = (1.0 - fv0) if FLIP_V else fv0
            sv1 = (1.0 - fv1) if FLIP_V else fv1

            p0 = surface_map(u, sv0)
            p1 = surface_map(u, sv1)

            dest_h = int(abs(p1[1] - p0[1]))
            if dest_h < 1:
                continue

            src_strip = content_surface.subsurface((src_x, sy0, src_w, seg_src_h))
            # 超采样：目标宽度缩回屏幕坐标（除以 SUPERSAMPLE）
            dest_w = max(1, src_w // SUPERSAMPLE + overlap)
            dst_strip = pygame.transform.smoothscale(src_strip, (dest_w, dest_h))

            # 取两端 x 的均值作为条带中心，体现左右弯曲
            dest_x = int((p0[0] + p1[0]) / 2 - dest_w / 2)
            dest_y = int(min(p0[1], p1[1]))

            screen.blit(dst_strip, (dest_x, dest_y))

    # 用 polygon 把区域外强行盖黑，防止投到不想投的地方
    mask_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    mask_surface.fill((0, 0, 0, 255))

    polygon_points = []
    for i in range(61):
        u = i / 60.0
        p = quadratic_bezier(control_points["TL"], control_points["TC"], control_points["TR"], u)
        polygon_points.append((int(p[0]), int(p[1])))
    for i in range(61):
        v = i / 60.0
        p = quadratic_bezier(control_points["TR"], control_points["RC"], control_points["BR"], v)
        polygon_points.append((int(p[0]), int(p[1])))
    for i in range(60, -1, -1):
        u = i / 60.0
        p = quadratic_bezier(control_points["BL"], control_points["BC"], control_points["BR"], u)
        polygon_points.append((int(p[0]), int(p[1])))
    for i in range(60, -1, -1):
        v = i / 60.0
        p = quadratic_bezier(control_points["TL"], control_points["LC"], control_points["BL"], v)
        polygon_points.append((int(p[0]), int(p[1])))

    pygame.draw.polygon(mask_surface, (0, 0, 0, 0), polygon_points)
    screen.blit(mask_surface, (0, 0))


# =========================
# 编辑器 overlay
# =========================
def draw_editor_overlay():
    if not editor_visible:
        return

    curve_steps = 24 if is_dragging else 60
    u_count = 4 if is_dragging else 7
    v_count = 3 if is_dragging else 5
    u_line_steps = 10 if is_dragging else 20
    v_line_steps = 20 if is_dragging else 40

    blue = (80, 165, 255)
    dark_grid = (46, 74, 104)
    white = (255, 255, 255)

    # 4条边曲线
    def draw_quad_bezier_curve(p0_name, p1_name, p2_name, steps):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            p = quadratic_bezier(control_points[p0_name], control_points[p1_name], control_points[p2_name], t)
            pts.append((int(p[0]), int(p[1])))
        pygame.draw.lines(screen, blue, False, pts, 2)

    draw_quad_bezier_curve("TL", "TC", "TR", curve_steps)
    draw_quad_bezier_curve("BL", "BC", "BR", curve_steps)
    draw_quad_bezier_curve("TL", "LC", "BL", curve_steps)
    draw_quad_bezier_curve("TR", "RC", "BR", curve_steps)

    # 手柄连线（从角点到中心手柄）
    handle_color = (80, 165, 255, 120)
    for handle, a, b in [("TC", "TL", "TR"), ("BC", "BL", "BR"), ("LC", "TL", "BL"), ("RC", "TR", "BR")]:
        hx, hy = int(control_points[handle][0]), int(control_points[handle][1])
        ax, ay = int(control_points[a][0]), int(control_points[a][1])
        bx, by = int(control_points[b][0]), int(control_points[b][1])
        pygame.draw.line(screen, (60, 120, 200), (ax, ay), (hx, hy), 1)
        pygame.draw.line(screen, (60, 120, 200), (bx, by), (hx, hy), 1)

    # 网格辅助线 - 竖向
    for i in range(1, u_count + 1):
        u = i / (u_count + 1)
        pts = []
        for j in range(u_line_steps + 1):
            v = j / u_line_steps
            p = surface_map(u, v)
            pts.append((int(p[0]), int(p[1])))
        pygame.draw.lines(screen, dark_grid, False, pts, 1)

    # 网格辅助线 - 横向
    for j in range(1, v_count + 1):
        v = j / (v_count + 1)
        pts = []
        for i in range(v_line_steps + 1):
            u = i / v_line_steps
            p = surface_map(u, v)
            pts.append((int(p[0]), int(p[1])))
        pygame.draw.lines(screen, dark_grid, False, pts, 1)

    # 角点：实心圆；手柄：空心圆
    corners = {"TL", "TR", "BL", "BR"}
    for name in point_order:
        x, y = control_points[name]
        center = (int(x), int(y))
        if name in corners:
            pygame.draw.circle(screen, blue, center, 10)
            pygame.draw.circle(screen, white, center, 10, 2)
        else:
            pygame.draw.circle(screen, white, center, 8, 2)
            pygame.draw.circle(screen, blue, center, 5)

    # 左上角提示
    hint_font = get_font(18, bold=True)
    lines = [
        "F: toggle fullscreen",
        "C: toggle editor",
        "S: print control points",
        "H: flip horizontal",
        "V: flip vertical",
        "[ / ]: strip width",
        "ESC: quit",
    ]
    panel = pygame.Surface((270, 172), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 120))
    y = 10
    for line in lines:
        hint_font.render_to(panel, (12, y), line, (220, 220, 220))
        y += 22
    screen.blit(panel, (18, 18))


# =========================
# 主循环
# =========================
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

            elif event.key == pygame.K_f:
                USE_FULLSCREEN = not USE_FULLSCREEN
                if USE_FULLSCREEN:
                    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                print("FULLSCREEN =", USE_FULLSCREEN)

            elif event.key == pygame.K_c:
                editor_visible = not editor_visible

            elif event.key == pygame.K_s:
                print_control_points()

            elif event.key == pygame.K_h:
                FLIP_U = not FLIP_U
                print("FLIP_U =", FLIP_U)

            elif event.key == pygame.K_v:
                FLIP_V = not FLIP_V
                print("FLIP_V =", FLIP_V)

            elif event.key == pygame.K_LEFTBRACKET:
                STRIP_W = min(24, STRIP_W + 1)
                print("STRIP_W =", STRIP_W)

            elif event.key == pygame.K_RIGHTBRACKET:
                STRIP_W = max(2, STRIP_W - 1)
                print("STRIP_W =", STRIP_W)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            selected_point = find_nearest_control(mx, my)
            if selected_point is not None:
                is_dragging = True

        elif event.type == pygame.MOUSEBUTTONUP:
            selected_point = None
            is_dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if selected_point is not None:
                mx, my = pygame.mouse.get_pos()
                control_points[selected_point][0] = float(mx)
                control_points[selected_point][1] = float(my)

    while not message_queue.empty():
        kind, msg = message_queue.get()
        print("[QUEUE]", kind, msg)
        texts.append(FloatingText(kind, msg))
        # 超过10条时，让最老的一条开始淡出
        active = [t for t in texts if not t.fading]
        if len(active) > 10:
            active[0].start_fade()

    for t in texts:
        t.update()
    texts = [t for t in texts if t.alive()]

    draw_content_surface()
    draw_warped_content_cpu()
    draw_editor_overlay()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
