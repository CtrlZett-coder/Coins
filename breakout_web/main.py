import asyncio
import math
import random
import pygame

# ================================================================ CONSTANTS

WIDTH, HEIGHT = 800, 600
FPS   = 60
TITLE = "Breakout"
WHITE = (255, 255, 255)
BG    = (15, 15, 30)

PADDLE_Y      = HEIGHT - 50
PADDLE_H      = 14
PADDLE_SPEED  = 7
PADDLE_SHRINK = 5

BALL_RADIUS       = 9
BALL_ACCEL_BRICK  = 0.08
BALL_ACCEL_PADDLE = 0.06
BALL_MAX_MULT     = 2.5

BRICK_W, BRICK_H = 68, 22
BRICK_GAP        = 6
BRICK_OFFSET_Y   = 65

BRICK_TYPES = {
    1: ((220,  80,  80), 10),   # red
    2: ((220, 150,  50), 20),   # orange
    3: ((100, 200,  80), 30),   # green
    4: ((240, 230,   0), 12),   # yellow  (1-hit, pattern levels)
    5: (( 60, 140, 220), 12),   # blue    (1-hit, pattern levels)
    6: ((190,  60, 220), 12),   # violet  (1-hit, pattern levels)
    7: ((255, 140, 180), 12),   # pink    (1-hit, pattern levels)
}
BRICK_HITS = {1: 1, 2: 2, 3: 3, 4: 1, 5: 1, 6: 1, 7: 1}

# ============================================================ LEVEL PATTERNS

_SPIRAL = [
    [3,3,3,3,3,3,3,3,3,3,3,3],
    [3,0,0,0,0,0,0,0,0,0,0,3],
    [3,0,2,2,2,2,2,2,2,2,0,3],
    [3,0,2,0,0,0,0,0,0,2,0,3],
    [3,0,2,0,1,1,1,1,0,2,0,3],
    [3,0,2,0,1,0,0,1,0,2,0,3],
    [3,0,2,0,1,1,1,1,0,2,0,3],
    [3,0,2,0,0,0,0,0,0,2,0,3],
    [3,0,2,2,2,2,2,2,2,2,0,3],
    [3,0,0,0,0,0,0,0,0,0,0,3],
    [3,3,3,3,3,3,3,3,3,3,3,3],
]

_NYAN = [
    [1,1,1,1,1, 0,7,7,0,7,7,0,0],
    [2,2,2,2,2, 7,7,7,7,7,7,7,0],
    [4,4,4,4,4, 7,0,7,7,7,0,7,0],
    [3,3,3,3,3, 7,7,7,7,7,7,7,0],
    [5,5,5,5,5, 7,1,1,1,1,1,7,0],
    [6,6,6,6,6, 7,1,1,1,1,1,7,7],
    [0,0,0,0,0, 7,7,7,7,7,7,7,7],
    [0,0,0,0,0, 0,7,0,7,0,7,0,0],
]

_HEART = [
    [0,0,1,1,0,0,0,1,1,0,0,0],
    [0,1,7,7,1,0,1,7,7,1,0,0],
    [1,7,7,7,7,1,7,7,7,7,1,0],
    [1,7,7,7,7,7,7,7,7,7,1,0],
    [1,7,7,7,7,7,7,7,7,7,1,0],
    [0,1,7,7,7,7,7,7,7,1,0,0],
    [0,0,1,7,7,7,7,7,1,0,0,0],
    [0,0,0,1,7,7,7,1,0,0,0,0],
    [0,0,0,0,1,7,1,0,0,0,0,0],
    [0,0,0,0,0,1,0,0,0,0,0,0],
]

