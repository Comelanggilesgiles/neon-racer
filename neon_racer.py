"""
Neon Racer - Python (pygame) edition.

A three-lane cartoon arcade racer. This is the desktop version of the browser
game in the parent folder and uses the same rules:

    lane      0, 1 or 2 (the player starts in the centre)
    speed     6 normally, +3 while boosting
    traffic   car.y += speed every frame
    boost     touching a boost pad sets boost = True and raises speed
    score     score += int(speed) every frame

Run:
    pip install -r requirements.txt
    python neon_racer.py

Controls:
    Left / Right arrows or A / D   switch lanes
    Enter or Space                 start / rematch
    Mouse click (left/right half)  switch lanes
    Esc                            quit
"""

import math
import os
import random
import sys

import pygame

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
W, H = 420, 720
FPS = 60
ROAD_L, ROAD_R = 60, 360
LANES = [110, 210, 310]          # x centre of each lane
PLAYER_Y = 560
BOOST_FRAMES = 240               # about four seconds at 60 fps

INK = (22, 10, 43)
CREAM = (255, 244, 214)
YELLOW = (255, 210, 63)
RED = (255, 61, 90)
CYAN = (39, 230, 255)
MAGENTA = (255, 47, 168)
ORANGE = (255, 122, 26)
BLUE = (47, 139, 255)

CAR_COLORS = [(255, 47, 168), (165, 91, 255), (255, 122, 47), (31, 215, 160), (255, 210, 63)]
SHIRTS = [RED, CYAN, YELLOW, (165, 91, 255), (31, 215, 160), (255, 122, 47)]
SKINS = [(255, 217, 179), (232, 176, 122), (185, 122, 75), (122, 74, 43), (255, 230, 204)]

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(HERE, "highscore.txt")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def shade(color, amount):
    """Lighten (amount > 0) or darken (amount < 0) an RGB colour."""
    target = 0 if amount < 0 else 255
    p = abs(amount)
    return tuple(int((target - v) * p + v) for v in color)


def hash_int(n):
    n = (n * 374761393) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) & 0xFFFFFFFF


def overlaps(ax, ay, aw, ah, bx, by, bw, bh, pad=0):
    return abs(ax - bx) < (aw + bw) / 2 - pad and abs(ay - by) < (ah + bh) / 2 - pad


def load_best():
    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def save_best(value):
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as f:
            f.write(str(value))
    except OSError:
        pass


# --------------------------------------------------------------------------
# Text with a cartoon outline
# --------------------------------------------------------------------------
_fonts = {}
_text_cache = {}


def get_font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.SysFont("impact,arialblack,arial", size, bold=True, italic=True)
    return _fonts[size]


def outlined_surface(text, size, color, shadow=None):
    key = (text, size, color, shadow)
    if key in _text_cache:
        return _text_cache[key]
    if len(_text_cache) > 400:
        _text_cache.clear()

    font = get_font(size)
    base = font.render(text, True, color)
    ink = font.render(text, True, INK)
    o = max(2, size // 8)
    sd = (size // 14 + 3) if shadow else 0
    pad = o + 2
    w, h = base.get_size()
    surf = pygame.Surface((w + 2 * pad + sd, h + 2 * pad + sd), pygame.SRCALPHA)

    offsets = [(dx, dy) for dx in (-o, 0, o) for dy in (-o, 0, o) if (dx, dy) != (0, 0)]
    half = o // 2
    offsets += [(dx, dy) for dx in (-half, half) for dy in (-half, half)]

    if shadow:
        shadow_base = font.render(text, True, shadow)
        for dx, dy in offsets:
            surf.blit(ink, (pad + dx + sd, pad + dy + sd))
        surf.blit(shadow_base, (pad + sd, pad + sd))
    for dx, dy in offsets:
        surf.blit(ink, (pad + dx, pad + dy))
    surf.blit(base, (pad, pad))
    _text_cache[key] = surf
    return surf


def draw_text(target, text, size, color, center=None, left=None, shadow=None,
              scale=1.0, angle=0.0, alpha=255):
    surf = outlined_surface(text, size, color, shadow)
    if scale != 1.0:
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(surf.get_width() * scale)), max(1, int(surf.get_height() * scale))))
    if angle:
        surf = pygame.transform.rotate(surf, angle)
    if alpha < 255:
        surf = surf.copy()
        surf.set_alpha(int(alpha))
    if center is not None:
        rect = surf.get_rect(center=(int(center[0]), int(center[1])))
    else:
        rect = surf.get_rect(midleft=(int(left[0]), int(left[1])))
    target.blit(surf, rect)
    return rect


