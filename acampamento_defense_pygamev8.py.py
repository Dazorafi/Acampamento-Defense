"""
acampamento_defense_pygame.py
================================

This module contains a self‑contained implementation of the "Última
Noite no Acampamento" defence game using the Pygame library.  It is
based on the gameplay and mechanics of the Tkinter version but takes
advantage of Pygame's hardware accelerated rendering to provide
smoother animation and frame pacing.  The core design mirrors the
HTML version: the player must survive fifteen waves of enemies by
building and repairing walls and traps, collecting resources, and
defeating mini‑bosses and a final boss.

Key differences from the Tkinter version:

* Rendering: Static background elements (trees, rocks, cabin and
  ruin) are drawn once to an off‑screen surface and blitted every
  frame.  Dynamic elements (player, enemies, bullets, structures,
  drops and HUD) are drawn each frame on top of the cached
  background.
* Frame rate: The game loop runs at the configured FPS (default 60).
  Changing the FPS constant allows faster or slower frame pacing.
* Audio: Pygame includes a mixer API but loading external audio
  requires sound files.  To keep the game self‑contained, simple
  procedurally generated tones are used for shooting, hits and
  building.  Music is simulated by looping short tones in a
  background thread when enabled.
* Fullscreen: The pause menu includes a toggle for fullscreen mode.

To run this game you must have Pygame installed.  Install it via

    pip install pygame

Then run the script with

    python acampamento_defense_pygame.py

"""

import pygame
import random
import math
import threading
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

# Constants
WIDTH = 1280
HEIGHT = 720
FPS = 60  # Change this value for a higher or lower frame rate
TAU = math.pi * 2


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def randf(a: float, b: float) -> float:
    return random.uniform(a, b)


def randi(a: int, b: int) -> int:
    return random.randint(a, b)