LEVELS = [
    {"cols": 8,  "rows": [1, 1, 1],              "speed": 4.5, "paddle_w": 120},
    {"cols": 8,  "rows": [2, 1, 1],              "speed": 4.8, "paddle_w": 115},
    {"cols": 9,  "rows": [2, 2, 1, 1],           "speed": 5.0, "paddle_w": 110},
    {"cols": 9,  "rows": [3, 2, 1, 1],           "speed": 5.2, "paddle_w": 105},
    {"cols": 10, "rows": [3, 2, 2, 1, 1],        "speed": 5.5, "paddle_w": 100},
    {"cols": 10, "rows": [3, 3, 2, 2, 1],        "speed": 5.8, "paddle_w": 95},
    {"cols": 10, "rows": [3, 3, 2, 2, 1, 1],     "speed": 6.0, "paddle_w": 90},
    {"cols": 10, "rows": [3, 3, 3, 2, 2, 1],     "speed": 6.3, "paddle_w": 85},
    {"cols": 10, "rows": [3, 3, 3, 2, 2, 2, 1],  "speed": 6.6, "paddle_w": 80},
    {"cols": 10, "rows": [3, 3, 3, 3, 2, 2, 1],  "speed": 7.0, "paddle_w": 75},
    # --- pattern levels ---
    {"speed": 7.2, "paddle_w": 72, "name": "Спираль",
     "brick_w": 56, "brick_h": 18, "brick_gap": 4, "pattern": _SPIRAL},
    {"speed": 7.5, "paddle_w": 70, "name": "Нян Кет",
     "brick_w": 52, "brick_h": 18, "brick_gap": 4, "pattern": _NYAN},
    {"speed": 7.8, "paddle_w": 68, "name": "Сердечко",
     "brick_w": 56, "brick_h": 20, "brick_gap": 4, "pattern": _HEART},
]

_max_unlocked = 0  # highest unlocked level index (persists in session)

# ================================================================ HELPERS

def draw_heart(surface, cx, cy, size):
    r, hr = size // 2, size // 4
    c = (230, 60, 60)
    pygame.draw.circle(surface, c, (cx - hr, cy), hr)
    pygame.draw.circle(surface, c, (cx + hr, cy), hr)
    pygame.draw.polygon(surface, c, [(cx - r, cy + 1), (cx + r, cy + 1), (cx, cy + r + hr)])

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

# ================================================================== BALL