# --------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------
def star(target, x, y, radius, points, fill, rot=0.0, outline=3):
    pts = []
    for i in range(points * 2):
        r = radius * 0.42 if i % 2 else radius
        a = rot + i * math.pi / points
        pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
    pygame.draw.polygon(target, fill, pts)
    if outline:
        pygame.draw.polygon(target, INK, pts, outline)


def draw_car(target, x, y, w, h, color, player=False, tilt=0.0, sx=1.0, sy=1.0,
             look=0.0, pupil=3.4, flame=0, alpha=255):
    """Draw one outlined cartoon car with eyes. Squash/stretch via sx, sy."""
    tw, th = w + 40, h + 110
    tmp = pygame.Surface((tw, th), pygame.SRCALPHA)
    cx, cy = tw // 2, th // 2
    top, left = cy - h // 2, cx - w // 2

    # exhaust flames (cartoon, outlined)
    if flame > 0:
        for ox in (-10, 10):
            f = flame * random.uniform(0.85, 1.15)
            by = cy + h // 2 - 2
            outer = [(cx + ox - 6, by), (cx + ox - 8, by + f * 0.5), (cx + ox, by + f),
                     (cx + ox + 8, by + f * 0.5), (cx + ox + 6, by)]
            inner = [(cx + ox - 3, by), (cx + ox - 4, by + f * 0.3), (cx + ox, by + f * 0.6),
                     (cx + ox + 4, by + f * 0.3), (cx + ox + 3, by)]
            pygame.draw.polygon(tmp, ORANGE, outer)
            pygame.draw.polygon(tmp, INK, outer, 3)
            pygame.draw.polygon(tmp, (255, 225, 74), inner)

    # wheels
    for side in (-1, 1):
        for wy in (-0.27, 0.26):
            rect = pygame.Rect(int(cx + side * (w / 2 + 1) - 4.5), int(cy + wy * h - 10), 9, 20)
            pygame.draw.rect(tmp, (42, 26, 68), rect, border_radius=3)
            pygame.draw.rect(tmp, INK, rect, 3, border_radius=3)

    # body, cel shading, highlight
    body = pygame.Rect(left, top, w, h)
    pygame.draw.rect(tmp, color, body, border_radius=12)
    shade_rect = pygame.Rect(int(cx + w * 0.14), top + 3, int(w * 0.36) - 2, h - 6)
    pygame.draw.rect(tmp, shade(color, -0.32), shade_rect, border_radius=9)
    pygame.draw.rect(tmp, shade(color, 0.45),
                     pygame.Rect(left + 5, top + 22, 4, int(h * 0.5)), border_radius=2)
    if player:
        pygame.draw.rect(tmp, CREAM, pygame.Rect(cx - 7, top + 4, 5, h - 8))
        pygame.draw.rect(tmp, CREAM, pygame.Rect(cx + 2, top + 4, 5, h - 8))
    pygame.draw.rect(tmp, INK, body, 4, border_radius=12)

    # windshield with glare, rear glass
    ws = pygame.Rect(int(cx - w * 0.34), int(cy - h * 0.03), int(w * 0.68), int(h * 0.2))
    pygame.draw.rect(tmp, (191, 243, 255), ws, border_radius=6)
    glare = [(cx - w * 0.26, cy + h * 0.15), (cx - w * 0.12, cy + h * 0.15),
             (cx + w * 0.02, cy - h * 0.01), (cx - w * 0.12, cy - h * 0.01)]
    pygame.draw.polygon(tmp, (255, 255, 255), glare)
    pygame.draw.rect(tmp, INK, ws, 3, border_radius=6)
    rg = pygame.Rect(int(cx - w * 0.28), int(cy + h * 0.24), int(w * 0.56), int(h * 0.09))
    pygame.draw.rect(tmp, (121, 200, 230), rg, border_radius=4)
    pygame.draw.rect(tmp, INK, rg, 2, border_radius=4)

    # tail lights and hero spoiler
    pygame.draw.rect(tmp, (255, 51, 85), pygame.Rect(left + 4, top + h - 7, 10, 4))
    pygame.draw.rect(tmp, (255, 51, 85), pygame.Rect(left + w - 14, top + h - 7, 10, 4))
    if player:
        sp = pygame.Rect(int(cx - w * 0.46), top + h - 2, int(w * 0.92), 7)
        pygame.draw.rect(tmp, shade(color, -0.25), sp, border_radius=3)
        pygame.draw.rect(tmp, INK, sp, 3, border_radius=3)

    # eyes: hero looks angry, traffic looks worried
    ey = top + 15
    for s in (-1, 1):
        pygame.draw.circle(tmp, (255, 255, 255), (cx + s * 9, ey), 8)
        pygame.draw.circle(tmp, INK, (cx + s * 9, ey), 8, 2)
        px = cx + s * 9 + look * 2.6
        py = ey + (-1.5 if player else 2)
        pygame.draw.circle(tmp, INK, (int(px), int(py)), max(1, int(round(pupil))))
        if player:
            brow = [(cx + s * 16, ey - 12), (cx + s * 3, ey - 7)]
        else:
            brow = [(cx + s * 16, ey - 8), (cx + s * 3, ey - 13)]
        pygame.draw.line(tmp, INK, brow[0], brow[1], 3)

    # squash and stretch, then tilt
    if abs(sx - 1) > 0.01 or abs(sy - 1) > 0.01:
        tmp = pygame.transform.smoothscale(
            tmp, (max(1, int(tw * sx)), max(1, int(th * sy))))
    if abs(tilt) > 0.005:
        tmp = pygame.transform.rotate(tmp, -math.degrees(tilt))
    if alpha < 255:
        tmp.set_alpha(alpha)
    target.blit(tmp, tmp.get_rect(center=(int(x), int(y))))


