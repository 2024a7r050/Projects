import os
import sys
import time
import math
import random
import threading
import keyboard
from PIL import Image, ImageTk
import customtkinter as ctk

# Ensure stdout and stderr handle UTF-8 cleanly on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import actions
import sounds
from brain import Brain
from voice import Voice
from ears import Ears
from config import config
from logger import logger, audit_logger

# Window Sizing Constants
MINI_WIDTH = 220
MINI_HEIGHT = 220
FULL_WIDTH = 380
FULL_HEIGHT = 650
PADDING_RIGHT = 30
PADDING_BOTTOM = 40

# Asset Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MINI_IMG_PATH = os.path.join(ASSETS_DIR, "groot_mini.png")
FULL_IMG_PATH = os.path.join(ASSETS_DIR, "groot_full.png")

# Baby Groot Theme Colors
GROOT_THEME = {
    "name": "Baby Groot AI Companion",
    "primary": "#4ade80",       # Vibrant Sprout Green
    "secondary": "#22c55e",     # Forest Green
    "dark": "#14532d",          # Deep Forest Bark
    "accent": "#facc15",        # Cosmic Sunlight Gold
    "bark_brown": "#854d0e",    # Warm Wood Bark
    "bg_glass": "#08120b",      # Deep Cosmic Green Glass HUD
    "text_col": "#dcfce7",      # Soft Mint / Sprout Cream Text
    "border_green": "#22c55e",  # Vibrant Green Border
    "growth_green": "#38ef7d",  # Growth Bar Color
    "energy_gold": "#eab308",   # Sunlight Energy Bar Color
}