def rects_overlap(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return not (
        a['x'] + a['w'] < b['x'] or
        a['x'] > b['x'] + b['w'] or
        a['y'] + a['h'] < b['y'] or
        a['y'] > b['y'] + b['h']
    )


def circle_rect_collision(cx: float, cy: float, cr: float,
                          rx: float, ry: float, rw: float, rh: float) -> bool:
    # Check whether a circle and axis‑aligned rectangle intersect or touch.
    nx = clamp(cx, rx, rx + rw)
    ny = clamp(cy, ry, ry + rh)
    dx = cx - nx
    dy = cy - ny
    return dx * dx + dy * dy <= cr * cr


def resolve_circle_rect(ent: Dict[str, float], rect: Dict[str, float]) -> None:
    # Push a circle out of an overlapping rectangle so it no longer intersects.
    nx = clamp(ent['x'], rect['x'], rect['x'] + rect['w'])
    ny = clamp(ent['y'], rect['y'], rect['y'] + rect['h'])
    dx = ent['x'] - nx
    dy = ent['y'] - ny
    d2 = dx * dx + dy * dy
    if d2 < ent['r'] * ent['r']:
        d = math.sqrt(d2) if d2 > 0 else 0.0001
        overlap = ent['r'] - d
        ent['x'] += (dx / d) * overlap
        ent['y'] += (dy / d) * overlap


def line_point_distance(px: float, py: float,
                        x1: float, y1: float,
                        x2: float, y2: float) -> float:
    # Compute the distance from a point to a line segment
    a = px - x1
    b = py - y1
    c = x2 - x1
    d = y2 - y1
    dot = a * c + b * d
    length = c * c + d * d
    t = clamp(dot / (length or 1), 0, 1)
    lx = x1 + c * t
    ly = y1 + d * t
    return math.hypot(px - lx, py - ly)


# Sound player using pygame.mixer for simple tones.  If the mixer
# fails to initialize (e.g. no sound device), the play methods are
# silently ignored.
class SoundPlayer:
    def __init__(self) -> None:
        try:
            pygame.mixer.init()
            self.available = True
        except pygame.error:
            self.available = False
        self.music_on = False
        self._music_thread: Optional[threading.Thread] = None

    def play_tone(self, frequency: int, duration_ms: int, volume: float = 0.5) -> None:
        if not self.available:
            return
        sample_rate = 44100
        n_samples = int(sample_rate * duration_ms / 1000)
        buf = (
            (math.sin(2 * math.pi * frequency * x / sample_rate) for x in range(n_samples))
        )
        # Convert to 16‑bit signed integers
        arr = bytearray()
        for s in buf:
            v = int(s * 32767 * volume)
            arr += int.to_bytes(v, 2, byteorder='little', signed=True)
        sound = pygame.mixer.Sound(buffer=arr)
        sound.play()

    def play_shot(self) -> None:
        self.play_tone(750, 40, 0.4)

    def play_hit(self) -> None:
        self.play_tone(450, 60, 0.5)

    def play_build(self) -> None:
        self.play_tone(600, 80, 0.45)

    def start_music(self) -> None:
        if not self.available or self.music_on:
            return
        self.music_on = True
        def music_loop():
            melody = [196, 246, 293, 246, 174, 196, 220, 246]
            idx = 0
            while self.music_on:
                freq = melody[idx % len(melody)]
                self.play_tone(freq, 120, 0.4)
                time.sleep(0.26)
                idx += 1
        self._music_thread = threading.Thread(target=music_loop, daemon=True)
        self._music_thread.start()

    def stop_music(self) -> None:
        self.music_on = False
        self._music_thread = None


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Última Noite no Acampamento - Pygame")
        self.clock = pygame.time.Clock()
        # Surfaces for static background and dynamic drawing
        self.static_surface = pygame.Surface((WIDTH, HEIGHT))
        self.static_dirty = True
        # Fonts
        self.font = pygame.font.SysFont('arial', 20)
        self.big_font = pygame.font.SysFont('arial', 40)
        # Sound
        self.sound_player = SoundPlayer()
        # Game state
        self.state: str = 'menu'
        self.fullscreen: bool = False
        self.sound_music = True
        self.sound_sfx = True
        # Player & world
        self.reset_game()

    # ------------------------------------------------------------------
    # Utility functions for cabin, ruin and solids
    def cabin_rect(self) -> Dict[str, float]:
        return {'x': WIDTH / 2 - 80, 'y': HEIGHT / 2 - 70, 'w': 160, 'h': 120}

    def ruin_body(self) -> Dict[str, float]:
        return {'x': self.ruin['x'], 'y': self.ruin['y'], 'w': self.ruin['w'], 'h': self.ruin['h']}

    def get_player_solids(self) -> List[Dict[str, float]]:
        solids: List[Dict[str, float]] = []
        c = self.cabin_rect()
        # Four thin rectangles forming a border around the cabin to prevent player overlap
        solids.append({'x': c['x'], 'y': c['y'], 'w': c['w'], 'h': 10})
        solids.append({'x': c['x'], 'y': c['y'] + c['h'] - 10, 'w': c['w'], 'h': 10})
        solids.append({'x': c['x'], 'y': c['y'], 'w': 10, 'h': c['h']})
        solids.append({'x': c['x'] + c['w'] - 10, 'y': c['y'], 'w': 10, 'h': c['h']})
        r = self.ruin_body()
        if not self.ruin['unlocked']:
            solids.append({'x': r['x'], 'y': r['y'], 'w': r['w'], 'h': 10})
            solids.append({'x': r['x'], 'y': r['y'], 'w': 10, 'h': r['h']})
            solids.append({'x': r['x'] + r['w'] - 10, 'y': r['y'], 'w': 10, 'h': r['h']})
            # Two segments at bottom leaving a door gap
            solids.append({'x': r['x'], 'y': r['y'] + r['h'] - 10, 'w': 54, 'h': 10})
            solids.append({'x': r['x'] + 96, 'y': r['y'] + r['h'] - 10, 'w': r['w'] - 96, 'h': 10})
        solids.extend(self.rocks)
        for s in self.structures:
            if s['type'] == 'wall' and not s['broken']:
                solids.append({'x': s['x'], 'y': s['y'], 'w': s['w'], 'h': s['h']})
        return solids

    def get_enemy_solids(self) -> List[Dict[str, float]]:
        solids = [self.cabin_rect(), self.ruin_body()]
        for s in self.structures:
            if s['type'] == 'wall' and not s['broken']:
                solids.append({'x': s['x'], 'y': s['y'], 'w': s['w'], 'h': s['h']})
        return solids

    # ------------------------------------------------------------------
    # Game reset and wave management
    def reset_game(self) -> None:
        """Reset all game data to initial state."""
        # Game state parameters
        self.wave = 0
        self.max_wave = 15
        self.prep_time = 45
        self.prep_remaining = 45
        self.in_preparation = True
        self.message = 'Pressione Espaço ou Enter para iniciar'
        self.score = 0
        self.kills = 0
        self.boss_bar = None
        self.current_build: Optional[str] = None  # 'wall' or 'trap'
        self.build_rotation = 0
        self.has_ruin_key = False
        self.reward_granted = False
        # Audio volumes (0..1).  Using sliders in the menu you can mute sounds by setting volume to 0.
        self.music_volume: float = 1.0
        self.sfx_volume: float = 1.0
        # Rects for interactive UI (start button, sliders) will be set during draw
        self.menu_start_rect = None
        self.music_slider_rect = None
        self.sfx_slider_rect = None
        # Pause UI interactive elements
        self.pause_resume_rect = None
        self.pause_restart_rect = None
        self.pause_fullscreen_rect = None
        self.pause_music_slider_rect = None
        self.pause_sfx_slider_rect = None
        # Entities
        self.enemies: List[Dict] = []
        self.bullets: List[Dict] = []
        self.enemy_bullets: List[Dict] = []
        self.drops: List[Dict] = []
        self.structures: List[Dict] = []
        self.effects: List[Dict] = []
        self.telegraphs: List[Dict] = []
        self.spawn_queue: List[str] = []
        self.spawn_timer = 0
        # Player and camp
        self.player = {
            'x': WIDTH / 2, 'y': HEIGHT / 2 + 80, 'r': 16, 'speed': 220,
            'hp': 100, 'maxHp': 100, 'weapon': 'pistol', 'damage': 10,
            'cooldown': 0, 'invuln': 0, 'wood': 10, 'stone': 5
        }
        self.camp = {'hp': 150, 'maxHp': 150}
        self.ruin = {'x': WIDTH - 270, 'y': 120, 'w': 150, 'h': 110, 'unlocked': False}
        self.chest = {'x': self.ruin['x'] + 55, 'y': self.ruin['y'] + 40, 'w': 40, 'h': 28, 'opened': False}
        # Trees and rocks randomly placed around the arena edges
        self.trees: List[Dict[str, float]] = []
        self.rocks: List[Dict[str, float]] = []
        for i in range(32):
            side = i % 4
            x = y = 0
            if side == 0:
                x, y = randf(40, WIDTH - 40), randf(20, 90)
            elif side == 1:
                x, y = randf(40, WIDTH - 40), randf(HEIGHT - 90, HEIGHT - 20)
            elif side == 2:
                x, y = randf(20, 90), randf(40, HEIGHT - 40)
            else:
                x, y = randf(WIDTH - 90, WIDTH - 20), randf(40, HEIGHT - 40)
            if (WIDTH / 2 - 180 < x < WIDTH / 2 + 180 and
                HEIGHT / 2 - 150 < y < HEIGHT / 2 + 150):
                continue
            self.trees.append({'x': x, 'y': y, 'r': randf(18, 30)})
        for _ in range(8):
            x, y = randf(140, WIDTH - 140), randf(140, HEIGHT - 140)
            w, h = randf(42, 72), randf(26, 52)
            # Keep clear of the central play area and the ruin
            if (WIDTH / 2 - 210 < x < WIDTH / 2 + 210 and
                HEIGHT / 2 - 170 < y < HEIGHT / 2 + 170):
                continue
            if (self.ruin['x'] - 60 < x < self.ruin['x'] + self.ruin['w'] + 60 and
                self.ruin['y'] - 60 < y < self.ruin['y'] + self.ruin['h'] + 60):
                continue
            self.rocks.append({'x': x, 'y': y, 'w': w, 'h': h})
        # Mark static surface dirty so it will be redrawn
        self.static_dirty = True
        # Stop any music when resetting
        self.sound_player.stop_music()

    def start_run(self) -> None:
        self.reset_game()
        self.state = 'playing'
        # Use the configured preparation time for the countdown instead of a fixed 5s value
        self.prep_remaining = self.prep_time
        self.message = 'Prepare‑se para a primeira onda'
        # Start background music if volume is above zero
        if getattr(self, 'music_volume', 1.0) > 0:
            self.sound_player.start_music()

    # ------------------------------------------------------------------
    # Enemy spawning and wave management
    def build_spawn_queue_for_wave(self, wave: int) -> List[str]:
        if wave == 5:
            return ['miniboss1']
        if wave == 10:
            return ['miniboss2']
        if wave == 15:
            return ['boss']
        queue: List[str] = []
        count = 4 + wave * 2
        for _ in range(count):
            roll = random.random()
            typ = 'basic'
            if wave >= 3 and roll > 0.45:
                typ = 'fast'
            if wave >= 7 and roll > 0.78:
                typ = 'tank'
            queue.append(typ)
        return queue

    def start_wave(self) -> None:
        self.wave += 1
        if self.wave > self.max_wave:
            self.state = 'victory'
            self.message = 'Você salvou o acampamento!'
            return
        self.in_preparation = False
        self.prep_remaining = self.prep_time
        self.message = f'Wave {self.wave}'
        self.spawn_queue = self.build_spawn_queue_for_wave(self.wave)
        self.spawn_timer = 0.1
        # Cancel any build preview when the wave begins.  Building is only allowed during preparation.
        self.current_build = None

    def spawn_enemy(self, typ: str) -> None:
        # Spawn an enemy off‑screen on one of four edges
        side = randi(0, 3)
        if side == 0:
            x, y = randf(0, WIDTH), -30
        elif side == 1:
            x, y = WIDTH + 30, randf(0, HEIGHT)
        elif side == 2:
            x, y = randf(0, WIDTH), HEIGHT + 30
        else:
            x, y = -30, randf(0, HEIGHT)
        stats = {
            'basic': dict(hp=30, speed=92, damage=10, r=14, color=(201, 92, 84), score=10, wood=(1, 2), stone=(0, 1)),
            'fast': dict(hp=20, speed=140, damage=8, r=12, color=(244, 162, 97), score=15, wood=(1, 2), stone=(0, 1)),
            'tank': dict(hp=60, speed=58, damage=15, r=18, color=(122, 143, 99), score=25, wood=(2, 3), stone=(1, 2)),
            'miniboss1': dict(hp=275, speed=70, damage=20, r=28, color=(214, 40, 40), score=120, wood=(12, 15), stone=(8, 10), boss=True, key=True),
            'miniboss2': dict(hp=400, speed=80, damage=25, r=30, color=(157, 78, 237), score=180, wood=(15, 18), stone=(10, 14), boss=True),
            'boss': dict(hp=775, speed=84, damage=30, r=36, color=(255, 0, 110), score=500, wood=(25, 30), stone=(18, 24), boss=True, finalBoss=True),
        }[typ]
        # Guarantee that every enemy drops at least one wood and one stone.  The original
        # HTML/Tk version always rewarded both resources upon a kill, so if the random
        # ranges generate zero we clamp them to one.  This change ensures more
        # consistent resource collection across waves.
        dropW = randi(*stats['wood'])
        dropS = randi(*stats['stone'])
        if dropW <= 0:
            dropW = 1
        if dropS <= 0:
            dropS = 1
        e = {
            'type': typ, 'x': x, 'y': y, 'r': stats['r'], 'hp': stats['hp'], 'maxHp': stats['hp'],
            'speed': stats['speed'], 'damage': stats['damage'], 'color': stats['color'], 'score': stats['score'],
            'dropWood': dropW, 'dropStone': dropS,
            'boss': stats.get('boss', False), 'finalBoss': stats.get('finalBoss', False), 'key': stats.get('key', False),
            'hitFlash': 0, 'attackCd': 0, 'laserCd': 4 if typ == 'boss' else 999, 'shootCd': 1.5 if typ in ('miniboss2', 'boss') else 999
        }
        self.enemies.append(e)
        if e['boss']:
            self.boss_bar = e

    # ------------------------------------------------------------------
    # Damage handlers
    def damage_player(self, amount: float) -> None:
        p = self.player
        if p['invuln'] > 0 or self.state != 'playing':
            return
        p['hp'] -= amount
        p['invuln'] = 0.35
        self.effects.append({'x': p['x'], 'y': p['y'], 'r': 18, 'life': 0.2, 'color': (255, 107, 107)})
        if p['hp'] <= 0:
            p['hp'] = 0
            self.state = 'gameover'
            self.message = 'Game Over'

    def damage_camp(self, amount: float) -> None:
        if self.state != 'playing':
            return
        self.camp['hp'] -= amount
        self.effects.append({'x': WIDTH / 2, 'y': HEIGHT / 2, 'r': 28, 'life': 0.22, 'color': (249, 115, 22)})
        if self.camp['hp'] <= 0:
            self.camp['hp'] = 0
            self.state = 'gameover'
            self.message = 'O acampamento foi destruído'

    def damage_structure(self, s: Dict, amount: float) -> None:
        s['hp'] -= amount
        if s['hp'] <= 0:
            self.structure_break(s)

    # ------------------------------------------------------------------
    # Entity management
    def kill_enemy(self, e: Dict) -> None:
        # Award resources and points, spawn drops
        self.score += e['score']
        self.kills += 1
        if e['key']:
            self.drops.append({'type': 'key', 'x': e['x'], 'y': e['y'], 'r': 10, 'color': (255, 215, 0)})
        else:
            # Spawn drops for both wood and stone with slight offsets so they don't overlap visually
            if e['dropWood']:
                self.drops.append({'type': 'wood', 'amount': e['dropWood'], 'x': e['x'] - 10, 'y': e['y'], 'r': 8, 'color': (140, 95, 40)})
            if e['dropStone']:
                self.drops.append({'type': 'stone', 'amount': e['dropStone'], 'x': e['x'] + 10, 'y': e['y'], 'r': 8, 'color': (140, 140, 140)})
        self.enemies.remove(e)
        if e is self.boss_bar:
            self.boss_bar = None

    def structure_break(self, s: Dict) -> None:
        s['broken'] = True
        s['hp'] = 0
        # After breaking, structures no longer block enemies or damage

    # ------------------------------------------------------------------
    # Shooting and building
    def player_shoot(self) -> None:
        p = self.player
        if p['cooldown'] > 0:
            return
        mouse_buttons = pygame.mouse.get_pressed()
        if not mouse_buttons[0]:
            return
        # Direction towards mouse pointer
        mx, my = pygame.mouse.get_pos()
        ang = math.atan2(my - p['y'], mx - p['x'])
        speed = 540 if p['weapon'] == 'rifle' else 420
        damage = 22 if p['weapon'] == 'rifle' else p['damage']
        self.bullets.append({
            'x': p['x'], 'y': p['y'],
            'vx': math.cos(ang) * speed,
            'vy': math.sin(ang) * speed,
            'r': 6, 'life': 2.5, 'damage': damage
        })
        p['cooldown'] = 0.18 if p['weapon'] == 'rifle' else 0.35
        # Play sfx only if volume > 0
        if getattr(self, 'sfx_volume', 1.0) > 0:
            self.sound_player.play_shot()

    def place_structure(self) -> None:
        # Handle building/trap placement on right click
        p = self.player
        if self.current_build is None:
            return
        # Use right click for placement
        # To avoid building on continuous press, check for a one‑off event
        # This uses pygame.MOUSEBUTTONDOWN in event loop instead
        pass

    def interact(self) -> None:
        """Handle interaction key presses (opening ruin door, chest, repairs).

        When the player presses E while playing, this method checks their
        proximity to interactable objects and performs the corresponding
        action.  The player can unlock the ruin if they have the key, open
        the chest once the ruin is unlocked, and receive the rifle reward.
        Future upgrades or repairs could be added here as well.
        """
        if self.state != 'playing':
            return
        # Player position
        px, py = self.player['x'], self.player['y']
        # Door rectangle on the ruin
        door_rect = pygame.Rect(self.ruin['x'] + 54, self.ruin['y'] + self.ruin['h'] - 10, 42, 12)
        # Chest rectangle inside ruin
        chest_rect = pygame.Rect(self.chest['x'], self.chest['y'], self.chest['w'], self.chest['h'])
        # Attempt to unlock ruin
        if not self.ruin['unlocked'] and door_rect.collidepoint(px, py):
            if self.has_ruin_key:
                self.ruin['unlocked'] = True
                self.message = 'Ruína aberta!'
            else:
                self.message = 'Precisa da chave para abrir a ruína'
            return
        # Attempt to open chest inside ruin
        if self.ruin['unlocked'] and chest_rect.collidepoint(px, py):
            if not self.chest['opened']:
                self.chest['opened'] = True
                if not self.reward_granted:
                    # Grant rifle reward to player
                    self.player['weapon'] = 'rifle'
                    self.player['damage'] = 22
                    self.reward_granted = True
                    self.message = 'Você encontrou um rifle no baú!'
                else:
                    self.message = 'O baú está vazio'
            return

        # Attempt to repair or upgrade nearby structure
        # Check each structure to see if player is overlapping
        for s in self.structures:
            if circle_rect_collision(px, py, self.player['r'], s['x'], s['y'], s['w'], s['h']):
                # First: repair if the structure has taken damage or is broken
                # We treat any HP below max or broken flag as requiring a repair
                if s['broken'] or s['hp'] < s['maxHp']:
                    cost = 2
                    if self.player['wood'] >= cost:
                        self.player['wood'] -= cost
                        s['broken'] = False
                        s['hp'] = s['maxHp']
                        self.message = 'Estrutura reparada'
                        if getattr(self, 'sfx_volume', 1.0) > 0:
                            self.sound_player.play_build()
                    else:
                        self.message = 'Madeira insuficiente para reparar'
                    return
                # Otherwise, if the structure is intact and level 1, upgrade it
                if s['type'] == 'wall' and s['level'] == 1:
                    cost = 5
                    if self.player['stone'] >= cost:
                        self.player['stone'] -= cost
                        s['level'] = 2
                        s['maxHp'] = 150
                        s['hp'] = 150
                        self.message = 'Parede aprimorada'
                        if getattr(self, 'sfx_volume', 1.0) > 0:
                            self.sound_player.play_build()
                    else:
                        self.message = 'Pedra insuficiente para melhorar'
                    return
                if s['type'] == 'trap' and s['level'] == 1:
                    cost = 4
                    if self.player['stone'] >= cost:
                        self.player['stone'] -= cost
                        s['level'] = 2
                        s['maxHp'] = 60
                        s['hp'] = 60
                        self.message = 'Armadilha aprimorada'
                        if getattr(self, 'sfx_volume', 1.0) > 0:
                            self.sound_player.play_build()
                    else:
                        self.message = 'Pedra insuficiente para melhorar'
                    return

    # ------------------------------------------------------------------
    # Update logic
    def update(self, dt: float) -> None:
        if self.state == 'menu':
            return
        # Handle pause toggle
        # Pause state logic handled in event loop for clarity
        # Preparation countdown
        if self.state == 'playing':
            # Update player timers
            p = self.player
            p['invuln'] = max(0.0, p['invuln'] - dt)
            p['cooldown'] = max(0.0, p['cooldown'] - dt)
            # Movement
            keys = pygame.key.get_pressed()
            mx = (-1 if keys[pygame.K_a] else 0) + (1 if keys[pygame.K_d] else 0)
            my = (-1 if keys[pygame.K_w] else 0) + (1 if keys[pygame.K_s] else 0)
            if mx != 0 or my != 0:
                ln = math.hypot(mx, my)
                mx /= ln
                my /= ln
                # Move player and resolve against obstacles
                p['x'] += mx * p['speed'] * dt
                p['y'] += my * p['speed'] * dt
                # Clamp to screen
                p['x'] = clamp(p['x'], p['r'], WIDTH - p['r'])
                p['y'] = clamp(p['y'], p['r'], HEIGHT - p['r'])
                # Resolve collisions with solids
                for rect in self.get_player_solids():
                    resolve_circle_rect(p, rect)
            # Shooting
            self.player_shoot()
            # Building and interactions (to be implemented)
            # Preparation phase
            if self.in_preparation:
                self.prep_remaining -= dt
                # Skip with space or enter
                keys_pressed = pygame.key.get_pressed()
                if keys_pressed[pygame.K_SPACE] or keys_pressed[pygame.K_RETURN]:
                    self.prep_remaining = 0
                if self.prep_remaining <= 0:
                    self.start_wave()
            else:
                # Spawn enemies gradually
                self.spawn_timer -= dt
                if self.spawn_queue and self.spawn_timer <= 0:
                    self.spawn_enemy(self.spawn_queue.pop(0))
                    self.spawn_timer = 0.55 if self.wave < 8 else 0.35
            # Update bullets
            for b in self.bullets[:]:
                b['x'] += b['vx'] * dt
                b['y'] += b['vy'] * dt
                b['life'] -= dt
                # Remove off screen or expired
                if (b['life'] <= 0 or b['x'] < -40 or b['x'] > WIDTH + 40 or
                        b['y'] < -40 or b['y'] > HEIGHT + 40):
                    self.bullets.remove(b)
                    continue
                # Check collision with enemies
                hit = False
                for e in self.enemies[:]:
                    if math.hypot(b['x'] - e['x'], b['y'] - e['y']) <= b['r'] + e['r']:
                        e['hp'] -= b['damage']
                        e['hitFlash'] = 0.08
                        if e['hp'] <= 0:
                            self.kill_enemy(e)
                        if b in self.bullets:
                            self.bullets.remove(b)
                        hit = True
                        break
                if hit:
                    continue
                # Bullets hitting walls
                for s in self.structures:
                    if (s['type'] == 'wall' and not s['broken'] and
                            circle_rect_collision(b['x'], b['y'], b['r'], s['x'], s['y'], s['w'], s['h'])):
                        if b in self.bullets:
                            self.bullets.remove(b)
                        break
            # Enemy bullets
            for b in self.enemy_bullets[:]:
                b['x'] += b['vx'] * dt
                b['y'] += b['vy'] * dt
                b['life'] -= dt
                if b['life'] <= 0:
                    self.enemy_bullets.remove(b)
                    continue
                if math.hypot(b['x'] - p['x'], b['y'] - p['y']) <= b['r'] + p['r']:
                    self.damage_player(b['damage'])
                    if b in self.enemy_bullets:
                        self.enemy_bullets.remove(b)
                    continue
                camp_rect = self.cabin_rect()
                if circle_rect_collision(b['x'], b['y'], b['r'], camp_rect['x'], camp_rect['y'], camp_rect['w'], camp_rect['h']):
                    self.damage_camp(b['damage'])
                    if b in self.enemy_bullets:
                        self.enemy_bullets.remove(b)
                    continue
                removed = False
                for s in self.structures:
                    if (s['type'] == 'wall' and not s['broken'] and
                            circle_rect_collision(b['x'], b['y'], b['r'], s['x'], s['y'], s['w'], s['h'])):
                        self.damage_structure(s, b['damage'])
                        if b in self.enemy_bullets:
                            self.enemy_bullets.remove(b)
                        removed = True
                        break
                if removed:
                    continue
            # Drops
            for d in self.drops[:]:
                if math.hypot(d['x'] - p['x'], d['y'] - p['y']) <= d['r'] + p['r'] + 2:
                    if d['type'] == 'wood':
                        p['wood'] += d['amount']
                    elif d['type'] == 'stone':
                        p['stone'] += d['amount']
                    elif d['type'] == 'key':
                        self.has_ruin_key = True
                        self.message = 'Chave da ruína obtida'
                    self.drops.remove(d)
            # Traps damage
            for s in self.structures:
                if s['type'] == 'trap' and not s['broken']:
                    s['tick'] = s.get('tick', 0) - dt
                    for e in self.enemies[:]:
                        if circle_rect_collision(e['x'], e['y'], e['r'], s['x'], s['y'], s['w'], s['h']):
                            if s['tick'] <= 0:
                                e['hp'] -= 8 if s['level'] == 1 else 14
                                s['tick'] = 0.35
                                if e['hp'] <= 0:
                                    self.kill_enemy(e)
                                    break
            # Enemies
            for e in self.enemies[:]:
                e['hitFlash'] = max(0.0, e['hitFlash'] - dt)
                e['attackCd'] = max(0.0, e['attackCd'] - dt)
                e['shootCd'] = max(0.0, e['shootCd'] - dt)
                e['laserCd'] = max(0.0, e['laserCd'] - dt)
                # Pursue player
                ang = math.atan2(p['y'] - e['y'], p['x'] - e['x'])
                vx = math.cos(ang) * e['speed']
                vy = math.sin(ang) * e['speed']
                # Move enemy
                e['x'] += vx * dt
                e['y'] += vy * dt
                # Clamp to play area
                e['x'] = clamp(e['x'], -40, WIDTH + 40)
                e['y'] = clamp(e['y'], -40, HEIGHT + 40)
                # Resolve collisions against camp, ruin and walls
                for rect in self.get_enemy_solids():
                    resolve_circle_rect(e, rect)
                # Enemy shooting
                if e['shootCd'] <= 0 and math.hypot(e['x'] - p['x'], e['y'] - p['y']) < 460:
                    self.enemy_shoot(e)
                    e['shootCd'] = 1.35 if e['finalBoss'] else 1.85
                # Boss laser
                if e['finalBoss'] and e['laserCd'] <= 0:
                    self.spawn_laser(e)
                    e['laserCd'] = 3.2
                # Damage player if overlapping
                if math.hypot(e['x'] - p['x'], e['y'] - p['y']) < e['r'] + p['r'] + 2 and e['attackCd'] <= 0:
                    self.damage_player(e['damage'])
                    e['attackCd'] = 0.7
                # Damage camp on collision
                camp_rect = self.cabin_rect()
                if circle_rect_collision(e['x'], e['y'], e['r'], camp_rect['x'], camp_rect['y'], camp_rect['w'], camp_rect['h']) and e['attackCd'] <= 0:
                    self.damage_camp(e['damage'])
                    e['attackCd'] = 0.8
                # Damage walls or traps when enemies collide with them.  Walls and traps
                # can be broken by enemy attacks.  This loop will break after
                # damaging one structure to avoid double hits in the same frame.
                for s in self.structures:
                    if (not s['broken'] and
                            circle_rect_collision(e['x'], e['y'], e['r'], s['x'], s['y'], s['w'], s['h']) and
                            e['attackCd'] <= 0):
                        # Damage structure regardless of type; walls and traps take
                        # the same amount of damage from enemies.  After breaking,
                        # the structure will no longer block or harm enemies.
                        self.damage_structure(s, e['damage'])
                        e['attackCd'] = 0.7
                        break
            # Lasers telegraphs update
            for t in self.telegraphs[:]:
                if t['timer'] > 0:
                    t['timer'] -= dt
                else:
                    t['activeTimer'] -= dt
                    if not t['dealt']:
                        if line_point_distance(p['x'], p['y'], t['x1'], t['y1'], t['x2'], t['y2']) <= p['r'] + 7:
                            self.damage_player(t['damage'])
                        t['dealt'] = True
                    if t['activeTimer'] <= 0:
                        self.telegraphs.remove(t)
            # Effects fade
            for fx in self.effects[:]:
                fx['life'] -= dt
                if fx['life'] <= 0:
                    self.effects.remove(fx)
            # Check if wave ends
            self.end_wave_if_clear()

    def enemy_shoot(self, enemy: Dict) -> None:
        ang = math.atan2(self.player['y'] - enemy['y'], self.player['x'] - enemy['x'])
        speed = 240 if enemy['finalBoss'] else 180
        self.enemy_bullets.append({
            'x': enemy['x'], 'y': enemy['y'],
            'vx': math.cos(ang) * speed, 'vy': math.sin(ang) * speed,
            'r': 7 if enemy['finalBoss'] else 5, 'life': 4,
            'damage': 14 if enemy['finalBoss'] else 10,
            'color': (255, 0, 110) if enemy['finalBoss'] else (214, 40, 40)
        })

    def spawn_laser(self, enemy: Dict) -> None:
        """
        Spawn a telegraphed laser attack from the boss.

        Instead of a random orientation, the laser now aligns to the
        vector from the boss to the current player position.  This
        makes the attack target the player's location directly, with
        warning before it becomes active.  The line extends in both
        directions from the boss so it appears infinite across the
        arena.  The telegraph includes a short warning phase before
        dealing damage.
        """
        # Determine angle towards the player so the laser passes over them
        px, py = self.player['x'], self.player['y']
        bx, by = enemy['x'], enemy['y']
        ang = math.atan2(py - by, px - bx)
        length = 640
        x1 = bx - math.cos(ang) * length
        y1 = by - math.sin(ang) * length
        x2 = bx + math.cos(ang) * length
        y2 = by + math.sin(ang) * length
        self.telegraphs.append({
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            'timer': 0.6, 'activeTimer': 0.65,
            'dealt': False, 'damage': 22
        })

    def spawn_laser_warning(self, enemy: Dict) -> None:
        pass

    def end_wave_if_clear(self) -> None:
        if self.in_preparation:
            return
        if not self.enemies and not self.spawn_queue:
            self.in_preparation = True
            self.prep_remaining = 45
            self.message = f'Onda {self.wave} concluída. Prepare‑se!'
            # Heal player partially between waves.  The camp does not regenerate.
            self.player['hp'] = min(self.player['maxHp'], self.player['hp'] + self.player['maxHp'] * 0.1)

    # ------------------------------------------------------------------
    # Drawing routines
    def draw_static(self) -> None:
        """Draw the static background onto the off‑screen surface."""
        self.static_surface.fill((24, 35, 28))
        # darker borders
        border_color = (26, 42, 32)
        pygame.draw.rect(self.static_surface, border_color, (0, 0, WIDTH, 110))
        pygame.draw.rect(self.static_surface, border_color, (0, HEIGHT - 110, WIDTH, 110))
        pygame.draw.rect(self.static_surface, border_color, (0, 0, 110, HEIGHT))
        pygame.draw.rect(self.static_surface, border_color, (WIDTH - 110, 0, 110, HEIGHT))
        # Trees
        for t in self.trees:
            pygame.draw.circle(self.static_surface, (49, 92, 43), (int(t['x']), int(t['y'])), int(t['r']))
            pygame.draw.circle(self.static_surface, (29, 59, 35), (int(t['x']), int(t['y'])), int(t['r']), 2)
        # Rocks
        for r in self.rocks:
            rect = pygame.Rect(r['x'], r['y'], r['w'], r['h'])
            pygame.draw.rect(self.static_surface, (94, 100, 114), rect)
            pygame.draw.rect(self.static_surface, (66, 71, 85), rect, 2)
        # Cabin body
        c = self.cabin_rect()
        cab_rect = pygame.Rect(c['x'], c['y'], c['w'], c['h'])
        pygame.draw.rect(self.static_surface, (127, 85, 57), cab_rect)
        pygame.draw.rect(self.static_surface, (74, 44, 27), cab_rect, 3)
        # Cabin door
        door_rect = pygame.Rect(c['x'] + 55, c['y'] + 70, 50, 50)
        pygame.draw.rect(self.static_surface, (59, 42, 29), door_rect)
        # Cabin roof
        pygame.draw.polygon(self.static_surface, (109, 63, 45), [
            (c['x'] - 10, c['y']), (c['x'] + c['w'] / 2, c['y'] - 40), (c['x'] + c['w'] + 10, c['y'])
        ])
        pygame.draw.lines(self.static_surface, (74, 44, 27), True, [
            (c['x'] - 10, c['y']), (c['x'] + c['w'] / 2, c['y'] - 40), (c['x'] + c['w'] + 10, c['y'])
        ], 3)
        # Ruin shell
        r = self.ruin
        ruin_rect = pygame.Rect(r['x'], r['y'], r['w'], r['h'])
        pygame.draw.rect(self.static_surface, (79, 79, 79), ruin_rect)
        pygame.draw.rect(self.static_surface, (34, 34, 34), ruin_rect, 3)
        # Mark clean
        self.static_dirty = False

    def draw_health_bar(self, x: float, y: float, w: float, h: float, frac: float, color: Tuple[int, int, int]) -> None:
        frac = clamp(frac, 0.0, 1.0)
        bg_rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (45, 53, 45), bg_rect)
        fg_rect = pygame.Rect(x, y, w * frac, h)
        pygame.draw.rect(self.screen, color, fg_rect)
        pygame.draw.rect(self.screen, (0, 0, 0), bg_rect, 1)

    def draw(self) -> None:
        # Draw static background if needed
        if self.static_dirty:
            self.draw_static()
        self.screen.blit(self.static_surface, (0, 0))
        if self.state == 'menu':
            self.draw_menu()
            return
        if self.state in ('gameover', 'victory'):
            # Fade dark overlay
            overlay = pygame.Surface((WIDTH, HEIGHT), flags=pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 128))
            self.screen.blit(overlay, (0, 0))
            self.draw_end()
            return
        # Draw dynamic world elements
        # Cabin and player health bars at top-left of screen.
        # Enlarge the bars and use wider margins so damage is more visible.
        p = self.player
        # Use larger health bars to make damage more noticeable
        bar_w = 260
        bar_h = 22
        # Player HP bar
        pygame.draw.rect(self.screen, (70, 70, 70), (20, 16, bar_w, bar_h))
        pygame.draw.rect(self.screen, (190, 50, 50), (20, 16, bar_w * max(0.0, p['hp'] / p['maxHp']), bar_h))
        hp_text = self.font.render(f"HP {int(p['hp'])}/{p['maxHp']}", True, (255, 255, 255))
        # Center text vertically within the bar
        self.screen.blit(hp_text, (20 + 4, 16 + (bar_h - hp_text.get_height()) / 2))
        # Camp HP bar below
        bar_y = 16 + bar_h + 6
        pygame.draw.rect(self.screen, (70, 70, 70), (20, bar_y, bar_w, bar_h))
        pygame.draw.rect(self.screen, (249, 115, 22), (20, bar_y, bar_w * max(0.0, self.camp['hp'] / self.camp['maxHp']), bar_h))
        camp_text = self.font.render(f"Camp {int(self.camp['hp'])}/{self.camp['maxHp']}", True, (255, 255, 255))
        self.screen.blit(camp_text, (20 + 4, bar_y + (bar_h - camp_text.get_height()) / 2))

        # Show preparation countdown timer at top centre when in preparation
        if self.state == 'playing' and self.in_preparation:
            # Show the number of seconds remaining until the next wave
            secs = max(0.0, self.prep_remaining)
            timer_surf = self.big_font.render(f"Próxima onda em {int(math.ceil(secs))}", True, (255, 255, 255))
            self.screen.blit(timer_surf, (WIDTH / 2 - timer_surf.get_width() / 2, 16))

        # Cabin health bar above cabin as before
        c = self.cabin_rect()
        # Show a thicker camp bar above the cabin to match the enlarged HUD bars
        self.draw_health_bar(c['x'], c['y'] - 22, c['w'], 14, self.camp['hp'] / self.camp['maxHp'], (249, 115, 22))
        # Ruin door and chest
        r = self.ruin
        door_rect = pygame.Rect(r['x'] + 54, r['y'] + r['h'] - 10, 42, 12)
        if not r['unlocked']:
            pygame.draw.rect(self.screen, (139, 94, 52), door_rect)
        else:
            pygame.draw.rect(self.screen, (26, 26, 26), door_rect)
        if r['unlocked']:
            chest_color = (212, 163, 115) if not self.chest['opened'] else (122, 92, 62)
            chest_rect = pygame.Rect(self.chest['x'], self.chest['y'], self.chest['w'], self.chest['h'])
            pygame.draw.rect(self.screen, chest_color, chest_rect)
            pygame.draw.rect(self.screen, (61, 44, 26), chest_rect, 2)
        # Structures
        # Also determine if a repair/upgrade hint should be shown
        hint_text = None
        hint_pos = None
        for s in self.structures:
            if s['type'] == 'wall':
                if s['broken']:
                    base_color = (120, 101, 90)
                else:
                    base_color = (141, 85, 36) if s['level'] == 1 else (109, 78, 59)
                outline = (43, 27, 18)
                rect = pygame.Rect(s['x'], s['y'], s['w'], s['h'])
                pygame.draw.rect(self.screen, base_color, rect)
                pygame.draw.rect(self.screen, outline, rect, 1)
            else:  # trap
                if s['broken']:
                    base_color = (117, 77, 85)
                else:
                    base_color = (193, 18, 31) if s['level'] == 1 else (224, 163, 62)
                outline = (92, 11, 22)
                rect = pygame.Rect(s['x'], s['y'], s['w'], s['h'])
                pygame.draw.rect(self.screen, base_color, rect)
                pygame.draw.rect(self.screen, outline, rect, 1)
                if not s['broken']:
                    line_color = (255, 214, 214) if s['level'] == 1 else (255, 243, 194)
                    pygame.draw.line(self.screen, line_color, rect.topleft, rect.bottomright, 2)
                    pygame.draw.line(self.screen, line_color, rect.topright, rect.bottomleft, 2)
            # Health bar for structure
            if not s['broken']:
                self.draw_health_bar(s['x'], s['y'] - 6, s['w'], 4, s['hp'] / s['maxHp'], (34, 197, 94))
            # Determine if the player is overlapping this structure to show a hint
            if hint_text is None:
                if circle_rect_collision(self.player['x'], self.player['y'], self.player['r'], s['x'], s['y'], s['w'], s['h']):
                    if s['broken']:
                        hint_text = 'E: Reparar'
                    else:
                        if s['type'] == 'wall' and s['level'] == 1:
                            hint_text = 'E: Melhorar Parede'
                        elif s['type'] == 'trap' and s['level'] == 1:
                            hint_text = 'E: Melhorar Armadilha'
                    if hint_text:
                        hint_pos = (s['x'] + s['w'] / 2, s['y'])
        # After iterating structures, draw the hint if any
        if hint_text:
            hint_surf = self.font.render(hint_text, True, (255, 255, 150))
            hx = hint_pos[0] - hint_surf.get_width() / 2
            hy = hint_pos[1] - 18
            # Draw a subtle background for the hint to improve contrast
            bg_rect = pygame.Rect(hx - 4, hy - 2, hint_surf.get_width() + 8, hint_surf.get_height() + 4)
            pygame.draw.rect(self.screen, (0, 0, 0, 160), bg_rect)
            self.screen.blit(hint_surf, (hx, hy))
        # Drops
        for d in self.drops:
            pygame.draw.circle(self.screen, d['color'], (int(d['x']), int(d['y'])), int(d['r']))
        # Bullets
        for b in self.bullets:
            pygame.draw.circle(self.screen, (255, 209, 102), (int(b['x']), int(b['y'])), int(b['r']))
        for b in self.enemy_bullets:
            pygame.draw.circle(self.screen, b.get('color', (214, 40, 40)), (int(b['x']), int(b['y'])), int(b['r']))
        # Lasers telegraphs
        for t in self.telegraphs:
            # Warning: semi‑transparent line when timer>0, opaque when active
            if t['timer'] > 0:
                alpha = int(255 * (1 - t['timer'] / 0.6))
                color = (255, 87, 51, alpha)
            else:
                color = (255, 87, 51, 255)
            surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.line(surf, color, (t['x1'], t['y1']), (t['x2'], t['y2']), 4)
            self.screen.blit(surf, (0, 0))
        # Effects
        for fx in self.effects:
            alpha = int(255 * clamp(fx['life'] / 0.5, 0.0, 1.0))
            surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*fx['color'], alpha), (int(fx['x']), int(fx['y'])), int(fx['r']))
            self.screen.blit(surf, (0, 0))
        # Enemies
        for e in self.enemies:
            color = e['color']
            if e['hitFlash'] > 0:
                flash = clamp(e['hitFlash'] / 0.08, 0.0, 1.0)
                color = (
                    min(255, int(color[0] + 100 * flash)),
                    min(255, int(color[1] + 100 * flash)),
                    min(255, int(color[2] + 100 * flash)),
                )
            pygame.draw.circle(self.screen, color, (int(e['x']), int(e['y'])), int(e['r']))
            # Health bar
            self.draw_health_bar(e['x'] - e['r'], e['y'] - e['r'] - 6, e['r'] * 2, 4, e['hp'] / e['maxHp'], (34, 197, 94))
        # Player
        pygame.draw.circle(self.screen, (63, 114, 175), (int(self.player['x']), int(self.player['y'])), self.player['r'])
        # Player facing barrel
        mx, my = pygame.mouse.get_pos()
        ang = math.atan2(my - self.player['y'], mx - self.player['x'])
        barrel_len = self.player['r'] + 6
        bx = self.player['x'] + math.cos(ang) * barrel_len
        by = self.player['y'] + math.sin(ang) * barrel_len
        pygame.draw.line(self.screen, (245, 245, 245), (self.player['x'], self.player['y']), (bx, by), 4)

        # Build preview: show ghost of the structure at the mouse when in build mode
        if self.state == 'playing' and self.current_build:
            # Determine preview size based on type and rotation
            if self.current_build == 'wall':
                w, h = (52, 18) if self.build_rotation % 2 == 0 else (18, 52)
                base_color = (141, 85, 36)
            else:
                w, h = (34, 34)
                base_color = (193, 18, 31)
            px = mx - w / 2
            py = my - h / 2
            preview_rect = {'x': px, 'y': py, 'w': w, 'h': h}
            # Check validity: inside screen and not colliding with player solids
            valid = True
            if px < 0 or py < 0 or px + w > WIDTH or py + h > HEIGHT:
                valid = False
            else:
                for rect in self.get_player_solids():
                    if rects_overlap(preview_rect, rect):
                        valid = False
                        break
            # Surface for preview
            surf = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
            color = base_color if valid else (200, 60, 60)
            surf.fill((*color, 100))
            # Draw outline
            pygame.draw.rect(surf, (0, 0, 0, 180), pygame.Rect(0, 0, w, h), 1)
            self.screen.blit(surf, (px, py))
        # HUD: show resource and status information at bottom-left with generous spacing and center alignment
        p = self.player
        hud_lines: List[str] = []
        hud_lines.append(f"Vida: {int(p['hp'])}/{p['maxHp']}    Acamp: {int(self.camp['hp'])}/{self.camp['maxHp']}")
        hud_lines.append(f"Madeira: {p['wood']}    Pedra: {p['stone']}    Wave: {self.wave}    Kills: {self.kills}    Score: {self.score}")
        # Show skip hint only during preparation phase
        if self.in_preparation:
            hud_lines.append("Espaço/Enter: Pular preparação")
        hud_surfs = [self.font.render(line, True, (255, 255, 255)) for line in hud_lines]
        hud_width = max(surf.get_width() for surf in hud_surfs) + 20
        # total height includes each line's height and a spacing of 8 pixels between lines plus top/bottom padding
        # Increase vertical spacing between HUD lines for better readability
        hud_height = sum(surf.get_height() for surf in hud_surfs) + (len(hud_surfs) + 1) * 12
        hud_bg = pygame.Surface((hud_width, hud_height), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 120))
        hud_x = 10
        hud_y = HEIGHT - hud_height - 20
        self.screen.blit(hud_bg, (hud_x, hud_y))
        current_y = hud_y + 12
        for surf in hud_surfs:
            text_x = hud_x + (hud_width - surf.get_width()) / 2
            self.screen.blit(surf, (text_x, current_y))
            current_y += surf.get_height() + 12
        # Message display at top-left, below health bars.
        # Recalculate offset based on enlarged bars: two bars of bar_h height, plus gap and margin.
        bar_height_total = bar_h * 2 + 6
        y_offset = 16 + bar_height_total + 8
        if self.message:
            msg_surface = self.font.render(self.message, True, (255, 225, 200))
            self.screen.blit(msg_surface, (20, y_offset))
            y_offset += msg_surface.get_height() + 6
        # Always show build instructions to guide the player
        instr = "1:Parede  2:Armadilha  R:Girar  E:Interagir  C:Cancelar"
        instr_surf = self.font.render(instr, True, (200, 200, 200))
        # Position instructions just above the HUD box
        instr_y = hud_y - instr_surf.get_height() - 10
        if instr_y < 0:
            instr_y = 0
        self.screen.blit(instr_surf, (20, instr_y))
        # Pause overlay
        if self.state == 'paused':
            self.draw_pause()

    def draw_menu(self) -> None:
        """Draw the main menu with a start button and volume sliders."""
        # Draw a central panel for the menu to make it visually appealing
        panel_w, panel_h = 420, 360
        panel_x = (WIDTH - panel_w) / 2
        panel_y = (HEIGHT - panel_h) / 2
        # Panel background with slight transparency
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_surf.fill((0, 0, 0, 180))
        # Panel border
        pygame.draw.rect(panel_surf, (50, 70, 45), (0, 0, panel_w, panel_h), 3, border_radius=8)
        self.screen.blit(panel_surf, (panel_x, panel_y))
        # Title at top of panel
        title_surf = self.big_font.render("Última Noite no Acampamento", True, (255, 255, 255))
        self.screen.blit(title_surf, (panel_x + (panel_w - title_surf.get_width()) / 2, panel_y + 30))
        # Start button inside panel
        btn_w, btn_h = 240, 70
        btn_x = panel_x + (panel_w - btn_w) / 2
        btn_y = panel_y + 100
        self.menu_start_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        mouse_pos = pygame.mouse.get_pos()
        hover_start = self.menu_start_rect.collidepoint(mouse_pos)
        btn_color = (83, 120, 61) if hover_start else (66, 101, 51)
        pygame.draw.rect(self.screen, btn_color, self.menu_start_rect, border_radius=6)
        pygame.draw.rect(self.screen, (34, 51, 25), self.menu_start_rect, 2, border_radius=6)
        start_text = self.font.render("Iniciar Jogo", True, (255, 255, 255))
        self.screen.blit(start_text, (btn_x + (btn_w - start_text.get_width()) / 2, btn_y + (btn_h - start_text.get_height()) / 2))
        # Sliders for volumes inside panel
        slider_w = 260
        slider_h = 12
        music_y = panel_y + 200
        sfx_y = panel_y + 260
        # Music slider label
        music_label = self.font.render("Volume da música", True, (220, 220, 220))
        sfx_label = self.font.render("Volume dos efeitos", True, (220, 220, 220))
        self.screen.blit(music_label, (panel_x + (panel_w - slider_w) / 2, music_y - 24))
        self.screen.blit(sfx_label, (panel_x + (panel_w - slider_w) / 2, sfx_y - 24))
        # Slider rectangles
        music_bar_rect = pygame.Rect(panel_x + (panel_w - slider_w) / 2, music_y, slider_w, slider_h)
        sfx_bar_rect = pygame.Rect(panel_x + (panel_w - slider_w) / 2, sfx_y, slider_w, slider_h)
        pygame.draw.rect(self.screen, (80, 80, 80), music_bar_rect)
        pygame.draw.rect(self.screen, (80, 80, 80), sfx_bar_rect)
        # Filled portions
        pygame.draw.rect(self.screen, (161, 223, 136), (music_bar_rect.x, music_bar_rect.y, slider_w * self.music_volume, slider_h))
        pygame.draw.rect(self.screen, (161, 223, 136), (sfx_bar_rect.x, sfx_bar_rect.y, slider_w * self.sfx_volume, slider_h))
        # Knobs
        knob_radius = 8
        music_knob_x = music_bar_rect.x + slider_w * self.music_volume
        sfx_knob_x = sfx_bar_rect.x + slider_w * self.sfx_volume
        pygame.draw.circle(self.screen, (214, 252, 184), (int(music_knob_x), int(music_y + slider_h / 2)), knob_radius)
        pygame.draw.circle(self.screen, (214, 252, 184), (int(sfx_knob_x), int(sfx_y + slider_h / 2)), knob_radius)
        # Fullscreen toggle button inside panel
        fs_w, fs_h = 140, 40
        fs_x = panel_x + (panel_w - fs_w) / 2
        fs_y = panel_y + panel_h - 70
        self.menu_fullscreen_rect = pygame.Rect(fs_x, fs_y, fs_w, fs_h)
        hover_fs = self.menu_fullscreen_rect.collidepoint(mouse_pos)
        fs_color = (92, 130, 200) if hover_fs else (75, 109, 168)
        pygame.draw.rect(self.screen, fs_color, self.menu_fullscreen_rect, border_radius=6)
        pygame.draw.rect(self.screen, (40, 60, 100), self.menu_fullscreen_rect, 2, border_radius=6)
        fs_text = "Tela Cheia: On" if self.fullscreen else "Tela Cheia: Off"
        fs_text_surf = self.font.render(fs_text, True, (255, 255, 255))
        self.screen.blit(fs_text_surf, (fs_x + (fs_w - fs_text_surf.get_width()) / 2, fs_y + (fs_h - fs_text_surf.get_height()) / 2))
        # Store slider rects for interaction
        self.music_slider_rect = music_bar_rect
        self.sfx_slider_rect = sfx_bar_rect

    def draw_pause(self) -> None:
        # Dark overlay
        overlay = pygame.Surface((WIDTH, HEIGHT), flags=pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        # Panel for pause menu
        # Increase panel height to accommodate volume sliders
        panel_w, panel_h = 420, 460
        panel_x = (WIDTH - panel_w) / 2
        panel_y = (HEIGHT - panel_h) / 2
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_surf.fill((0, 0, 0, 200))
        pygame.draw.rect(panel_surf, (50, 70, 45), (0, 0, panel_w, panel_h), 3, border_radius=8)
        self.screen.blit(panel_surf, (panel_x, panel_y))
        # Title
        title_surf = self.big_font.render("Jogo Pausado", True, (255, 255, 255))
        self.screen.blit(title_surf, (panel_x + (panel_w - title_surf.get_width()) / 2, panel_y + 30))
        # Resume button
        btn_w, btn_h = 200, 60
        btn_x = panel_x + (panel_w - btn_w) / 2
        btn_y = panel_y + 100
        self.pause_resume_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        mouse_pos = pygame.mouse.get_pos()
        hover_resume = self.pause_resume_rect.collidepoint(mouse_pos)
        btn_color = (83, 120, 61) if hover_resume else (66, 101, 51)
        pygame.draw.rect(self.screen, btn_color, self.pause_resume_rect, border_radius=6)
        pygame.draw.rect(self.screen, (34, 51, 25), self.pause_resume_rect, 2, border_radius=6)
        resume_text = self.font.render("Continuar", True, (255, 255, 255))
        self.screen.blit(resume_text, (btn_x + (btn_w - resume_text.get_width()) / 2, btn_y + (btn_h - resume_text.get_height()) / 2))
        # Restart button
        restart_y = btn_y + btn_h + 20
        self.pause_restart_rect = pygame.Rect(btn_x, restart_y, btn_w, btn_h)
        hover_restart = self.pause_restart_rect.collidepoint(mouse_pos)
        btn_color_r = (161, 74, 66) if hover_restart else (140, 58, 50)
        pygame.draw.rect(self.screen, btn_color_r, self.pause_restart_rect, border_radius=6)
        pygame.draw.rect(self.screen, (77, 30, 27), self.pause_restart_rect, 2, border_radius=6)
        restart_text = self.font.render("Reiniciar", True, (255, 255, 255))
        self.screen.blit(restart_text, (btn_x + (btn_w - restart_text.get_width()) / 2, restart_y + (btn_h - restart_text.get_height()) / 2))
        # Volume sliders labels and bars inside the pause panel
        slider_w = 260
        slider_h = 12
        music_y = restart_y + btn_h + 30
        sfx_y = music_y + 60
        music_label = self.font.render("Volume música", True, (220, 220, 220))
        sfx_label = self.font.render("Volume efeitos", True, (220, 220, 220))
        self.screen.blit(music_label, (panel_x + (panel_w - slider_w) / 2, music_y - 24))
        self.screen.blit(sfx_label, (panel_x + (panel_w - slider_w) / 2, sfx_y - 24))
        music_bar_rect = pygame.Rect(panel_x + (panel_w - slider_w) / 2, music_y, slider_w, slider_h)
        sfx_bar_rect = pygame.Rect(panel_x + (panel_w - slider_w) / 2, sfx_y, slider_w, slider_h)
        pygame.draw.rect(self.screen, (80, 80, 80), music_bar_rect)
        pygame.draw.rect(self.screen, (80, 80, 80), sfx_bar_rect)
        # Fill according to current volumes
        pygame.draw.rect(self.screen, (161, 223, 136), (music_bar_rect.x, music_bar_rect.y, slider_w * self.music_volume, slider_h))
        pygame.draw.rect(self.screen, (161, 223, 136), (sfx_bar_rect.x, sfx_bar_rect.y, slider_w * self.sfx_volume, slider_h))
        # Slider knobs
        knob_radius = 8
        music_knob_x = music_bar_rect.x + slider_w * self.music_volume
        sfx_knob_x = sfx_bar_rect.x + slider_w * self.sfx_volume
        pygame.draw.circle(self.screen, (214, 252, 184), (int(music_knob_x), int(music_y + slider_h / 2)), knob_radius)
        pygame.draw.circle(self.screen, (214, 252, 184), (int(sfx_knob_x), int(sfx_y + slider_h / 2)), knob_radius)
        # Store slider rects for interaction during pause
        self.pause_music_slider_rect = music_bar_rect
        self.pause_sfx_slider_rect = sfx_bar_rect
        # Fullscreen toggle button
        fs_y = sfx_y + 60
        fs_h = 50
        self.pause_fullscreen_rect = pygame.Rect(btn_x, fs_y, btn_w, fs_h)
        hover_fs = self.pause_fullscreen_rect.collidepoint(mouse_pos)
        fs_color = (92, 130, 200) if hover_fs else (75, 109, 168)
        pygame.draw.rect(self.screen, fs_color, self.pause_fullscreen_rect, border_radius=6)
        pygame.draw.rect(self.screen, (40, 60, 100), self.pause_fullscreen_rect, 2, border_radius=6)
        fs_text = "Tela Cheia: On" if self.fullscreen else "Tela Cheia: Off"
        fs_text_surf = self.font.render(fs_text, True, (255, 255, 255))
        self.screen.blit(fs_text_surf, (btn_x + (btn_w - fs_text_surf.get_width()) / 2, fs_y + (fs_h - fs_text_surf.get_height()) / 2))

    def draw_end(self) -> None:
        title = 'Vitória' if self.state == 'victory' else 'Game Over'
        title_surf = self.big_font.render(title, True, (255, 255, 255))
        msg_surf = self.font.render(self.message, True, (255, 225, 200))
        hint_surf = self.font.render("Pressione Enter para voltar ao menu", True, (200, 200, 200))
        self.screen.blit(title_surf, (WIDTH / 2 - title_surf.get_width() / 2, HEIGHT / 2 - 60))
        self.screen.blit(msg_surf, (WIDTH / 2 - msg_surf.get_width() / 2, HEIGHT / 2))
        self.screen.blit(hint_surf, (WIDTH / 2 - hint_surf.get_width() / 2, HEIGHT / 2 + 40))

    # ------------------------------------------------------------------
    # Main event loop
    def run(self) -> None:
        running = True
        while running:
            dt_ms = self.clock.tick(FPS)
            dt = dt_ms / 1000.0
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                # Mouse interactions (menu and gameplay)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # If in menu, handle clicks for start button and sliders
                    if self.state == 'menu' and event.button == 1:
                        mx, my = event.pos
                        # Start button
                        if hasattr(self, 'menu_start_rect') and self.menu_start_rect.collidepoint((mx, my)):
                            self.start_run()
                            continue
                        # Music slider
                        if hasattr(self, 'music_slider_rect') and self.music_slider_rect.collidepoint((mx, my)):
                            rel_x = mx - self.music_slider_rect.x
                            self.music_volume = max(0.0, min(1.0, rel_x / self.music_slider_rect.width))
                            if self.music_volume > 0:
                                self.sound_player.start_music()
                            else:
                                self.sound_player.stop_music()
                            continue
                        # SFX slider
                        if hasattr(self, 'sfx_slider_rect') and self.sfx_slider_rect.collidepoint((mx, my)):
                            rel_x = mx - self.sfx_slider_rect.x
                            self.sfx_volume = max(0.0, min(1.0, rel_x / self.sfx_slider_rect.width))
                            continue
                        # Fullscreen toggle button
                        if hasattr(self, 'menu_fullscreen_rect') and self.menu_fullscreen_rect.collidepoint((mx, my)):
                            self.toggle_fullscreen()
                            continue
                    # In gameplay state, handle building on right click
                    elif self.state == 'playing':
                        if event.button == 1:
                            # left click handled by continuous player_shoot()
                            pass
                        elif event.button == 3:
                            self.handle_build_click()
                    # In paused state, handle clicks on pause menu buttons
                    elif self.state == 'paused' and event.button == 1:
                        mx, my = event.pos
                        # Resume game
                        if hasattr(self, 'pause_resume_rect') and self.pause_resume_rect and self.pause_resume_rect.collidepoint((mx, my)):
                            self.state = 'playing'
                            continue
                        # Restart run
                        if hasattr(self, 'pause_restart_rect') and self.pause_restart_rect and self.pause_restart_rect.collidepoint((mx, my)):
                            self.start_run()
                            continue
                        # Pause volume sliders
                        if hasattr(self, 'pause_music_slider_rect') and self.pause_music_slider_rect and self.pause_music_slider_rect.collidepoint((mx, my)):
                            rel_x = mx - self.pause_music_slider_rect.x
                            self.music_volume = max(0.0, min(1.0, rel_x / self.pause_music_slider_rect.width))
                            if self.music_volume > 0:
                                self.sound_player.start_music()
                            else:
                                self.sound_player.stop_music()
                            continue
                        if hasattr(self, 'pause_sfx_slider_rect') and self.pause_sfx_slider_rect and self.pause_sfx_slider_rect.collidepoint((mx, my)):
                            rel_x = mx - self.pause_sfx_slider_rect.x
                            self.sfx_volume = max(0.0, min(1.0, rel_x / self.pause_sfx_slider_rect.width))
                            continue
                        # Toggle fullscreen
                        if hasattr(self, 'pause_fullscreen_rect') and self.pause_fullscreen_rect and self.pause_fullscreen_rect.collidepoint((mx, my)):
                            self.toggle_fullscreen()
                            continue
                elif event.type == pygame.KEYDOWN:
                    if self.state == 'menu':
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self.start_run()
                    elif self.state == 'playing':
                        # In‐game keybindings
                        if event.key == pygame.K_ESCAPE:
                            # Pause the game
                            self.state = 'paused'
                        # Select build type 1 = wall, 2 = trap
                        elif event.key == pygame.K_1:
                            # Enter wall build mode
                            self.current_build = 'wall'
                            self.message = 'Construir Parede: clique direito para colocar'
                        elif event.key == pygame.K_2:
                            # Enter trap build mode
                            self.current_build = 'trap'
                            self.message = 'Construir Armadilha: clique direito para colocar'
                        # Rotate build preview
                        elif event.key == pygame.K_r:
                            self.build_rotation = (self.build_rotation + 1) % 2
                        # Cancel build: press C to exit build mode and clear preview
                        elif event.key == pygame.K_c:
                            if self.current_build is not None:
                                self.current_build = None
                                self.message = ''
                        # Interact key (open ruin, chest or upgrade/repair)
                        elif event.key == pygame.K_e:
                            self.interact()
                    elif self.state == 'paused':
                        if event.key == pygame.K_ESCAPE:
                            self.state = 'playing'
                        elif event.key == pygame.K_RETURN:
                            # Restart run
                            self.start_run()
                        elif event.key == pygame.K_f:
                            self.toggle_fullscreen()
                    elif self.state in ('gameover', 'victory'):
                        if event.key == pygame.K_RETURN:
                            self.state = 'menu'
                            self.reset_game()
                # (mouse building handling now integrated above)
            # Update logic if not paused or menu
            if self.state == 'playing':
                self.update(dt)
            # Draw all
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode((WIDTH, HEIGHT))

    def handle_build_click(self) -> None:
        # Right click build/trap placement
        if self.current_build is None:
            return
        # Determine size based on current build and rotation
        if self.current_build == 'wall':
            w, h = (52, 18) if self.build_rotation % 2 == 0 else (18, 52)
        else:
            w, h = (34, 34)
        mx, my = pygame.mouse.get_pos()
        x = mx - w / 2
        y = my - h / 2
        new_rect = {'x': x, 'y': y, 'w': w, 'h': h}
        # Check collision with solids and screen bounds
        if (x < 0 or y < 0 or x + w > WIDTH or y + h > HEIGHT):
            return
        for rect in self.get_player_solids():
            if rects_overlap(new_rect, rect):
                return
        # Resource costs
        if self.current_build == 'wall':
            cost_wood = 5
            if self.player['wood'] < cost_wood:
                return
            self.player['wood'] -= cost_wood
            self.structures.append({
                'type': 'wall', 'x': x, 'y': y, 'w': w, 'h': h,
                'level': 1, 'hp': 100, 'maxHp': 100, 'broken': False
            })
        else:
            cost_wood = 4
            if self.player['wood'] < cost_wood:
                return
            self.player['wood'] -= cost_wood
            self.structures.append({
                'type': 'trap', 'x': x, 'y': y, 'w': w, 'h': h,
                'level': 1, 'hp': 40, 'maxHp': 40, 'broken': False, 'tick': 0
            })
        # Play build sound if sfx volume > 0
        if getattr(self, 'sfx_volume', 1.0) > 0:
            self.sound_player.play_build()
        # Leave build mode active to allow sequential placement.  Message cleared.
        self.message = ''

    # Placeholder for spawn ruins and chest interactions


if __name__ == '__main__':
    game = Game()
    game.run()