def draw_bar(target, x, y, w, h, frac, fill, back, from_right=False):
    """Slanted fighting-game style meter."""
    skew = 8
    outline = [(x + skew, y), (x + w + skew, y), (x + w, y + h), (x, y + h)]
    pygame.draw.polygon(target, back, outline)
    fw = int(w * clamp(frac, 0, 1))
    if fw > 0:
        if from_right:
            fx = x + w - fw
        else:
            fx = x
        pts = [(fx + skew, y), (fx + fw + skew, y), (fx + fw, y + h), (fx, y + h)]
        pygame.draw.polygon(target, fill, pts)
    pygame.draw.polygon(target, INK, outline, 3)


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.scene = pygame.Surface((W, H)).convert()
        self.best = load_best()
        self.state = "ready"
        self.tick = 0
        self.dash_off = 0.0
        self.bar_off = 0.0
        self.crowd_scroll = 0.0
        self.over_t = 0
        self.bg_normal = self._gradient((27, 11, 58), (42, 15, 79))
        self.bg_boost = self._gradient((58, 10, 63), (90, 18, 56))
        self.vignette = self._make_vignette()
        self.reset()

    # -- setup ------------------------------------------------------------
    @staticmethod
    def _gradient(top, bottom):
        surf = pygame.Surface((W, H))
        for y in range(H):
            t = y / H
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(surf, c, (0, y), (W, y))
        return surf.convert()

    @staticmethod
    def _make_vignette():
        sw, sh = 42, 72
        small = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for yy in range(sh):
            for xx in range(sw):
                d = math.hypot((xx / sw - 0.5) * 1.0, (yy / sh - 0.5) * 0.58)
                a = clamp((d - 0.28) / 0.4, 0, 1) * 100
                small.set_at((xx, yy), (255, 60, 120, int(a)))
        return pygame.transform.smoothscale(small, (W, H))

    def reset(self):
        self.lane = 1
        self.score = 0
        self.speed = 6.0
        self.boost = False
        self.base_speed = 6.0
        self.boost_timer = 0
        self.frames = 0
        self.traffic = []
        self.pads = []
        self.particles = []
        self.fx = []
        self.banners = []
        self.spawn_dist = 220
        self.pad_dist = 900
        self.shake = 0.0
        self.flash = 0.0
        self.zoom = 0.0
        self.hit_stop = 0
        self.combo = 0
        self.combo_timer = 0
        self.combo_pulse = 0.0
        self.intro_t = 0
        self.px = float(LANES[1])
        self.tilt = 0.0
        self.sq = 0.0
        self.pop = 0.0

    def begin(self):
        self.reset()
        self.state = "intro"

    # -- effects ----------------------------------------------------------
    def add_banner(self, text, color, size=76, life=70):
        self.banners.append({"text": text, "color": color, "size": size, "life": life, "max": life})

    def add_pow(self, x, y, text, color):
        self.fx.append({"kind": "pow", "x": x, "y": y, "text": text, "color": color,
                        "life": 34, "max": 34, "rot": random.uniform(-0.3, 0.3)})

    def add_float(self, x, y, text, color):
        self.fx.append({"kind": "float", "x": x, "y": y, "text": text, "color": color,
                        "life": 44, "max": 44})

    def burst(self, x, y, n, colors, power, stars=False):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(1.5, power)
            self.particles.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s,
                                   "life": random.randint(18, 44), "c": random.choice(colors),
                                   "star": stars and random.random() < 0.5,
                                   "r": random.uniform(2, 4.5)})

    def effects_tick(self):
        if self.flash > 0:
            self.flash -= 0.06
        self.shake *= 0.86
        self.zoom *= 0.85
        self.pop *= 0.86
        self.combo_pulse *= 0.88
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["star"]:
                p["vy"] += 0.12
            p["life"] -= 1
        self.particles = [p for p in self.particles if p["life"] > 0]
        for f in self.fx:
            f["life"] -= 1
            if f["kind"] == "float":
                f["y"] -= 1.1
        self.fx = [f for f in self.fx if f["life"] > 0]
        for b in self.banners:
            b["life"] -= 1
        self.banners = [b for b in self.banners if b["life"] > 0]

    # -- input ------------------------------------------------------------
    def move_lane(self, d):
        if self.state not in ("play", "intro"):
            return
        old = self.lane
        if d < 0 and self.lane > 0:      # if keys[K_LEFT] and lane > 0
            self.lane -= 1
        if d > 0 and self.lane < 2:      # if keys[K_RIGHT] and lane < 2
            self.lane += 1
        if self.lane != old and self.state == "play":
            # dodge: a car in the lane you just left was about to hit you
            for car in self.traffic:
                if (car["lane"] == old and not car["dodged"]
                        and PLAYER_Y - 210 < car["y"] < PLAYER_Y + 10):
                    car["dodged"] = True
                    self.register_dodge(car)

    def register_dodge(self, car):
        self.combo += 1
        self.combo_timer = 150
        self.combo_pulse = 1.0
        pts = 50 * self.combo
        self.score += pts
        if self.combo >= 4:
            self.add_pow(car["x"], car["y"] - 20, "INSANE!", RED)
        elif self.combo >= 2:
            self.add_pow(car["x"], car["y"] - 20, "NICE!", CYAN)
        else:
            self.add_pow(car["x"], car["y"] - 20, "DODGE!", CYAN)
        self.add_float(car["x"], car["y"] - 60, "+%d" % pts, YELLOW)
        self.hit_stop = 3
        self.zoom = max(self.zoom, 0.025)

    # -- spawning ---------------------------------------------------------
    def spawn_traffic(self):
        two = random.random() < (0.4 if self.boost else 0.22)
        order = [0, 1, 2]
        random.shuffle(order)
        for i in range(2 if two else 1):
            lane = order[i]
            self.traffic.append({"lane": lane, "x": LANES[lane], "y": -60 - i * 6, "w": 42, "h": 78,
                                 "c": random.choice(CAR_COLORS), "dodged": False})

    def spawn_pad(self):
        lane = random.randint(0, 2)
        if any(t["lane"] == lane and t["y"] < 160 for t in self.traffic):
            return
        self.pads.append({"x": LANES[lane], "y": -50, "w": 60, "h": 46})

    # -- update -----------------------------------------------------------
    def ease_player(self):
        before = self.px
        self.px += (LANES[self.lane] - self.px) * 0.32      # player.x = lanes[lane], eased
        vx = self.px - before
        self.tilt += (vx * 0.06 - self.tilt) * 0.3
        self.sq += (min(abs(vx) * 0.03, 0.25) - self.sq) * 0.4

    def scenery(self, sp):
        self.dash_off = (self.dash_off + sp) % 80
        self.bar_off = (self.bar_off + sp) % 60
        self.crowd_scroll += sp

    def update(self):
        self.effects_tick()

        if self.state == "over":
            self.over_t += 1
            return

        if self.state == "intro":
            self.intro_t += 1
            self.ease_player()
            self.scenery(6)
            if self.intro_t == 2:
                self.add_banner("READY?", YELLOW)
            if self.intro_t == 58:
                self.add_banner("GO!!", (255, 90, 31), 96)
                self.state = "play"
                self.flash = 0.6
                self.zoom = 0.05
            return

        if self.state != "play":
            return

        self.frames += 1
        self.base_speed = min(8.0, 6 + (self.frames // 600) * 0.25)
        self.ease_player()

        if self.boost:
            self.boost_timer -= 1
            if self.boost_timer <= 0:
                self.boost = False
        else:
            self.speed += (self.base_speed - self.speed) * 0.05

        for car in self.traffic:                 # car.y += speed
            car["y"] += self.speed
        for pad in self.pads:
            pad["y"] += self.speed
        self.traffic = [c for c in self.traffic if c["y"] < H + 100]
        self.pads = [p for p in self.pads if p["y"] < H + 100]

        self.spawn_dist -= self.speed
        if self.spawn_dist <= 0:
            self.spawn_traffic()
            self.spawn_dist = random.uniform(105, 175) if self.boost else random.uniform(170, 270)
        self.pad_dist -= self.speed
        if self.pad_dist <= 0:
            self.spawn_pad()
            self.pad_dist = random.uniform(1300, 2200)

        # player.colliderect(boost_pad)
        for pad in self.pads[:]:
            if overlaps(self.px, PLAYER_Y, 40, 76, pad["x"], pad["y"], pad["w"], pad["h"]):
                self.boost = True
                self.boost_timer = BOOST_FRAMES
                self.speed = self.base_speed + 3
                self.flash = 1.0
                self.shake = 9
                self.zoom = 0.07
                self.hit_stop = 5
                self.pop = 0.35
                self.add_banner("BOOST!!", (255, 90, 31), 84)
                self.add_pow(pad["x"], PLAYER_Y - 70, "WHOOSH!", YELLOW)
                self.burst(pad["x"], PLAYER_Y, 26, [YELLOW, ORANGE, (255, 255, 255)], 7, True)
                self.pads.remove(pad)

        for car in self.traffic:
            if overlaps(self.px, PLAYER_Y, 40, 76, car["x"], car["y"], car["w"], car["h"], 6):
                self.crash(car)
                return

        self.score += int(self.speed)            # score += int(speed)
        self.scenery(self.speed)
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                self.combo = 0
        if self.boost and self.frames % 2 == 0:
            self.particles.append({"x": self.px + random.uniform(-12, 12), "y": PLAYER_Y + 44,
                                   "vx": random.uniform(-0.5, 0.5), "vy": random.uniform(2, 5),
                                   "life": 20, "c": random.choice([YELLOW, (255, 90, 31)]),
                                   "star": False, "r": random.uniform(2, 4)})
        if self.boost:
            self.shake = max(self.shake, 1.8)

    def crash(self, car):
        self.state = "over"
        self.over_t = 0
        self.hit_stop = 16
        self.shake = 16
        self.flash = 1.0
        self.zoom = 0.12
        self.add_pow(car["x"], (car["y"] + PLAYER_Y) / 2, "CRASH!", RED)
        self.burst(self.px, PLAYER_Y - 10, 70, [MAGENTA, YELLOW, (255, 255, 255), CYAN], 10, True)
        self.banners = []
        self.add_banner("K.O.!!", RED, 110, 150)
        self.new_best = self.score > self.best
        if self.new_best:
            self.best = self.score
            save_best(self.best)

    def tick_frame(self):
        self.tick += 1
        if self.hit_stop > 0:
            self.hit_stop -= 1
        else:
            self.update()

    # -- drawing ----------------------------------------------------------
    def draw_crowd(self, s):
        row_h = 38
        base = int(self.crowd_scroll // row_h)
        frac = self.crowd_scroll % row_h
        cheer = self.boost
        for side in (0, 1):
            for j in range(22):
                idx = j - base
                h = hash_int(idx * 2 + side)
                x = 20 + (h % 3) * 8 if side == 0 else 400 - (h % 3) * 8
                bob = math.sin(self.tick * 0.28 + h % 7) * (5 if cheer else 1.6)
                y = j * row_h + frac - 60 + bob
                shirt = SHIRTS[h % len(SHIRTS)]
                skin = SKINS[(h >> 3) % len(SKINS)]
                arm_y = (-14 + math.sin(self.tick * 0.5 + j) * 4) if cheer else 9
                for sgn in (-1, 1):
                    a = (x + sgn * 8, y + 4)
                    b = (x + sgn * 15, y + arm_y)
                    pygame.draw.line(s, INK, a, b, 7)
                    pygame.draw.line(s, skin, a, b, 3)
                body = pygame.Rect(int(x - 9), int(y), 18, 17)
                pygame.draw.rect(s, shirt, body, border_radius=5)
                pygame.draw.rect(s, INK, body, 2, border_radius=5)
                pygame.draw.circle(s, skin, (int(x), int(y - 8)), 9)
                pygame.draw.circle(s, INK, (int(x), int(y - 8)), 9, 2)
                pygame.draw.circle(s, INK, (int(x - 3.4), int(y - 9)), 2)
                pygame.draw.circle(s, INK, (int(x + 3.4), int(y - 9)), 2)
                if cheer:
                    pygame.draw.ellipse(s, INK, pygame.Rect(int(x - 3), int(y - 6), 6, 5))
                else:
                    pygame.draw.rect(s, INK, pygame.Rect(int(x - 2), int(y - 4), 5, 2))

    def draw_pad(self, s, p):
        pulse = 1 + math.sin(self.tick * 0.2) * 0.06
        w, h = 60 * pulse, 46 * pulse
        rect = pygame.Rect(int(p["x"] - w / 2), int(p["y"] - h / 2), int(w), int(h))
        pygame.draw.rect(s, YELLOW, rect, border_radius=9)
        pygame.draw.rect(s, INK, rect, 4, border_radius=9)
        for i in range(2):
            o = i * 15 - 7
            pts = [(p["x"] - 14, p["y"] + 9 + o), (p["x"], p["y"] - 5 + o), (p["x"] + 14, p["y"] + 9 + o)]
            pygame.draw.lines(s, INK, False, pts, 9)
            pygame.draw.lines(s, (255, 90, 31), False, pts, 5)
        for i in range(3):
            a = self.tick * 0.08 + i * 2.1
            star(s, p["x"] + math.cos(a) * 38, p["y"] + math.sin(a) * 28, 6, 4, (255, 255, 255), a, 2)

    def draw_scene(self, s):
        s.blit(self.bg_boost if self.boost else self.bg_normal, (0, 0))

        # halftone dots
        off = self.crowd_scroll % 20
        dot = (110, 30, 110) if not self.boost else (150, 40, 100)
        for row, y in enumerate(range(-20, H + 20, 20)):
            r = int(1 + (y / H) * 2.6)
            shift = 10 if row % 2 else 0
            for x in range(0, W + 20, 20):
                pygame.draw.circle(s, dot, (x + shift, int(y + off)), max(1, r))

        self.draw_crowd(s)

        # barriers
        for i in range(-2, H // 30 + 2):
            y = i * 30 + self.bar_off
            col = CREAM if i % 2 else RED
            for bx in (44, 360):
                rect = pygame.Rect(bx, int(y), 16, 30)
                pygame.draw.rect(s, col, rect, border_radius=3)
                pygame.draw.rect(s, INK, rect, 3, border_radius=3)

        # road, edge stripes, lane dashes
        pygame.draw.rect(s, (90, 47, 110) if self.boost else (58, 47, 110),
                         pygame.Rect(ROAD_L, 0, ROAD_R - ROAD_L, H))
        for x in (ROAD_L + 8, ROAD_R - 8):
            pygame.draw.line(s, INK, (x, 0), (x, H), 9)
            pygame.draw.line(s, YELLOW, (x, 0), (x, H), 4)
        for x in (160, 260):
            y = -80 + self.dash_off
            while y < H + 40:
                pygame.draw.line(s, INK, (x, y), (x, y + 36), 10)
                pygame.draw.line(s, CREAM, (x, y + 1), (x, y + 35), 5)
                y += 80

        # boost: radial speed rays and streaks
        if self.boost:
            rays = pygame.Surface((W, H), pygame.SRCALPHA)
            rot = self.tick * 0.012
            for i in range(16):
                a = rot + i * math.pi / 8
                pts = [(W / 2, 260),
                       (W / 2 + math.cos(a - 0.11) * 900, 260 + math.sin(a - 0.11) * 900),
                       (W / 2 + math.cos(a + 0.11) * 900, 260 + math.sin(a + 0.11) * 900)]
                pygame.draw.polygon(rays, (255, 220, 90, 44), pts)
            s.blit(rays, (0, 0))
            for i in range(14):
                x = ROAD_L + 14 + ((i * 53 + 17) % (ROAD_R - ROAD_L - 28))
                y = ((i * 97 + self.tick * (16 + (i % 4) * 5)) % (H + 220)) - 110
                pygame.draw.line(s, (255, 244, 214), (x, y), (x, y + 80 + (i % 3) * 34), 3)

        for p in self.pads:
            self.draw_pad(s, p)

        # traffic
        for c in self.traffic:
            near = clamp(1 - abs(PLAYER_Y - c["y"]) / 300, 0, 1)
            draw_car(s, c["x"], c["y"], c["w"], c["h"], c["c"],
                     look=clamp((self.px - c["x"]) / 110, -1, 1), pupil=3.6 - near * 1.7)

        # player with afterimages
        if self.state != "over":
            pop = self.pop + (0.07 if self.boost else 0)
            args = dict(w=40, h=76, player=True, tilt=self.tilt,
                        sx=1 - self.sq * 0.8 - pop * 0.45, sy=1 + self.sq + pop,
                        look=clamp((LANES[self.lane] - self.px) / 40, -1, 1))
            if self.boost:
                draw_car(s, self.px, PLAYER_Y + 58, color=YELLOW, alpha=40, **args)
                draw_car(s, self.px, PLAYER_Y + 30, color=(255, 138, 63), alpha=72, **args)
            draw_car(s, self.px, PLAYER_Y, color=BLUE, flame=46 if self.boost else 0, **args)

        # particles
        for p in self.particles:
            if p["star"]:
                star(s, p["x"], p["y"], p["r"] * 2.2, 4, p["c"], p["life"] * 0.2, 2)
            else:
                r = int(p["r"])
                pygame.draw.rect(s, p["c"], pygame.Rect(int(p["x"]), int(p["y"]), r, r))

        # comic bursts and floating numbers
        for f in self.fx:
            t = 1 - f["life"] / f["max"]
            if f["kind"] == "pow":
                sc = 0.4 + (t / 0.2) * 0.9 if t < 0.2 else 1.3 - (t - 0.2) * 0.25
                r = 54 * sc
                star(s, f["x"], f["y"], r, 9, f["color"], f["rot"], 4)
                star(s, f["x"], f["y"], r * 0.63, 9, CREAM, f["rot"] + 0.2, 0)
                draw_text(s, f["text"], 22, f["color"], center=(f["x"], f["y"]), scale=sc,
                          alpha=255 * min(1, f["life"] / 8))
            else:
                draw_text(s, f["text"], 24, f["color"], center=(f["x"], f["y"]),
                          alpha=255 * min(1, f["life"] / 12))

    def draw_hud(self, scr):
        draw_text(scr, "BOOST", 16, CREAM, left=(14, 18))
        draw_bar(scr, 14, 32, 130, 14, self.boost_timer / BOOST_FRAMES if self.boost else 0,
                 YELLOW, (194, 31, 69))
        draw_text(scr, "SCORE", 16, YELLOW, center=(W // 2, 18))
        draw_text(scr, "{:,}".format(self.score), 32, CREAM, center=(W // 2, 46))
        draw_text(scr, "HI {:,}".format(self.best), 15, CYAN, center=(W // 2, 72))
        draw_text(scr, "%d KM/H" % round(self.speed * 30), 16, CREAM, center=(W - 70, 18))
        draw_bar(scr, W - 144, 32, 130, 14, clamp((self.speed - 4) / 6, 0, 1),
                 CYAN, (33, 32, 107), from_right=True)

    def draw_overlay_text(self, scr):
        if self.combo >= 2 and self.state == "play":
            sc = 1 + self.combo_pulse * 0.5
            rect = draw_text(scr, str(self.combo), 58, YELLOW, left=(60, 170), scale=sc)
            draw_text(scr, "HIT COMBO!", 20, CREAM, left=(rect.right + 6, 176))
        for b in self.banners:
            t = b["max"] - b["life"]
            sc = 3.2 - (t / 7) * 2.2 if t < 7 else 1 + math.sin(t * 0.3) * 0.02
            alpha = 255 * min(1, b["life"] / 12)
            draw_text(scr, b["text"], b["size"], b["color"], center=(W // 2, 270),
                      shadow=MAGENTA, scale=sc, angle=3.4, alpha=alpha)

    def draw_menu(self, scr):
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((18, 6, 31, 200))
        scr.blit(dim, (0, 0))
        if self.state == "ready":
            draw_text(scr, "ROUND 1", 26, CYAN, center=(W // 2, 220))
            draw_text(scr, "NEON RACER", 62, YELLOW, center=(W // 2, 290), shadow=MAGENTA, angle=4)
            draw_text(scr, "ARROWS or A / D to switch lanes", 18, CREAM, center=(W // 2, 380))
            draw_text(scr, "Dodge at the last second for combos", 18, CREAM, center=(W // 2, 410))
            draw_text(scr, "Grab a boost pad and hang on", 18, CREAM, center=(W // 2, 440))
            draw_text(scr, "PRESS ENTER TO FIGHT", 28, YELLOW, center=(W // 2, 520))
        else:
            draw_text(scr, "K.O.!", 96, RED, center=(W // 2, 250), shadow=YELLOW, angle=4)
            draw_text(scr, "{:,}".format(self.score), 52, CREAM, center=(W // 2, 350))
            note = "New personal best!" if getattr(self, "new_best", False) else "Best: {:,}".format(self.best)
            draw_text(scr, note, 20, CYAN, center=(W // 2, 405))
            draw_text(scr, "PRESS ENTER FOR A REMATCH", 26, YELLOW, center=(W // 2, 500))

    def draw(self):
        self.draw_scene(self.scene)

        scr = self.screen
        z = 1 + self.zoom
        if self.zoom > 0.002 or self.shake > 0.3:
            size = (int(W * z), int(H * z))
            scaled = pygame.transform.smoothscale(self.scene, size)
            ox = (W - size[0]) // 2 + random.uniform(-self.shake, self.shake)
            oy = (H - size[1]) // 2 + random.uniform(-self.shake, self.shake)
            scr.fill(INK)
            scr.blit(scaled, (int(ox), int(oy)))
        else:
            scr.blit(self.scene, (0, 0))

        if self.boost:
            scr.blit(self.vignette, (0, 0))
        if self.flash > 0:
            fl = pygame.Surface((W, H))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(clamp(self.flash * 0.5, 0, 0.5) * 255))
            scr.blit(fl, (0, 0))

        self.draw_hud(scr)
        self.draw_overlay_text(scr)
        if self.state == "ready" or (self.state == "over" and self.over_t > 66):
            self.draw_menu(scr)


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Neon Racer")
    clock = pygame.time.Clock()
    game = Game(screen)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    game.move_lane(-1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    game.move_lane(1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and game.state in ("ready", "over"):
                    game.begin()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.state in ("ready", "over"):
                    game.begin()
                else:
                    game.move_lane(-1 if event.pos[0] < W / 2 else 1)

        game.tick_frame()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