class GrootWebWindow:
    """Manages the 3D animated Baby Groot window.

    Launches groot_viewer.py as a SUBPROCESS (pywebview requires the main thread;
    this avoids the 'pywebview must be run on a main thread' crash).
    Commands are sent to the viewer via its stdin pipe.

    Supported moods: idle, happy, dance, water, hug, sprout, guard, sleepy
    """

    MOOD_MAP = {
        "happy":     "happy",
        "dancing":   "dance",
        "sprouting": "sprout",
        "playful":   "happy",
        "sleepy":    "sleepy",
        "battle":    "guard",
        "idle":      "idle",
    }
    GESTURE_MAP = {
        "dance":  "dance",
        "water":  "water",
        "hug":    "hug",
        "sprout": "sprout",
        "guard":  "guard",
    }

    def __init__(self):
        self._proc = None
        self._viewer_path = os.path.join(BASE_DIR, "groot_viewer.py")
        self._python_exe = sys.executable

    def start(self):
        """Launch groot_viewer.py as a subprocess (main-thread safe)."""
        if not os.path.exists(self._viewer_path):
            logger.warning("groot_viewer.py not found — 3D Groot window disabled.")
            return
        if not os.path.exists(os.path.join(BASE_DIR, "groot_3d.html")):
            logger.warning("groot_3d.html not found — 3D Groot window disabled.")
            return
        try:
            import subprocess
            self._proc = subprocess.Popen(
                [self._python_exe, self._viewer_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,       # line-buffered
                cwd=BASE_DIR,
            )
            logger.info("3D Groot viewer subprocess launched.")
        except Exception as e:
            logger.error(f"Failed to launch 3D Groot viewer: {e}")
            self._proc = None

    def set_mood(self, groot_mood: str):
        """Send a mood command to the 3D viewer."""
        js_mood = self.MOOD_MAP.get(groot_mood.lower(), "idle")
        self._send(f"mood:{js_mood}")

    def set_gesture(self, gesture: str):
        """Trigger a gesture in the 3D viewer."""
        js_mood = self.GESTURE_MAP.get(gesture.lower(), "idle")
        self._send(f"mood:{js_mood}")

    def say(self, text: str):
        """Show a speech bubble in the 3D viewer."""
        if not text:
            return
        safe = text[:120].replace("\n", " ").replace("\r", "")
        self._send(f"speech:{safe}")

    def close(self):
        """Gracefully shut down the viewer subprocess."""
        self._send("quit")
        if self._proc:
            try:
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()

    def _send(self, cmd: str):
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
            except Exception:
                pass  # Viewer may have been closed



class BuddyApp(ctk.CTk):
    """Dedicated Baby Groot AI Companion and Desktop Assistant Application."""


    def __init__(self):
        super().__init__()

        # Enterprise Subsystems
        logger.info("Booting BUDDY Baby Groot Companion Subsystems...")
        try:
            audit_logger.record_event(
                event_type="BOOT_INIT",
                action="BuddyApp.__init__",
                parameters={"environment": config.env, "model": config.primary_model}
            )
        except Exception as e:
            logger.error(f"Boot telemetry error: {e}")

        self.brain = Brain()
        self.voice = Voice()
        self.ears = Ears()

        # 3D Animated Baby Groot Window (pywebview — real browser WebGL canvas)
        self.groot_3d = GrootWebWindow()
        self.groot_3d.start()

        # Baby Groot Companion State & Vitality Metrics
        self.groot_mood = "happy"       # happy, dancing, sprouting, playful, sleepy, battle
        self.groot_gesture = "idle"     # idle, dance, water, hug, sprout, guard
        self.growth = 100               # 0 to 100%
        self.sunlight = 100             # 0 to 100%
        self.water_count = 0
        self.dance_count = 0
        self.hug_count = 0

        # Animation States
        self.hud_elements = []
        self._load_avatar_images()

        # App State
        self.is_expanded = False
        self.ai_state = "monitoring"  # monitoring, listening, thinking, speaking
        self.is_processing = False

        # Register Callbacks with actions module
        actions.set_voice_ref(self.voice)
        actions.set_groot_mood_callback(self._set_groot_mood_safe)
        actions.set_groot_gesture_callback(self._set_groot_gesture_safe)
        actions.set_dog_mood_callback(self._set_groot_mood_safe)
        actions.set_dog_gesture_callback(self._set_groot_gesture_safe)

        # Window Setup
        self.title("Buddy AI - Baby Groot Companion (I am Groot!)")
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        self.screen_w = self.winfo_screenwidth()
        self.screen_h = self.winfo_screenheight()

        # Position in bottom-right corner
        x = self.screen_w - MINI_WIDTH - PADDING_RIGHT
        y = self.screen_h - MINI_HEIGHT - PADDING_BOTTOM
        self.geometry(f"{MINI_WIDTH}x{MINI_HEIGHT}+{x}+{y}")

        self.configure(fg_color="#010101")
        self.attributes("-alpha", 0.96)
        self.attributes("-transparentcolor", "#010101")

        # ---- CANVAS ----
        self.canvas = ctk.CTkCanvas(self, width=MINI_WIDTH, height=MINI_HEIGHT, bg="#010101", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # ---- EXPANDED DASHBOARD PANEL ----
        self.transcript_frame = ctk.CTkFrame(
            self,
            fg_color=GROOT_THEME["bg_glass"],
            corner_radius=12,
            border_width=1,
            border_color=GROOT_THEME["border_green"]
        )

        # Header Title
        self.transcript_header = ctk.CTkLabel(
            self.transcript_frame,
            text="🌱 I AM GROOT // BABY GROOT COMPANION",
            font=("Consolas", 12, "bold"),
            text_color=GROOT_THEME["primary"]
        )
        self.transcript_header.pack(fill="x", padx=10, pady=(6, 4))

        # Care Metrics Progress Bars (Growth & Sunlight)
        self.care_bar_frame = ctk.CTkFrame(self.transcript_frame, fg_color="#041007", corner_radius=8, border_width=1, border_color="#14532d")
        self.care_bar_frame.pack(fill="x", padx=8, pady=(0, 6))

        # Growth Vitality Row
        self.growth_row = ctk.CTkFrame(self.care_bar_frame, fg_color="transparent")
        self.growth_row.pack(fill="x", padx=8, pady=(4, 2))
        self.lbl_growth = ctk.CTkLabel(self.growth_row, text=f"Growth ({self.growth}%)", font=("Consolas", 9, "bold"), text_color="#4ade80", width=85, anchor="w")
        self.lbl_growth.pack(side="left")
        self.bar_growth = ctk.CTkProgressBar(self.growth_row, height=8, corner_radius=4, progress_color="#38ef7d", fg_color="#0c2a15")
        self.bar_growth.set(self.growth / 100.0)
        self.bar_growth.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Sunlight / Photosynthesis Energy Row
        self.sunlight_row = ctk.CTkFrame(self.care_bar_frame, fg_color="transparent")
        self.sunlight_row.pack(fill="x", padx=8, pady=(2, 4))
        self.lbl_sunlight = ctk.CTkLabel(self.sunlight_row, text=f"Sunlight ({self.sunlight}%)", font=("Consolas", 9, "bold"), text_color="#facc15", width=85, anchor="w")
        self.lbl_sunlight.pack(side="left")
        self.bar_sunlight = ctk.CTkProgressBar(self.sunlight_row, height=8, corner_radius=4, progress_color="#facc15", fg_color="#362905")
        self.bar_sunlight.set(self.sunlight / 100.0)
        self.bar_sunlight.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Stats Counter Row
        self.lbl_stats = ctk.CTkLabel(
            self.care_bar_frame,
            text=f"Waterings: {self.water_count}  |  Dances: {self.dance_count}  |  Twig Hugs: {self.hug_count}",
            font=("Consolas", 8),
            text_color="#dcfce7"
        )
        self.lbl_stats.pack(pady=(0, 4))

        # Interactive Command Deck (6 Touch Buttons with Generous Sizing)
        self.deck_frame = ctk.CTkFrame(self.transcript_frame, fg_color="transparent")
        self.deck_frame.pack(fill="x", padx=8, pady=(0, 6))
        for col_i in range(6):
            self.deck_frame.grid_columnconfigure(col_i, weight=1)

        self.btn_talk = ctk.CTkButton(
            self.deck_frame, text="Talk", font=("Consolas", 9, "bold"),
            fg_color="#15803d", hover_color="#16a34a", text_color="#ffffff",
            border_width=1, border_color="#4ade80", height=24, corner_radius=6,
            command=self._toggle_talk
        )
        self.btn_talk.grid(row=0, column=0, padx=2, sticky="ew")

        self.btn_dance = ctk.CTkButton(
            self.deck_frame, text="Dance", font=("Consolas", 9, "bold"),
            fg_color="#14532d", hover_color="#166534", text_color="#dcfce7",
            border_width=1, border_color="#22c55e", height=24, corner_radius=6,
            command=lambda: actions.dance_groot()
        )
        self.btn_dance.grid(row=0, column=1, padx=2, sticky="ew")

        self.btn_water = ctk.CTkButton(
            self.deck_frame, text="Water", font=("Consolas", 9, "bold"),
            fg_color="#14532d", hover_color="#166534", text_color="#dcfce7",
            border_width=1, border_color="#22c55e", height=24, corner_radius=6,
            command=lambda: actions.water_groot()
        )
        self.btn_water.grid(row=0, column=2, padx=2, sticky="ew")

        self.btn_hug = ctk.CTkButton(
            self.deck_frame, text="Hug", font=("Consolas", 9, "bold"),
            fg_color="#14532d", hover_color="#166534", text_color="#dcfce7",
            border_width=1, border_color="#22c55e", height=24, corner_radius=6,
            command=lambda: actions.hug_groot()
        )
        self.btn_hug.grid(row=0, column=3, padx=2, sticky="ew")

        self.btn_sprout = ctk.CTkButton(
            self.deck_frame, text="Sprout", font=("Consolas", 9, "bold"),
            fg_color="#14532d", hover_color="#166534", text_color="#dcfce7",
            border_width=1, border_color="#22c55e", height=24, corner_radius=6,
            command=lambda: actions.sprout_groot()
        )
        self.btn_sprout.grid(row=0, column=4, padx=2, sticky="ew")

        self.btn_guard = ctk.CTkButton(
            self.deck_frame, text="Guard", font=("Consolas", 9, "bold"),
            fg_color="#14532d", hover_color="#166534", text_color="#dcfce7",
            border_width=1, border_color="#22c55e", height=24, corner_radius=6,
            command=lambda: actions.guard_groot()
        )
        self.btn_guard.grid(row=0, column=5, padx=2, sticky="ew")

        # Status & Mood HUD Card
        self.status_card = ctk.CTkFrame(
            self.transcript_frame,
            fg_color="#051208",
            border_width=1,
            border_color="#22c55e",
            corner_radius=6
        )
        self.status_card.pack(fill="x", padx=8, pady=(0, 6))

        self.status_card_title = ctk.CTkLabel(
            self.status_card,
            text="BABY GROOT STATUS // MOOD: HAPPY",
            font=("Consolas", 9, "bold"),
            text_color="#4ade80",
            anchor="w"
        )
        self.status_card_title.pack(fill="x", padx=8, pady=(3, 1))

        self.status_card_info = ctk.CTkLabel(
            self.status_card,
            text="[ SPECIES ]: Flora Colossus (Planet X)  |  [ VOCAL ]: \"I am Groot!\"\n[ SHORTCUTS ]: Dance (D), Water (W), Twig Hug (H), Sprout (Space), Guard (G)\n[ MOOD KEYS ]: 1:Happy, 2:Dancing, 3:Sprouting, 4:Playful, 5:Sleepy, 6:Battle",
            font=("Consolas", 8),
            text_color="#dcfce7",
            justify="left",
            anchor="w"
        )
        self.status_card_info.pack(fill="x", padx=8, pady=(0, 4))

        # Transcript Box
        self.transcript = ctk.CTkTextbox(
            self.transcript_frame,
            width=350,
            height=130,
            fg_color="#030a05",
            text_color=GROOT_THEME["text_col"],
            font=("Consolas", 11),
            corner_radius=6,
            border_width=1,
            border_color=GROOT_THEME["dark"]
        )
        self.transcript.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.transcript.insert("0.0", "[ Baby Groot AI Companion ] \"I am Groot!\" (Online & Ready)\n")
        self.transcript.insert("end", "[ Actions ] Left-Click: Twig Hug  |  Right-Click: Water Groot  |  Space: Dance\n")
        self.transcript.insert("end", "[ Hotkeys ] Key 'D': Dance  |  'W': Water  |  'H': Twig Hug  |  'G': Guard Mode\n")
        self.transcript.insert("end", "[ Voice ] Say 'Hey Buddy' or 'Hey Groot', ask any question, or command your PC!\n")
        self.transcript.configure(state="disabled")

        # Direct Command Input Bar
        self.cmd_input_frame = ctk.CTkFrame(self.transcript_frame, fg_color="transparent")
        self.cmd_input_frame.pack(fill="x", padx=8, pady=(0, 6))

        self.cmd_entry = ctk.CTkEntry(
            self.cmd_input_frame,
            placeholder_text="Speak or type ('dance', 'water groot', 'sprout', 'boost ram', 'play music')...",
            font=("Consolas", 10),
            fg_color="#07190d",
            border_color="#22c55e",
            text_color="#dcfce7",
            placeholder_text_color="#52796f",
            height=28,
            corner_radius=6
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.cmd_entry.bind("<Return>", lambda e: self._submit_typed_command())

        self.cmd_send_btn = ctk.CTkButton(
            self.cmd_input_frame,
            text="EXECUTE",
            width=68,
            height=28,
            font=("Consolas", 9, "bold"),
            fg_color="#15803d",
            hover_color="#16a34a",
            text_color="#ffffff",
            border_width=1,
            border_color="#4ade80",
            corner_radius=6,
            command=self._submit_typed_command
        )
        self.cmd_send_btn.pack(side="right")

        # Initial Draw
        self._draw_mini()

        # Mouse Event Bindings
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._has_dragged = False
        self._single_click_timer = None

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
        self.canvas.bind("<Button-2>", self._on_middle_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Triple-Button-1>", self._on_triple_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        # Global Keyboard Hotkeys
        self.bind_all("<Key>", self._on_key_press)
        keyboard.add_hotkey('ctrl+shift+b', self.hotkey_pressed)

        # Console Banner
        print(f"\033[92m{'=' * 68}")
        print("  BUDDY v5.0 — Baby Groot AI Desktop Companion (Flora Colossus)")
        print(f"{'=' * 68}")
        print("  Baby Groot AI Features Active:")
        print("    - [Dynamic Moods 1-6] Happy, Dancing, Sprouting, Playful, Sleepy, Battle")
        print("    - [Left-Click / 'H'] Cozy Twig Hug ('I am Groot!' with warm chirp)")
        print("    - [Right-Click / 'W'] Water Baby Groot (Blooming fresh sprouts & flowers)")
        print("    - [Middle-Click / 'D'] Dance & Groove (Upbeat disco funk & twig swaying)")
        print("    - [Spacebar / Triple-Click] Sprout Superpower (Flushes PC RAM & accelerates)")
        print("    - [Key 'G'] Guardian Mode (Heavy ironwood shield & locks Windows)")
        print("    - [Voice Commands] 'Dance groot', 'Water plant', 'Hug baby groot', 'Sprout'")
        print("    - [AI Intelligence] Q&A, Coding, PC Automation, RAM Boost, Media")
        print(f"{'=' * 68}\033[0m")

        # Start wake word listener
        self.wake_word_thread = threading.Thread(target=self._wake_word_loop, daemon=True)
        self.wake_word_thread.start()

        # Start animation loop
        self.animate()

    # ============================================================
    # AVATAR IMAGE LOADING & RENDERING
    # ============================================================
    def _load_avatar_images(self):
        """Loads and prepares the high-resolution photo avatars with smooth rounded masking."""
        self.photo_mini = None
        self.photo_full = None

        if os.path.exists(MINI_IMG_PATH):
            try:
                img_m = Image.open(MINI_IMG_PATH)
                self.photo_mini = ImageTk.PhotoImage(img_m)
            except Exception as e:
                logger.error(f"Error loading mini image: {e}")

        if os.path.exists(FULL_IMG_PATH):
            try:
                img_f = Image.open(FULL_IMG_PATH)
                self.photo_full = ImageTk.PhotoImage(img_f)
            except Exception as e:
                logger.error(f"Error loading full image: {e}")

    def _draw_mini(self):
        """Draws the Baby Groot photo avatar in mini desktop companion mode."""
        self.canvas.delete("all")
        self.hud_elements = []
        cx = MINI_WIDTH // 2
        cy = MINI_HEIGHT // 2 - 10

        if self.photo_mini:
            # Soft ambient drop shadow
            self.canvas.create_oval(cx - 92, cy - 92, cx + 92, cy + 92, fill="#040c06", outline="#0a2612", width=2)
            # Glowing bioluminescent green outer ring
            self.canvas.create_oval(cx - 90, cy - 90, cx + 90, cy + 90, fill="", outline=GROOT_THEME["border_green"], width=2)
            # Baby Groot Mini Avatar
            self.canvas.create_image(cx, cy, image=self.photo_mini)
        else:
            # Fallback circle if image missing
            self.canvas.create_oval(cx - 80, cy - 80, cx + 80, cy + 80, fill="#15803d", outline="#4ade80", width=2)

        # Status text below avatar
        label = "I AM GROOT!"
        self.status_text = self.canvas.create_text(
            cx, MINI_HEIGHT - 12,
            text=label,
            fill=GROOT_THEME["primary"],
            font=("Consolas", 10, "bold")
        )

    def _draw_full(self):
        """Draws the full Baby Groot standing avatar in expanded dashboard mode."""
        self.canvas.delete("all")
        self.hud_elements = []
        cx = FULL_WIDTH // 2
        cy = 145

        if self.photo_full:
            # Card frame background
            self.canvas.create_rectangle(cx - 132, cy - 132, cx + 132, cy + 132, fill="#051208", outline=GROOT_THEME["border_green"], width=2)
            # Full Body Baby Groot standing on glowing stage
            self.canvas.create_image(cx, cy, image=self.photo_full)
        else:
            self.canvas.create_rectangle(cx - 120, cy - 120, cx + 120, cy + 120, fill="#15803d", outline="#4ade80", width=2)

        label = f"BABY GROOT: {self.groot_mood.upper()} [I am Groot!]"
        self.status_text = self.canvas.create_text(
            cx, 280,
            text=label,
            fill=GROOT_THEME["primary"],
            font=("Consolas", 12, "bold")
        )

    # ============================================================
    # REAL-TIME ANIMATION LOOP
    # ============================================================
    def animate(self):
        t_now = time.time()
        cx = FULL_WIDTH // 2 if self.is_expanded else MINI_WIDTH // 2
        cy = 145 if self.is_expanded else (MINI_HEIGHT // 2 - 10)

        # Clear floating dynamic overlays
        for hid in self.hud_elements:
            try:
                self.canvas.delete(hid)
            except Exception:
                pass
        self.hud_elements = []

        # Floating Animated Mood Emotes & Bioluminescent Flora Spores
        try:
            if self.groot_mood == "dancing":
                note_dy = int(math.sin(t_now * 8) * 5)
                note_dx = int(math.cos(t_now * 6) * 4)
                note1 = self.canvas.create_text(
                    cx + 55 + note_dx, cy - 45 + note_dy,
                    text="♪", fill="#facc15", font=("Consolas", 14, "bold")
                )
                note2 = self.canvas.create_text(
                    cx - 55 - note_dx, cy - 50 - note_dy,
                    text="♫", fill="#4ade80", font=("Consolas", 12, "bold")
                )
                self.hud_elements.extend([note1, note2])

            elif self.groot_mood == "sprouting":
                sprout_dy = (int(t_now * 20) % 20)
                sprout = self.canvas.create_text(
                    cx + 55, cy - 40 - sprout_dy,
                    text="🌱", fill="#4ade80", font=("Consolas", 13, "bold")
                )
                self.hud_elements.append(sprout)

            elif self.groot_mood == "sleepy":
                z_offset = (int(t_now * 14) % 24)
                z_txt = self.canvas.create_text(
                    cx + 45 + (z_offset * 0.3), cy - 45 - z_offset,
                    text="Zzz", fill="#86efac",
                    font=("Consolas", 11 + int(z_offset * 0.1), "bold")
                )
                self.hud_elements.append(z_txt)

            elif self.groot_mood == "battle":
                badge_dy = int(math.sin(t_now * 6) * 2)
                guard_badge = self.canvas.create_text(
                    cx + 55, cy - 45 + badge_dy,
                    text="🛡️", fill="#fbbf24", font=("Consolas", 11, "bold")
                )
                self.hud_elements.append(guard_badge)

            elif self.groot_mood in ["happy", "playful"]:
                sparkle_dy = int(math.sin(t_now * 4) * 3)
                sparkle = self.canvas.create_text(
                    cx + 55, cy - 45 + sparkle_dy,
                    text="✨", fill="#fef08a", font=("Consolas", 13, "bold")
                )
                self.hud_elements.append(sparkle)

        except Exception:
            pass

        # Update status text
        if hasattr(self, "status_text") and self.status_text:
            status_lbl = "I AM GROOT!" if not self.is_expanded else f"BABY GROOT: {self.groot_mood.upper()} [I am Groot!]"
            self.canvas.itemconfig(self.status_text, text=status_lbl, fill=GROOT_THEME["primary"])

        self.after(33, self.animate)

    # ============================================================
    # GROOT MOOD & GESTURE STATE HANDLERS
    # ============================================================
    def _set_groot_mood_safe(self, mood):
        self.after(0, lambda: self._apply_groot_mood(mood))

    def _apply_groot_mood(self, mood):
        self.groot_mood = mood.lower()
        if self.groot_mood == "happy":
            self.growth = min(100, self.growth + 5)
        elif self.groot_mood in ["dancing", "playful"]:
            self.growth = min(100, self.growth + 10)
            self.sunlight = max(10, self.sunlight - 5)
        elif self.groot_mood == "sprouting":
            self.growth = 100
            self.sunlight = 100
        elif self.groot_mood == "sleepy":
            self.sunlight = min(100, self.sunlight + 20)

        self._refresh_care_bars()
        self._update_status_card()

        if self.is_expanded:
            self._draw_full()
        else:
            self._draw_mini()

        # Sync 3D animated Groot window
        self.groot_3d.set_mood(self.groot_mood)
        self.update_transcript(f"[ Baby Groot ] Mood: {self.groot_mood.upper()}! 🌱")


    def _set_groot_gesture_safe(self, gesture):
        self.after(0, lambda: self._apply_groot_gesture(gesture))

    def _apply_groot_gesture(self, gesture):
        self.groot_gesture = gesture.lower()
        if gesture == "hug":
            self.hug_count += 1
            self.growth = min(100, self.growth + 10)
            self.groot_mood = "happy"
        elif gesture == "water":
            self.water_count += 1
            self.growth = min(100, self.growth + 15)
            self.sunlight = min(100, self.sunlight + 10)
            self.groot_mood = "sprouting"
        elif gesture == "dance":
            self.dance_count += 1
            self.growth = min(100, self.growth + 15)
            self.sunlight = max(10, self.sunlight - 5)
            self.groot_mood = "dancing"
        elif gesture == "sprout":
            self.growth = 100
            self.sunlight = 100
            self.groot_mood = "sprouting"
        elif gesture == "guard":
            self.groot_mood = "battle"

        self._refresh_care_bars()
        self._update_status_card()

        if self.is_expanded:
            self._draw_full()
        else:
            self._draw_mini()

        # Sync 3D animated Groot window gesture
        self.groot_3d.set_gesture(gesture)


    def _refresh_care_bars(self):
        if hasattr(self, "bar_growth") and self.bar_growth:
            self.bar_growth.set(self.growth / 100.0)
            self.lbl_growth.configure(text=f"Growth ({self.growth}%)")
        if hasattr(self, "bar_sunlight") and self.bar_sunlight:
            self.bar_sunlight.set(self.sunlight / 100.0)
            self.lbl_sunlight.configure(text=f"Sunlight ({self.sunlight}%)")
        if hasattr(self, "lbl_stats") and self.lbl_stats:
            self.lbl_stats.configure(text=f"Waterings: {self.water_count}  |  Dances: {self.dance_count}  |  Twig Hugs: {self.hug_count}")

    def _update_status_card(self):
        if not hasattr(self, 'status_card_title') or self.status_card_title is None:
            return
        mood_str = self.groot_mood.upper()
        try:
            self.status_card_title.configure(text=f"BABY GROOT STATUS // MOOD: {mood_str}")
            txt = (
                f"[ SPECIES ]: Flora Colossus (Planet X)  |  [ VOCAL ]: \"I am Groot!\"\n"
                f"[ SHORTCUTS ]: Dance (D), Water (W), Twig Hug (H), Sprout (Space), Guard (G)\n"
                f"[ MOOD KEYS ]: 1:Happy, 2:Dancing, 3:Sprouting, 4:Playful, 5:Sleepy, 6:Battle"
            )
            self.status_card_info.configure(text=txt)
        except Exception:
            pass

    # ============================================================
    # MOUSE & GESTURE INTERACTION HANDLERS
    # ============================================================
    def _on_mouse_down(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._has_dragged = False

    def _on_mouse_drag(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._has_dragged = True
            new_x = self.winfo_x() + dx
            new_y = self.winfo_y() + dy
            self.geometry(f"+{new_x}+{new_y}")
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root

    def _on_mouse_release(self, event):
        if self._has_dragged:
            self._has_dragged = False
            return
        if self._single_click_timer is not None:
            self.after_cancel(self._single_click_timer)
            self._single_click_timer = None
        self._single_click_timer = self.after(200, self._execute_left_click)

    def _execute_left_click(self):
        """Left Click: Cozy twig hug!"""
        self._single_click_timer = None
        actions.hug_groot()

    def _on_right_click(self, event):
        """Right Click: Water Baby Groot!"""
        actions.water_groot("fresh mineral water")

    def _on_middle_click(self, event):
        """Middle Click: Dance & groove!"""
        actions.dance_groot()

    def _on_double_click(self, event):
        """Double Click: Toggle Mini Companion / Expanded Dashboard Mode."""
        if self._single_click_timer is not None:
            self.after_cancel(self._single_click_timer)
            self._single_click_timer = None
        if self.is_expanded:
            self.collapse_window()
        else:
            self.expand_window()

    def _on_triple_click(self, event):
        """Triple Click: Sprout leaves & boost RAM!"""
        if self._single_click_timer is not None:
            self.after_cancel(self._single_click_timer)
            self._single_click_timer = None
        actions.sprout_groot()

    # ============================================================
    # KEYBOARD SHORTCUTS (1-6 for Moods, D/W/H/G/Space for Gestures)
    # ============================================================
    def _on_key_press(self, event):
        key = event.char
        sym = event.keysym.lower()

        if key in ['1', 'h', 'H'] and sym == '1':
            actions.set_groot_mood("happy")
        elif key in ['2'] or sym == '2':
            actions.set_groot_mood("dancing")
        elif key in ['3'] or sym == '3':
            actions.set_groot_mood("sprouting")
        elif key in ['4'] or sym == '4':
            actions.set_groot_mood("playful")
        elif key in ['5'] or sym == '5':
            actions.set_groot_mood("sleepy")
        elif key in ['6'] or sym == '6':
            actions.set_groot_mood("battle")
        elif key in ['d', 'D'] or sym == 'd':
            actions.dance_groot()
        elif key in ['w', 'W'] or sym == 'w':
            actions.water_groot()
        elif key in ['h', 'H'] or sym == 'h':
            actions.hug_groot()
        elif key in ['g', 'G'] or sym == 'g':
            actions.guard_groot()
        elif sym in ['space']:
            actions.sprout_groot()
        elif key in ['t', 'T', 'l', 'L'] or sym in ['t', 'l']:
            self._toggle_talk()

    # ============================================================
    # WINDOW EXPANSION & COLLAPSE
    # ============================================================
    def expand_window(self):
        """Expands into full companion dashboard."""
        self.is_expanded = True
        x = self.screen_w - FULL_WIDTH - PADDING_RIGHT
        y = self.screen_h - FULL_HEIGHT - PADDING_BOTTOM
        self.geometry(f"{FULL_WIDTH}x{FULL_HEIGHT}+{x}+{y}")

        self.canvas.configure(width=FULL_WIDTH, height=290)
        self.transcript_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self._draw_full()
        sounds.play_groot_sprout()

    def collapse_window(self):
        """Collapses into mini companion widget."""
        self.is_expanded = False
        self.transcript_frame.pack_forget()

        self.canvas.configure(width=MINI_WIDTH, height=MINI_HEIGHT)
        x = self.screen_w - MINI_WIDTH - PADDING_RIGHT
        y = self.screen_h - MINI_HEIGHT - PADDING_BOTTOM
        self.geometry(f"{MINI_WIDTH}x{MINI_HEIGHT}+{x}+{y}")
        self._draw_mini()
        sounds.play_groot_i_am_groot()

    # ============================================================
    # DIRECT COMMAND BAR & TRANSCRIPT
    # ============================================================
    def _toggle_talk(self):
        if not self.is_processing:
            self.wake_up()
        else:
            self.update_transcript("[ Audio Engine ] Voice listening active — speak your command!")

    def _submit_typed_command(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self.cmd_entry.delete(0, "end")
        logger.info(f"Command Bar input submitted: '{cmd}'")
        if not self.is_processing:
            self.wake_up(initial_query=cmd)
        else:
            self.ears.inject_text(cmd)

    def update_transcript(self, text: str):
        if not hasattr(self, 'transcript'):
            return
        try:
            self.transcript.configure(state="normal")
            self.transcript.insert("end", f"{text}\n")
            self.transcript.see("end")
            self.transcript.configure(state="disabled")
        except Exception:
            pass

        # Mirror Groot's responses as speech bubble in the 3D window
        if text.startswith("Groot:"):
            self.groot_3d.say(text[6:].strip())


    # ============================================================
    # AI ASSISTANT & SPEECH PROCESSING
    # ============================================================
    def hotkey_pressed(self):
        if not self.is_processing:
            self.after(0, self.wake_up)

    def wake_up(self, initial_query: str = None):
        if self.is_processing:
            return
        self.is_processing = True
        self.ai_state = "listening"
        sounds.play_groot_i_am_groot()
        threading.Thread(target=self._process_interaction, args=(initial_query,), daemon=True).start()

    def _process_interaction(self, initial_query: str = None):
        try:
            if initial_query:
                user_input = initial_query
            else:
                self.update_transcript("[ Listening... Speak to Baby Groot ]")
                user_input = self.ears.listen()

            if not user_input or not user_input.strip():
                self.ai_state = "monitoring"
                self.is_processing = False
                return

            self.update_transcript(f"You: {user_input}")
            clean_in = user_input.lower().strip()

            # Fast offline direct Groot intercepts
            if any(k in clean_in for k in ["dance", "dance groot", "baby groot dance"]):
                self.ai_state = "speaking"
                res = actions.dance_groot()
                self.update_transcript(f"Groot: {res}")
                self.voice.speak("I am Groot! Let's dance!")
                return
            elif any(k in clean_in for k in ["water", "water groot", "hydrate"]):
                self.ai_state = "speaking"
                res = actions.water_groot()
                self.update_transcript(f"Groot: {res}")
                self.voice.speak("I am Groot! Thank you for the fresh water!")
                return
            elif any(k in clean_in for k in ["hug", "hug groot", "cuddle"]):
                self.ai_state = "speaking"
                res = actions.hug_groot()
                self.update_transcript(f"Groot: {res}")
                self.voice.speak("I am Groot! Big twig hugs for you!")
                return
            elif any(k in clean_in for k in ["sprout", "grow leaves", "boost ram", "turbo"]):
                self.ai_state = "speaking"
                res = actions.sprout_groot()
                self.update_transcript(f"Groot: {res}")
                self.voice.speak("I am Groot! RAM boosted and system running at top speed!")
                return
            elif any(k in clean_in for k in ["guard", "guard pc", "battle mode", "lock computer"]):
                self.ai_state = "speaking"
                res = actions.guard_groot()
                self.update_transcript(f"Groot: {res}")
                self.voice.speak("I am Groot! Workstation locked securely!")
                return

            self.ai_state = "thinking"
            response = self.brain.think(user_input)

            self.update_transcript(f"Groot: {response}")
            self.ai_state = "speaking"

            self.voice.speak(response)

        except Exception as e:
            logger.error(f"Interaction processing error: {e}")
            self.update_transcript(f"[ Error ]: {e}")
        finally:
            self.ai_state = "monitoring"
            self.is_processing = False

    def _wake_word_loop(self):
        """Continuous background wake-word loop (Hey Buddy / Groot / Buddy)."""
        while True:
            try:
                if not self.is_processing:
                    res = self.ears.listen_for_wake_word()
                    if isinstance(res, tuple):
                        detected, query = res
                    else:
                        detected, query = bool(res), None
                    if detected and not self.is_processing:
                        logger.info("Wake word detected!")
                        self.after(0, lambda q=query: self.wake_up(initial_query=q))
                time.sleep(0.1)
            except Exception as e:
                time.sleep(1.0)


if __name__ == "__main__":
    app = BuddyApp()
    try:
        app.mainloop()
    finally:
        # Gracefully shut down 3D Groot viewer subprocess
        try:
            app.groot_3d.close()
        except Exception:
            pass