class Ball:
    def __init__(self, x, y, base_speed):
        self.radius     = BALL_RADIUS
        self.base_speed = base_speed
        self.reset(x, y)

    def reset(self, x, y):
        self.x     = float(x)
        self.y     = float(y)
        self.speed = self.base_speed
        angle = math.radians(random.choice([-70, -75, -80, -85, -95, -100, -105, -110]))
        self.vx = self.speed * math.cos(angle)
        self.vy = self.speed * math.sin(angle)
        self.active = False

    def launch(self):
        self.active = True

    def accelerate(self, amount):
        new_speed = min(self.speed + amount, self.base_speed * BALL_MAX_MULT)
        if new_speed > self.speed:
            scale = new_speed / self.speed
            self.vx *= scale
            self.vy *= scale
            self.speed = new_speed

    def update(self):
        if not self.active:
            return
        self.x += self.vx
        self.y += self.vy
        r = self.radius
        if self.x - r <= 0:
            self.x = r;          self.vx =  abs(self.vx)
        elif self.x + r >= WIDTH:
            self.x = WIDTH - r;  self.vx = -abs(self.vx)
        if self.y - r <= 0:
            self.y = r;          self.vy =  abs(self.vy)

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(int(self.x) - self.radius, int(self.y) - self.radius, d, d)

    def is_lost(self):
        return self.y - self.radius > HEIGHT

    def draw(self, surface):
        t = min(1.0, (self.speed - self.base_speed) / (self.base_speed * (BALL_MAX_MULT - 1)))
        color = lerp_color((255, 255, 255), (255, 160, 60), t)
        pos = (int(self.x), int(self.y))
        pygame.draw.circle(surface, color, pos, self.radius)
        pygame.draw.circle(surface, (255, 255, 220), pos, self.radius // 2)

# ================================================================ PADDLE

class Paddle:
    def __init__(self, initial_w):
        self.initial_w = float(initial_w)
        self.w  = float(initial_w)
        self.h  = PADDLE_H
        self.x  = WIDTH / 2 - self.w / 2
        self.y  = PADDLE_Y

    def reset(self):
        self.w = self.initial_w
        self.x = WIDTH / 2 - self.w / 2

    def shrink(self):
        self.w = max(0.0, self.w - PADDLE_SHRINK)
        self._clamp_x()

    def update_keys(self, keys):
        if self.w <= 0:
            return
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.x -= PADDLE_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.x += PADDLE_SPEED
        self._clamp_x()

    def move_by_delta(self, dx):
        self.x += dx
        self._clamp_x()

    def _clamp_x(self):
        self.x = max(0.0, min(WIDTH - self.w, self.x))

    @property
    def rect(self):
        return pygame.Rect(int(self.x), self.y, max(0, int(self.w)), self.h)

    @property
    def center_x(self):
        return self.x + self.w / 2

    @property
    def health(self):
        return self.w / self.initial_w

    def draw(self, surface):
        if self.w < 1:
            return
        rect = self.rect
        color = lerp_color((80, 160, 255), (255, 60, 60), 1 - self.health)
        pygame.draw.rect(surface, color, rect, border_radius=7)
        if self.w > 10:
            hl = pygame.Rect(rect.x + 4, rect.y + 2, max(0, int(self.w) - 8), 4)
            pygame.draw.rect(surface, tuple(min(255, c + 80) for c in color), hl, border_radius=3)

# ================================================================== BRICK

class Brick:
    def __init__(self, x, y, hits=1, brick_type=None, w=BRICK_W, h=BRICK_H):
        self.rect       = pygame.Rect(x, y, w, h)
        self.brick_type = brick_type if brick_type is not None else hits
        self.max_hits   = hits
        self.hits       = hits
        self.alive      = True

    def hit(self):
        self.hits -= 1
        if self.hits <= 0:
            self.alive = False
            return BRICK_TYPES[self.brick_type][1]
        return 0

    @property
    def color(self):
        base, _ = BRICK_TYPES[self.brick_type]
        r = self.hits / self.max_hits
        return tuple(int(c * r + 40 * (1 - r)) for c in base)

    def draw(self, surface):
        if not self.alive:
            return
        pygame.draw.rect(surface, self.color, self.rect, border_radius=4)
        pygame.draw.rect(surface, (0, 0, 0), self.rect, 1, border_radius=4)
        hl = pygame.Rect(self.rect.x + 4, self.rect.y + 3, max(1, self.rect.width - 8), 4)
        pygame.draw.rect(surface, tuple(min(255, c + 80) for c in self.color), hl, border_radius=2)

# =================================================================== MENU

class Menu:
    BTN_W, BTN_H = 260, 90

    def __init__(self, screen, clock):
        self.screen     = screen
        self.clock      = clock
        self.font_title = pygame.font.SysFont("Arial", 64, bold=True)
        self.font_btn   = pygame.font.SysFont("Arial", 30, bold=True)
        self.font_hint  = pygame.font.SysFont("Arial", 17)
        cx = WIDTH // 2
        cy = HEIGHT // 2 + 20
        self.buttons = [
            {"label": "Компьютер", "hint": "<- / ->  +  Пробел",
             "rect": pygame.Rect(cx - self.BTN_W - 24, cy, self.BTN_W, self.BTN_H),
             "mode": "pc", "color": (50, 110, 220)},
            {"label": "Телефон / Сенсор", "hint": "Касание экрана",
             "rect": pygame.Rect(cx + 24, cy, self.BTN_W, self.BTN_H),
             "mode": "mobile", "color": (40, 170, 80)},
        ]

    async def run(self):
        while True:
            self.clock.tick(FPS)
            mp = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for btn in self.buttons:
                        if btn["rect"].collidepoint(mp):
                            return btn["mode"]
                if event.type == pygame.FINGERDOWN:
                    fx, fy = event.x * WIDTH, event.y * HEIGHT
                    for btn in self.buttons:
                        if btn["rect"].collidepoint(fx, fy):
                            return btn["mode"]
            self._draw(mp)
            await asyncio.sleep(0)

    def _draw(self, mp):
        self.screen.fill(BG)
        t = self.font_title.render("BREAKOUT", True, WHITE)
        self.screen.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 4 - 30))
        s = self.font_hint.render("Выбери режим управления", True, (150, 150, 190))
        self.screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 4 + 50))
        info = self.font_hint.render("10 уровней  |  мяч ускоряется  |  платформа сужается",
                                     True, (120, 120, 160))
        self.screen.blit(info, (WIDTH // 2 - info.get_width() // 2, HEIGHT // 4 + 76))
        for i in range(3):
            draw_heart(self.screen, WIDTH // 2 - 32 + i * 32, HEIGHT // 4 + 112, 18)
        for btn in self.buttons:
            hovered = btn["rect"].collidepoint(mp)
            color   = tuple(min(255, v + 35) for v in btn["color"]) if hovered else btn["color"]
            pygame.draw.rect(self.screen, color, btn["rect"], border_radius=12)
            pygame.draw.rect(self.screen, WHITE if hovered else (120, 120, 140),
                             btn["rect"], 2, border_radius=12)
            lbl  = self.font_btn.render(btn["label"], True, WHITE)
            hint = self.font_hint.render(btn["hint"],  True, (210, 210, 210))
            cx, cy = btn["rect"].centerx, btn["rect"].centery
            self.screen.blit(lbl,  (cx - lbl.get_width()  // 2, cy - 18))
            self.screen.blit(hint, (cx - hint.get_width() // 2, cy + 14))
        pygame.display.flip()

# =============================================================== LEVEL SELECT

class LevelSelect:
    COLS   = 5
    BTN_W  = 130
    BTN_H  = 64
    GAP    = 10

    def __init__(self, screen, clock, mode):
        self.screen     = screen
        self.clock      = clock
        self.mode       = mode
        self.font_title = pygame.font.SysFont("Arial", 46, bold=True)
        self.font_num   = pygame.font.SysFont("Arial", 30, bold=True)
        self.font_xs    = pygame.font.SysFont("Arial", 14)

        total_w = self.COLS * self.BTN_W + (self.COLS - 1) * self.GAP
        ox      = (WIDTH  - total_w) // 2
        rows    = (len(LEVELS) + self.COLS - 1) // self.COLS
        total_h = rows * self.BTN_H + (rows - 1) * self.GAP
        oy      = (HEIGHT - total_h) // 2 + 30

        self.buttons = []
        for i in range(len(LEVELS)):
            row = i // self.COLS
            col = i % self.COLS
            x = ox + col * (self.BTN_W + self.GAP)
            y = oy + row * (self.BTN_H + self.GAP)
            self.buttons.append({
                "idx":      i,
                "rect":     pygame.Rect(x, y, self.BTN_W, self.BTN_H),
                "unlocked": i <= _max_unlocked,
            })

    async def run(self):
        while True:
            self.clock.tick(FPS)
            mp = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return -1  # back to mode select
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for btn in self.buttons:
                        if btn["unlocked"] and btn["rect"].collidepoint(mp):
                            return btn["idx"]
                if event.type == pygame.FINGERDOWN:
                    fx, fy = event.x * WIDTH, event.y * HEIGHT
                    for btn in self.buttons:
                        if btn["unlocked"] and btn["rect"].collidepoint(fx, fy):
                            return btn["idx"]
            self._draw(mp)
            await asyncio.sleep(0)

    def _draw(self, mp):
        self.screen.fill(BG)
        t = self.font_title.render("Выбор уровня", True, WHITE)
        self.screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 50))

        for btn in self.buttons:
            i, unlocked = btn["idx"], btn["unlocked"]
            hovered = btn["rect"].collidepoint(mp) and unlocked
            frac    = i / (len(LEVELS) - 1)
            base    = lerp_color((40, 160, 80), (200, 55, 55), frac)
            color   = tuple(min(255, c + 40) for c in base) if hovered else (base if unlocked else (45, 45, 58))
            border  = WHITE if hovered else ((150, 150, 170) if unlocked else (65, 65, 80))

            pygame.draw.rect(self.screen, color,  btn["rect"], border_radius=10)
            pygame.draw.rect(self.screen, border, btn["rect"], 2, border_radius=10)

            num = self.font_num.render(str(i + 1), True, WHITE if unlocked else (70, 70, 85))
            self.screen.blit(num, (btn["rect"].centerx - num.get_width() // 2,
                                   btn["rect"].centery - 14))
            if unlocked:
                cfg  = LEVELS[i]
                info = self.font_xs.render(f"v{cfg['speed']}  {cfg['paddle_w']}px",
                                           True, (190, 190, 190))
            else:
                info = self.font_xs.render("LOCKED", True, (70, 70, 85))
            self.screen.blit(info, (btn["rect"].centerx - info.get_width() // 2,
                                    btn["rect"].centery + 10))

        hint_text = "ESC - назад" if self.mode == "pc" else "Нажми уровень для игры"
        hint = self.font_xs.render(hint_text, True, (90, 90, 110))
        self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 30))
        pygame.display.flip()

# =================================================================== GAME

class Game:
    _PAUSE_BTN        = pygame.Rect(WIDTH - 88,  6,  80, 26)
    _RESTART_BTN      = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 90,  190, 48)
    _END_LEVELS_BTN   = pygame.Rect(WIDTH // 2 - 90,  HEIGHT // 2 + 150, 180, 48)
    _RESUME_BTN       = pygame.Rect(WIDTH // 2 - 120, HEIGHT // 2 - 80,  240, 54)
    _PAUSE_LEVELS_BTN = pygame.Rect(WIDTH // 2 - 120, HEIGHT // 2,       240, 54)
    _PAUSE_LOBBY_BTN  = pygame.Rect(WIDTH // 2 - 120, HEIGHT // 2 + 80,  240, 54)

    def __init__(self, screen, clock, mode, start_level):
        self.screen      = screen
        self.clock       = clock
        self.mode        = mode
        self.start_level = start_level
        self.font_sm     = pygame.font.SysFont("Arial", 22, bold=True)
        self.font_lg     = pygame.font.SysFont("Arial", 48, bold=True)
        self.font_xs     = pygame.font.SysFont("Arial", 17)
        self._drag_finger   = None
        self._drag_start_fx = 0.0
        self._drag_start_px = 0.0
        self._paused_from   = "playing"
        self._start_game()

    # ------------------------------------------------------ setup

    def _start_game(self):
        self.level = self.start_level
        self.score = 0
        self.lives = 3
        self._load_level()

    def _load_level(self):
        cfg          = LEVELS[self.level]
        self.paddle  = Paddle(cfg["paddle_w"])
        self.ball    = Ball(WIDTH // 2, PADDLE_Y - BALL_RADIUS - 2, cfg["speed"])
        self.bricks  = self._build_bricks(cfg)
        self.state   = "playing"
        self._drag_finger = None

    def _build_bricks(self, cfg):
        if "pattern" in cfg:
            return self._build_pattern_bricks(cfg)
        cols    = cfg["cols"]
        total_w = cols * BRICK_W + (cols - 1) * BRICK_GAP
        ox      = (WIDTH - total_w) // 2
        bricks  = []
        for row, hits in enumerate(cfg["rows"]):
            for col in range(cols):
                x = ox + col * (BRICK_W + BRICK_GAP)
                y = BRICK_OFFSET_Y + row * (BRICK_H + BRICK_GAP)
                bricks.append(Brick(x, y, hits))
        return bricks

    def _build_pattern_bricks(self, cfg):
        bw  = cfg.get("brick_w",   BRICK_W)
        bh  = cfg.get("brick_h",   BRICK_H)
        gap = cfg.get("brick_gap", BRICK_GAP)
        pat = cfg["pattern"]
        cols    = len(pat[0])
        total_w = cols * bw + (cols - 1) * gap
        ox      = (WIDTH - total_w) // 2
        bricks  = []
        for ri, row in enumerate(pat):
            for ci, btype in enumerate(row):
                if btype == 0:
                    continue
                x = ox + ci * (bw + gap)
                y = BRICK_OFFSET_Y + ri * (bh + gap)
                hits = BRICK_HITS.get(btype, 1)
                bricks.append(Brick(x, y, hits, brick_type=btype, w=bw, h=bh))
        return bricks

    def _reset_ball_and_paddle(self):
        self.paddle.reset()
        self.ball.reset(self.paddle.center_x, PADDLE_Y - BALL_RADIUS - 2)
        self._drag_finger = None

    def _advance_level(self):
        global _max_unlocked
        _max_unlocked = max(_max_unlocked, self.level + 1)
        self.level += 1
        if self.level >= len(LEVELS):
            self.state = "win"
        else:
            self._load_level()
            self.state = "level_ready"   # wait for second touch to launch
            self.lives = 3               # restore lives on new level

    def _toggle_pause(self):
        if self.state == "paused":
            self.state = self._paused_from
        elif self.state in ("playing", "level_ready"):
            self._paused_from = self.state
            self.state = "paused"

    # --------------------------------------------------------- touch

    def _on_finger_down(self, fx, fy):
        # Pause button (top-right)
        if self.state in ("playing", "level_ready") and self._PAUSE_BTN.collidepoint(fx, fy):
            self._toggle_pause()
            return None

        # Pause overlay buttons
        if self.state == "paused":
            if self._RESUME_BTN.collidepoint(fx, fy):
                self._toggle_pause()
            elif self._PAUSE_LEVELS_BTN.collidepoint(fx, fy):
                return "menu"
            elif self._PAUSE_LOBBY_BTN.collidepoint(fx, fy):
                return "lobby"
            return None

        if self.state == "playing":
            if self._drag_finger is None:
                self._drag_finger   = True
                self._drag_start_fx = fx
                self._drag_start_px = self.paddle.x
            if not self.ball.active:
                self.ball.launch()

        elif self.state == "level_complete":
            self._advance_level()  # → state becomes "level_ready"

        elif self.state == "level_ready":
            # Second touch: launch ball
            self.ball.launch()
            self.state = "playing"
            if self._drag_finger is None:
                self._drag_finger   = True
                self._drag_start_fx = fx
                self._drag_start_px = self.paddle.x

        elif self.state in ("game_over", "win"):
            if self._END_LEVELS_BTN.collidepoint(fx, fy):
                return "menu"
            else:
                self._start_game()
        return None

    def _on_finger_motion(self, fx, _fy):
        if self.state in ("playing", "level_ready") and self._drag_finger is not None:
            delta = fx - self._drag_start_fx
            self.paddle.x = self._drag_start_px + delta
            self.paddle._clamp_x()

    def _on_finger_up(self):
        self._drag_finger = None

    # --------------------------------------------------------- events

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "menu"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.state in ("playing", "level_ready", "paused"):
                        self._toggle_pause()
                    else:
                        return "menu"
                if event.key == pygame.K_SPACE:
                    if self.state == "playing":
                        if not self.ball.active:
                            self.ball.launch()
                    elif self.state == "level_complete":
                        self._advance_level()
                    elif self.state == "level_ready":
                        self.ball.launch()
                        self.state = "playing"
                    elif self.state not in ("paused",):
                        self._start_game()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if self.state in ("playing", "level_ready") and self._PAUSE_BTN.collidepoint(mx, my):
                    self._toggle_pause()
                elif self.state == "paused":
                    if self._RESUME_BTN.collidepoint(mx, my):
                        self._toggle_pause()
                    elif self._PAUSE_LEVELS_BTN.collidepoint(mx, my):
                        return "menu"
                    elif self._PAUSE_LOBBY_BTN.collidepoint(mx, my):
                        return "lobby"
                elif self.state == "level_complete":
                    self._advance_level()
                elif self.state == "level_ready":
                    self.ball.launch()
                    self.state = "playing"
                elif self.state in ("game_over", "win"):
                    if self._END_LEVELS_BTN.collidepoint(mx, my):
                        return "menu"
                    else:
                        self._start_game()

            if event.type == pygame.FINGERDOWN:
                result = self._on_finger_down(event.x * WIDTH, event.y * HEIGHT)
                if result:
                    return result
            elif event.type == pygame.FINGERMOTION:
                self._on_finger_motion(event.x * WIDTH, event.y * HEIGHT)
            elif event.type == pygame.FINGERUP:
                self._on_finger_up()

        return None

    # --------------------------------------------------------- physics

    def _collide_paddle(self):
        ball, pad = self.ball, self.paddle
        if pad.w < 1 or ball.vy <= 0 or not ball.rect.colliderect(pad.rect):
            return
        offset = (ball.x - pad.center_x) / (pad.w / 2)
        offset = max(-1.0, min(1.0, offset))
        angle  = math.radians(-90 + offset * 60)
        ball.vx = ball.speed * math.cos(angle)
        ball.vy = -abs(ball.speed * math.sin(angle))
        ball.y  = pad.y - ball.radius - 1
        ball.accelerate(BALL_ACCEL_PADDLE)
        pad.shrink()

    def _collide_bricks(self):
        for brick in self.bricks:
            if not brick.alive or not self.ball.rect.colliderect(brick.rect):
                continue
            dx = (self.ball.x - brick.rect.centerx) / (brick.rect.width  / 2)
            dy = (self.ball.y - brick.rect.centery) / (brick.rect.height / 2)
            if abs(dx) >= abs(dy):
                self.ball.vx = -self.ball.vx
            else:
                self.ball.vy = -self.ball.vy
            self.score += brick.hit()
            self.ball.accelerate(BALL_ACCEL_BRICK)
            break

    # --------------------------------------------------------- update

    def _update(self):
        if self.state not in ("playing",):
            return
        if self.mode == "pc":
            self.paddle.update_keys(pygame.key.get_pressed())
        if self.paddle.w < 1 and not self.ball.active:
            self.ball.launch()
        if not self.ball.active:
            self.ball.x = self.paddle.center_x
            return
        self.ball.update()
        self._collide_paddle()
        self._collide_bricks()
        if self.ball.is_lost():
            self._drag_finger = None
            self.lives -= 1
            if self.lives <= 0:
                self.state = "game_over"
            else:
                self._reset_ball_and_paddle()
        if all(not b.alive for b in self.bricks):
            self.state = "level_complete"

    # --------------------------------------------------------- draw helpers

    def _draw_hud(self):
        score_s = self.font_sm.render(f"Счёт: {self.score}", True, WHITE)
        self.screen.blit(score_s, (12, 8))
        lv_s = self.font_sm.render(f"Уровень {self.level + 1} / {len(LEVELS)}", True, (180, 180, 220))
        self.screen.blit(lv_s, (WIDTH // 2 - lv_s.get_width() // 2, 8))
        # Pause button (top-right)
        pygame.draw.rect(self.screen, (60, 60, 90), self._PAUSE_BTN, border_radius=6)
        pygame.draw.rect(self.screen, (110, 110, 150), self._PAUSE_BTN, 1, border_radius=6)
        mb = self.font_xs.render("II  Пауза", True, (200, 200, 220))
        self.screen.blit(mb, (self._PAUSE_BTN.centerx - mb.get_width() // 2,
                               self._PAUSE_BTN.centery - mb.get_height() // 2))
        # Speed / paddle info
        spd_frac = min(1.0, (self.ball.speed - self.ball.base_speed) /
                       (self.ball.base_speed * (BALL_MAX_MULT - 1)))
        spd_s = self.font_xs.render(
            f"Скорость: {int(spd_frac * 100)}%  Платформа: {int(self.paddle.w)}px",
            True, (110, 110, 140))
        self.screen.blit(spd_s, (12, 36))
        # Lives (hearts) right side
        for i in range(self.lives):
            draw_heart(self.screen, WIDTH - 18 - i * 26, 38, 18)
        # Paddle health bar
        bar_w = int(WIDTH * self.paddle.health)
        pygame.draw.rect(self.screen, (40, 40, 60), pygame.Rect(0, HEIGHT - 5, WIDTH, 5))
        pygame.draw.rect(self.screen, lerp_color((220, 60, 60), (60, 180, 255), self.paddle.health),
                         pygame.Rect(0, HEIGHT - 5, bar_w, 5))

    def _draw_overlay_box(self):
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        self.screen.blit(ov, (0, 0))

    def _draw_btn(self, rect, label, color=(70, 70, 110)):
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        pygame.draw.rect(self.screen, (150, 150, 180), rect, 2, border_radius=10)
        t = self.font_sm.render(label, True, WHITE)
        self.screen.blit(t, (rect.centerx - t.get_width() // 2,
                             rect.centery  - t.get_height() // 2))

    def _draw_level_complete(self):
        self._draw_overlay_box()
        cx, cy = WIDTH // 2, HEIGHT // 2
        t = self.font_lg.render(f"Уровень {self.level + 1} пройден!", True, (120, 255, 140))
        s = self.font_sm.render(f"Счёт: {self.score}", True, (200, 200, 200))
        self.screen.blit(t, (cx - t.get_width() // 2, cy - 60))
        self.screen.blit(s, (cx - s.get_width() // 2, cy))
        if self.level + 1 < len(LEVELS):
            cfg  = LEVELS[self.level + 1]
            nxt  = cfg.get("name", f"Уровень {self.level + 2}")
            info = self.font_xs.render(
                f"Следующий: {nxt}  v{cfg['speed']}  {cfg['paddle_w']}px",
                True, (140, 140, 180))
            self.screen.blit(info, (cx - info.get_width() // 2, cy + 36))
        hint = "Пробел — продолжить" if self.mode == "pc" else "Коснись экрана — продолжить"
        h = self.font_xs.render(hint, True, (150, 150, 150))
        self.screen.blit(h, (cx - h.get_width() // 2, cy + 70))

    def _draw_level_ready(self):
        hint = "Пробел — запустить мяч" if self.mode == "pc" else "Коснись для запуска"
        s = self.font_sm.render(hint, True, (180, 220, 180))
        self.screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 + 50))

    def _draw_pause(self):
        self._draw_overlay_box()
        cx = WIDTH // 2
        t = self.font_lg.render("ПАУЗА", True, WHITE)
        self.screen.blit(t, (cx - t.get_width() // 2, HEIGHT // 2 - 150))
        self._draw_btn(self._RESUME_BTN,       "Продолжить",   (40, 140, 60))
        self._draw_btn(self._PAUSE_LEVELS_BTN, "Выбор уровня", (50, 100, 180))
        self._draw_btn(self._PAUSE_LOBBY_BTN,  "< Лобби",      (70, 70, 100))
        if self.mode == "pc":
            h = self.font_xs.render("Esc — продолжить", True, (100, 100, 120))
            self.screen.blit(h, (cx - h.get_width() // 2, HEIGHT // 2 + 150))

    def _draw_end_screen(self, title, color=WHITE):
        self._draw_overlay_box()
        cx, cy = WIDTH // 2, HEIGHT // 2
        t = self.font_lg.render(title, True, color)
        s = self.font_sm.render(f"Финальный счёт: {self.score}", True, (200, 200, 200))
        self.screen.blit(t, (cx - t.get_width() // 2, cy - 70))
        self.screen.blit(s, (cx - s.get_width() // 2, cy - 10))
        if self.mode == "pc":
            h = self.font_xs.render("Пробел — снова  |  Esc — пауза/меню", True, (130, 130, 130))
            self.screen.blit(h, (cx - h.get_width() // 2, cy + 35))
        else:
            self._draw_btn(self._RESTART_BTN,   "Снова",    (50, 130, 50))
            self._draw_btn(self._END_LEVELS_BTN, "< Уровни")

    def _draw(self):
        self.screen.fill(BG)
        for brick in self.bricks:
            brick.draw(self.screen)
        self.paddle.draw(self.screen)
        self.ball.draw(self.screen)
        self._draw_hud()

        if self.state == "playing" and not self.ball.active:
            hint = "Коснись и тяни" if self.mode == "mobile" else "Пробел — запуск"
            s = self.font_sm.render(hint, True, (180, 180, 180))
            self.screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 + 40))

        if self.state == "level_ready":
            self._draw_level_ready()
        elif self.state == "level_complete":
            self._draw_level_complete()
        elif self.state == "paused":
            self._draw_pause()
        elif self.state == "game_over":
            self._draw_end_screen("ИГРА ОКОНЧЕНА", (255, 100, 100))
        elif self.state == "win":
            self._draw_end_screen("ПОБЕДА!", (100, 255, 140))

        pygame.display.flip()

    async def run(self):
        while True:
            self.clock.tick(FPS)
            result = self._handle_events()
            if result:
                return result
            self._update()
            self._draw()
            await asyncio.sleep(0)

# ================================================================== MAIN

async def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock  = pygame.time.Clock()
    while True:
        mode = await Menu(screen, clock).run()
        if mode is None:
            break
        while True:
            level = await LevelSelect(screen, clock, mode).run()
            if level is None or level == -1:
                break  # back to mode select
            result = await Game(screen, clock, mode, level).run()
            if result is None:
                return
            if result == "lobby":
                break  # break inner while → back to mode select
            # "menu" → continue inner while (level select)

asyncio.run(main())
