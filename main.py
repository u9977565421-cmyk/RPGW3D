import pygame
import math
import random
import json
import os
from enum import Enum

# --- Configuration ---
WIDTH, HEIGHT = 800, 480
FPS = 60
TILE_SIZE = 64
MAP_SIZE = 30  
FOV = math.pi / 3
NUM_RAYS = 120
MAX_DEPTH = 800
DELTA_ANGLE = FOV / NUM_RAYS
# Magic number constants
PLAYER_SPEED = 5
PLAYER_ROTATION_SPEED = 0.05
QUEST_PICKUP_DISTANCE = 40
WALL_HEIGHT_MULTIPLIER = 21000
FOG_DISTANCE_DIVISOR = 2.6
PARTICLE_EPSILON = 0.0001
# Cloud parallax constants
CLOUD_SPRITE_PATH = "clouds_pixel.png"
CLOUD_LAYERS = 3  # Number of parallax layers
CLOUD_SPEED_MULTIPLIERS = [0.1, 0.2, 0.35]  # Speed for each layer (closer = faster)

# Dynamic weather system constants
WEATHER_TYPES = ['none', 'rain_light', 'rain_heavy', 'snow', 'sandstorm']
WEATHER_TRANSITIONS = {  # Min and max duration in frames (at 60 FPS)
    'none': (120, 300),
    'rain_light': (180, 480),
    'rain_heavy': (240, 600),
    'snow': (200, 500),
    'sandstorm': (150, 420)
}
WEATHER_INTENSITY = {  # Particle density and effect intensity
    'rain_light': {'count': 150, 'speed_mult': 0.6},
    'rain_heavy': {'count': 300, 'speed_mult': 1.2},
    'snow': {'count': 180, 'speed_mult': 0.3},
    'sandstorm': {'count': 400, 'speed_mult': 0.8, 'wind': 3.0}
}

# Weather Colors
RAIN_COLOR = (100, 150, 255)
SNOW_COLOR = (255, 255, 255)
DUST_COLOR = (140, 120, 90)

# Map Editor Configuration
EDITOR_WIDTH = 1200
EDITOR_HEIGHT = 800
GRID_SIZE = 32  # Size of each grid cell in editor
MAP_DATA_FILE = "map_data.json"

class TileType(Enum):
    EMPTY = 0
    WALL = 1

class ToolMode(Enum):
    DRAW = 0
    ERASE = 1
    FILL = 2
    PICK = 3

class MapEditor:
    """Integrated map editor for the game"""
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((EDITOR_WIDTH, EDITOR_HEIGHT))
        pygame.display.set_caption("Wolfenstein 3D Map Editor")
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("georgia", 14)
        self.font_medium = pygame.font.SysFont("georgia", 16, bold=True)
        self.font_large = pygame.font.SysFont("georgia", 20, bold=True)
        
        # Map data
        self.map = [[1 for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
        self.map_filename = MAP_DATA_FILE
        
        # Editor state
        self.tool_mode = ToolMode.DRAW
        self.current_tile = TileType.WALL
        self.mouse_pos = (0, 0)
        self.dragging = False
        self.grid_offset_x = 20
        self.grid_offset_y = 20
        self.zoom = 1.0
        
        # Undo/Redo system
        self.history = []
        self.history_index = -1
        self.max_history = 50
        self.save_state()
        
        # UI
        self.status_message = "Ready"
        self.status_timer = 0
        self.show_grid = True
        self.show_help = False
        
        # Load existing map if available
        self.load_map()

    def save_state(self):
        """Save current map state to history for undo/redo"""
        # Remove any redo history when making new changes
        self.history = self.history[:self.history_index + 1]
        
        # Deep copy current map
        state = [row[:] for row in self.map]
        self.history.append(state)
        self.history_index = len(self.history) - 1
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1

    def undo(self):
        """Undo last change"""
        if self.history_index > 0:
            self.history_index -= 1
            self.map = [row[:] for row in self.history[self.history_index]]
            self.set_status("Undo applied")

    def redo(self):
        """Redo last undone change"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.map = [row[:] for row in self.history[self.history_index]]
            self.set_status("Redo applied")

    def set_status(self, message):
        """Set status message with timer"""
        self.status_message = message
        self.status_timer = 120  # 2 seconds at 60 FPS

    def screen_to_grid(self, screen_x, screen_y):
        """Convert screen coordinates to grid coordinates"""
        grid_x = (screen_x - self.grid_offset_x) // (GRID_SIZE * self.zoom)
        grid_y = (screen_y - self.grid_offset_y) // (GRID_SIZE * self.zoom)
        return int(grid_x), int(grid_y)

    def grid_to_screen(self, grid_x, grid_y):
        """Convert grid coordinates to screen coordinates"""
        screen_x = self.grid_offset_x + grid_x * GRID_SIZE * self.zoom
        screen_y = self.grid_offset_y + grid_y * GRID_SIZE * self.zoom
        return int(screen_x), int(screen_y)

    def is_valid_grid_pos(self, grid_x, grid_y):
        """Check if grid position is valid"""
        return 0 <= grid_x < MAP_SIZE and 0 <= grid_y < MAP_SIZE

    def draw_tile(self, grid_x, grid_y, tile_value=None):
        """Draw a single tile"""
        if not self.is_valid_grid_pos(grid_x, grid_y):
            return
        
        if tile_value is not None:
            old_value = self.map[grid_y][grid_x]
            if old_value != tile_value:
                self.map[grid_y][grid_x] = tile_value
                self.set_status(f"Tile set at ({grid_x}, {grid_y})")
        else:
            self.map[grid_y][grid_x] = self.current_tile.value

    def erase_tile(self, grid_x, grid_y):
        """Erase a tile (set to empty)"""
        if self.is_valid_grid_pos(grid_x, grid_y):
            self.map[grid_y][grid_x] = TileType.EMPTY.value

    def fill_region(self, start_x, start_y, fill_value):
        """Flood fill algorithm"""
        if not self.is_valid_grid_pos(start_x, start_y):
            return
        
        target_value = self.map[start_y][start_x]
        if target_value == fill_value:
            return
        
        stack = [(start_x, start_y)]
        filled = set()
        
        while stack:
            x, y = stack.pop()
            if (x, y) in filled:
                continue
            if not self.is_valid_grid_pos(x, y):
                continue
            if self.map[y][x] != target_value:
                continue
            
            filled.add((x, y))
            self.map[y][x] = fill_value
            
            # Add neighbors
            stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])
        
        self.set_status(f"Filled {len(filled)} tiles")

    def handle_mouse_click(self, pos, button):
        """Handle mouse clicks"""
        grid_x, grid_y = self.screen_to_grid(pos[0], pos[1])
        
        if button == 1:  # Left click
            if self.tool_mode == ToolMode.DRAW:
                self.draw_tile(grid_x, grid_y)
                self.dragging = True
            elif self.tool_mode == ToolMode.ERASE:
                self.erase_tile(grid_x, grid_y)
                self.dragging = True
            elif self.tool_mode == ToolMode.FILL:
                self.fill_region(grid_x, grid_y, self.current_tile.value)
                self.save_state()
            elif self.tool_mode == ToolMode.PICK:
                if self.is_valid_grid_pos(grid_x, grid_y):
                    self.current_tile = TileType(self.map[grid_y][grid_x])
                    self.set_status(f"Picked tile: {self.current_tile.name}")

    def handle_mouse_motion(self, pos):
        """Handle mouse motion for dragging"""
        self.mouse_pos = pos
        
        if self.dragging:
            grid_x, grid_y = self.screen_to_grid(pos[0], pos[1])
            if self.tool_mode == ToolMode.DRAW:
                self.draw_tile(grid_x, grid_y)
            elif self.tool_mode == ToolMode.ERASE:
                self.erase_tile(grid_x, grid_y)

    def handle_mouse_release(self, button):
        """Handle mouse release"""
        if button == 1:
            self.dragging = False
            if self.tool_mode in [ToolMode.DRAW, ToolMode.ERASE]:
                self.save_state()

    def handle_input(self):
        """Handle keyboard input"""
        keys = pygame.key.get_pressed()
        
        # Pan with arrow keys
        pan_speed = 5
        if keys[pygame.K_LEFT]:
            self.grid_offset_x += pan_speed
        if keys[pygame.K_RIGHT]:
            self.grid_offset_x -= pan_speed
        if keys[pygame.K_UP]:
            self.grid_offset_y += pan_speed
        if keys[pygame.K_DOWN]:
            self.grid_offset_y -= pan_speed
        
        # Zoom with +/-
        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS]:
            if self.zoom < 2.0:
                self.zoom *= 1.02
        if keys[pygame.K_MINUS]:
            if self.zoom > 0.5:
                self.zoom *= 0.98

    def handle_keypress(self, key):
        """Handle key presses"""
        if key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.undo()
        elif key == pygame.K_y and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.redo()
        elif key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.save_map()
        elif key == pygame.K_l and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.load_map()
        elif key == pygame.K_n and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.new_map()
        elif key == pygame.K_g:
            self.show_grid = not self.show_grid
            self.set_status(f"Grid {'enabled' if self.show_grid else 'disabled'}")
        elif key == pygame.K_h:
            self.show_help = not self.show_help
        elif key == pygame.K_1:
            self.tool_mode = ToolMode.DRAW
            self.current_tile = TileType.WALL
            self.set_status("Tool: Draw Wall")
        elif key == pygame.K_2:
            self.tool_mode = ToolMode.ERASE
            self.set_status("Tool: Erase (Empty)")
        elif key == pygame.K_3:
            self.tool_mode = ToolMode.FILL
            self.set_status("Tool: Fill")
        elif key == pygame.K_4:
            self.tool_mode = ToolMode.PICK
            self.set_status("Tool: Pick Tile")
        elif key == pygame.K_SPACE:
            # Clear map (borders only)
            self.map = [[1 for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
            for y in range(1, MAP_SIZE - 1):
                for x in range(1, MAP_SIZE - 1):
                    self.map[y][x] = 0
            self.save_state()
            self.set_status("Map cleared")

    def new_map(self):
        """Create a new map"""
        self.map = [[1 for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
        self.history = []
        self.history_index = -1
        self.save_state()
        self.set_status("New map created")

    def save_map(self):
        """Save map to JSON file"""
        try:
            data = {'map': self.map, 'map_size': MAP_SIZE}
            with open(self.map_filename, 'w') as f:
                json.dump(data, f, indent=2)
            self.set_status(f"Map saved to {self.map_filename}")
        except Exception as e:
            self.set_status(f"Error saving map: {str(e)}")

    def load_map(self):
        """Load map from JSON file"""
        try:
            if os.path.exists(self.map_filename):
                with open(self.map_filename, 'r') as f:
                    data = json.load(f)
                    self.map = data.get('map', self.map)
                    self.set_status(f"Map loaded from {self.map_filename}")
                    self.history = []
                    self.history_index = -1
                    self.save_state()
        except Exception as e:
            self.set_status(f"Error loading map: {str(e)}")

    def draw_grid(self):
        """Draw the map grid"""
        self.screen.fill((30, 30, 35))
        
        # Draw grid lines
        if self.show_grid:
            grid_color = (60, 60, 70)
            
            # Vertical lines
            x = self.grid_offset_x
            while x < EDITOR_WIDTH:
                pygame.draw.line(self.screen, grid_color, (x, 0), (x, EDITOR_HEIGHT), 1)
                x += int(GRID_SIZE * self.zoom)
            
            # Horizontal lines
            y = self.grid_offset_y
            while y < EDITOR_HEIGHT:
                pygame.draw.line(self.screen, grid_color, (0, y), (EDITOR_WIDTH, y), 1)
                y += int(GRID_SIZE * self.zoom)
        
        # Draw map tiles
        for grid_y in range(MAP_SIZE):
            for grid_x in range(MAP_SIZE):
                screen_x, screen_y = self.grid_to_screen(grid_x, grid_y)
                cell_size = int(GRID_SIZE * self.zoom)
                
                if self.map[grid_y][grid_x] == 1:
                    # Wall tile
                    pygame.draw.rect(self.screen, (120, 100, 80), 
                                   (screen_x, screen_y, cell_size, cell_size))
                    pygame.draw.rect(self.screen, (80, 60, 40), 
                                   (screen_x, screen_y, cell_size, cell_size), 1)
                else:
                    # Empty tile
                    pygame.draw.rect(self.screen, (50, 70, 50), 
                                   (screen_x, screen_y, cell_size, cell_size))
                    pygame.draw.rect(self.screen, (70, 90, 70), 
                                   (screen_x, screen_y, cell_size, cell_size), 1)

    def draw_ui(self):
        """Draw user interface elements"""
        # Tool indicator
        tool_text = f"Tool: {self.tool_mode.name} | Tile: {self.current_tile.name}"
        tool_surf = self.font_medium.render(tool_text, True, (200, 200, 200))
        self.screen.blit(tool_surf, (10, 10))
        
        # Status message
        if self.status_timer > 0:
            status_surf = self.font_small.render(self.status_message, True, (150, 255, 150))
            self.screen.blit(status_surf, (10, 35))
            self.status_timer -= 1
        
        # Coordinates at cursor
        grid_x, grid_y = self.screen_to_grid(self.mouse_pos[0], self.mouse_pos[1])
        if self.is_valid_grid_pos(grid_x, grid_y):
            coord_text = f"Grid: ({grid_x}, {grid_y}) | Value: {self.map[grid_y][grid_x]}"
            coord_surf = self.font_small.render(coord_text, True, (200, 200, 200))
            self.screen.blit(coord_surf, (10, EDITOR_HEIGHT - 60))
        
        # Zoom level
        zoom_text = f"Zoom: {self.zoom:.2f}x"
        zoom_surf = self.font_small.render(zoom_text, True, (200, 200, 200))
        self.screen.blit(zoom_surf, (10, EDITOR_HEIGHT - 35))
        
        # Help
        help_y = EDITOR_HEIGHT - 200
        if self.show_help:
            help_lines = [
                "--- CONTROLS ---",
                "1/2/3/4: Draw/Erase/Fill/Pick tools",
                "Left Click: Use current tool",
                "Arrow Keys: Pan view",
                "+/-: Zoom",
                "G: Toggle grid | H: Toggle help",
                "SPACE: Clear map",
                "Ctrl+Z: Undo | Ctrl+Y: Redo",
                "Ctrl+S: Save | Ctrl+L: Load",
                "Ctrl+N: New Map | ESC: Exit to Game"
            ]
            
            for i, line in enumerate(help_lines):
                help_surf = self.font_small.render(line, True, (150, 200, 255))
                self.screen.blit(help_surf, (10, help_y + i * 18))

    def run(self):
        """Main editor loop"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_mouse_click(event.pos, event.button)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.handle_mouse_release(event.button)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        self.handle_keypress(event.key)
            
            self.handle_input()
            self.draw_grid()
            self.draw_ui()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()

class Inventory:
    def __init__(self, on_consume_callback=None):
        self.items = [{"name": "Gold", "qty": 50, "type": "currency"},
                      {"name": "Iron Dagger", "qty": 1, "type": "weapon", "equipped": False},
                      {"name": "Sweetroll", "qty": 2, "type": "consumable", "health": 30, "mana": 0},
                      {"name": "Brass Key", "qty": 1, "type": "key"}]
        self.visible = False
        self.selected_idx = 0
        self.on_consume_callback = on_consume_callback

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.selected_idx = 0

    def handle_input(self, key):
        if not self.visible: return
        max_items = len(self.items)
        
        if key == pygame.K_UP:
            self.selected_idx = (self.selected_idx - 1) % max_items
        elif key == pygame.K_DOWN:
            self.selected_idx = (self.selected_idx + 1) % max_items
        elif key == pygame.K_e:  # Equip/Unequip
            item = self.items[self.selected_idx]
            if item["type"] == "weapon":
                item["equipped"] = not item.get("equipped", False)
        elif key == pygame.K_u:  # Use/Drink
            item = self.items[self.selected_idx]
            if item["type"] == "consumable" and item["qty"] > 0:
                # Apply consumable effects
                health_restore = item.get("health", 0)
                mana_restore = item.get("mana", 0)
                if self.on_consume_callback:
                    self.on_consume_callback(item["name"], health_restore, mana_restore)
                item["qty"] -= 1
        elif key == pygame.K_d:  # Drop
            item = self.items[self.selected_idx]
            if item["qty"] > 0:
                item["qty"] -= 1

    def draw(self, screen):
        if not self.visible: return
        overlay = pygame.Surface((400, 450))
        overlay.set_alpha(220)
        overlay.fill((20, 15, 10)) 
        screen.blit(overlay, (WIDTH//2 - 200, 20))
        
        # Border
        pygame.draw.rect(screen, (200, 180, 100), (WIDTH//2 - 200, 20, 400, 450), 3)
        
        font_title = pygame.font.SysFont("georgia", 28, bold=True)
        font_item = pygame.font.SysFont("georgia", 20)
        font_small = pygame.font.SysFont("georgia", 16)
        
        title = font_title.render("- INVENTORY -", True, (200, 180, 100))
        screen.blit(title, (WIDTH//2 - 95, 35))
        
        y_offset = 90
        slot_height = 50
        
        for idx, item in enumerate(self.items):
            is_selected = (idx == self.selected_idx)
            
            # Draw selection box
            if is_selected:
                pygame.draw.rect(screen, (220, 100, 50), (WIDTH//2 - 180, y_offset - 5, 360, slot_height + 10), 3)
                bg_color = (60, 40, 20)
            else:
                bg_color = (40, 30, 20)
            
            pygame.draw.rect(screen, bg_color, (WIDTH//2 - 175, y_offset, 350, slot_height))
            
            # Item name and quantity
            name_text = f"{item['name']}: {item['qty']}"
            if item.get("equipped"):
                name_text += " [EQUIPPED]"
            
            text = font_item.render(name_text, True, (255, 200, 100))
            screen.blit(text, (WIDTH//2 - 165, y_offset + 8))
            
            # Action hints
            if is_selected:
                hint_text = "E:Equip  U:Use  D:Drop"
                hint = font_small.render(hint_text, True, (150, 150, 100))
                screen.blit(hint, (WIDTH//2 - 165, y_offset + 28))
            
            y_offset += slot_height + 10
        
        # Instructions at bottom
        instr_text = "Arrow Keys: Navigate | I: Close"
        instr = font_small.render(instr_text, True, (150, 150, 100))
        screen.blit(instr, (WIDTH//2 - 120, y_offset + 20))

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Wolfenstein 3D Style - Quest & Weather")
        self.clock = pygame.time.Clock()
        
        # Systems
        self.inventory = Inventory(on_consume_callback=self.consume_item)
        self.map = self.load_or_generate_map()
        self.player_x, self.player_y = self.get_safe_spawn()
        self.player_angle = 0
        
        # Player stats
        self.health = 100
        self.max_health = 100
        self.mana = 50
        self.max_mana = 50
        
        # Environment & Day/Night
        self.time = 0.0 
        self.ambient_light = 255
        self.sky_keyframes = {0: (5, 5, 20), 600: (255, 140, 90), 1200: (135, 206, 235), 1800: (200, 70, 30), 2400: (5, 5, 20)}
        self.wall_tex = self.create_brick_texture()
        self.floor_tex = self.load_floor_texture()
        self.floor_color = (25, 60, 25)
        
        # Cloud sprite with parallax
        self.cloud_sprite = self.load_cloud_sprite()
        self.cloud_sprites_cache = {}  # Scaled sprite cache
        self.clouds = self.generate_parallax_clouds()
        
        # Quest System
        self.quest_item_pos = self.get_safe_spawn() # Randomly place the artifact
        self.quest_completed = False

        # Dynamic Weather System
        self.weather_type = 'none'
        self.weather_timer = 0
        self.weather_duration = random.randint(WEATHER_TRANSITIONS['none'][0], WEATHER_TRANSITIONS['none'][1])
        self.current_weather_intensity = 0
        self.wind_effect = 0 
        self.depth_buffer = [MAX_DEPTH] * NUM_RAYS
        self.particles = []
        self.init_particles()
        
        # Consume feedback
        self.consume_message = ""
        self.consume_message_timer = 0
        
        # Teleport/Door System
        self.doors = [
            {"x": 500, "y": 500, "name": "Mystery Portal", "key_required": "Brass Key", "teleport_x": 1000, "teleport_y": 1000}
        ]
        self.door_range = 60  # Distance to interact with door
        self.in_interior = False
        self.exterior_spawn = (128, 128)  # Remember where player came from
        
        # Fog of War (Minimap visibility tracking)
        self.fog_of_war = [[False for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
        self.minimap_reveal_radius = 8  # Cells revealed on minimap
        self.minimap_x = WIDTH - 150
        self.minimap_y = 20
        self.minimap_size = 140
        
        # Torch system
        self.torches = self.generate_torches()
        self.torch_light_range = 200  # Light radius in pixels
        self.torch_brightness = 255

    def load_or_generate_map(self):
        """Load map from file or generate a new one"""
        try:
            if os.path.exists(MAP_DATA_FILE):
                with open(MAP_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('map', self.generate_dungeon())
        except:
            pass
        return self.generate_dungeon()

    def generate_torches(self):
        """Generate randomly placed torches in open areas"""
        torches = []
        attempts = 0
        while len(torches) < 15 and attempts < 100:  # Place up to 15 torches
            x = random.randint(5, MAP_SIZE - 5) * TILE_SIZE + TILE_SIZE // 2
            y = random.randint(5, MAP_SIZE - 5) * TILE_SIZE + TILE_SIZE // 2
            # Check if position is in open area (not wall)
            if self.map[int(y/TILE_SIZE)][int(x/TILE_SIZE)] == 0:
                torches.append({"x": x, "y": y, "light": 255})
            attempts += 1
        return torches

    def get_torch_lighting(self, px, py):
        """Calculate lighting contribution from all torches"""
        torch_light = 0
        for torch in self.torches:
            # Calculate distance from player to torch
            dx = torch["x"] - px
            dy = torch["y"] - py
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist < self.torch_light_range:
                # Quadratic falloff
                light_contrib = int((1 - (dist / self.torch_light_range)**2) * 80)
                torch_light = max(torch_light, light_contrib)
        return torch_light

    def update_fog_of_war(self):
        """Update visible areas based on player position"""
        player_grid_x = int(self.player_x / TILE_SIZE)
        player_grid_y = int(self.player_y / TILE_SIZE)
        
        for y in range(max(0, player_grid_y - self.minimap_reveal_radius), 
                       min(MAP_SIZE, player_grid_y + self.minimap_reveal_radius + 1)):
            for x in range(max(0, player_grid_x - self.minimap_reveal_radius), 
                          min(MAP_SIZE, player_grid_x + self.minimap_reveal_radius + 1)):
                dist = math.sqrt((x - player_grid_x)**2 + (y - player_grid_y)**2)
                if dist <= self.minimap_reveal_radius:
                    self.fog_of_war[y][x] = True

    def draw_sun_moon(self):
        """Draw sun/moon based on time of day"""
        # Calculate sun/moon position across the sky
        # 0-300: night (moon), 300-900: sunrise to daytime, 900-1500: day, 1500-1800: sunset, 1800-2400: night
        
        sun_x = WIDTH // 2
        sun_y = HEIGHT // 4
        sun_size = 40
        
        if 600 <= self.time < 1800:  # Sun visible during day
            # Sun moves across sky from left to right
            progress = (self.time - 600) / (1800 - 600)
            sun_x = int(50 + progress * (WIDTH - 100))
            sun_y = int(HEIGHT // 4 + 30 * math.sin(progress * math.pi))
            
            # Draw sun with glow
            pygame.draw.circle(self.screen, (255, 200, 50), (sun_x, sun_y), sun_size + 5)
            pygame.draw.circle(self.screen, (255, 220, 100), (sun_x, sun_y), sun_size)
        else:  # Moon visible at night
            # Moon position roughly opposite to sun
            if self.time < 600:
                progress = self.time / 600  # Morning approach
            else:
                progress = (self.time - 1800) / 600  # Evening to night
            
            moon_x = int(WIDTH // 2 + 100 * math.cos(progress * math.pi))
            moon_y = int(HEIGHT // 4 + 30)
            
            # Draw moon with craters
            pygame.draw.circle(self.screen, (220, 220, 200), (moon_x, moon_y), sun_size - 5)
            pygame.draw.circle(self.screen, (100, 100, 80), (moon_x - 10, moon_y - 5), 4)
            pygame.draw.circle(self.screen, (100, 100, 80), (moon_x + 8, moon_y + 8), 3)

    def draw_stars(self):
        """Draw stars at night"""
        # Only show stars when it's dark
        if self.time < 600 or self.time > 1800:
            # Use time-based seed for consistent star positions
            random.seed(42)  # Consistent star field
            for _ in range(100):
                star_x = random.randint(0, WIDTH)
                star_y = random.randint(0, HEIGHT // 2)
                star_size = random.randint(1, 2)
                brightness = int(200 + 55 * math.sin(self.time / 100))  # Twinkling effect
                pygame.draw.circle(self.screen, (brightness, brightness, brightness), (star_x, star_y), star_size)
            random.seed()  # Reset seed

    def draw_minimap(self):
        """Draw minimap with fog of war"""
        minimap_w = self.minimap_size
        minimap_h = self.minimap_size
        cell_size = minimap_w / MAP_SIZE
        
        # Draw background
        pygame.draw.rect(self.screen, (20, 20, 20), (self.minimap_x, self.minimap_y, minimap_w + 4, minimap_h + 4))
        pygame.draw.rect(self.screen, (100, 100, 100), (self.minimap_x, self.minimap_y, minimap_w + 4, minimap_h + 4), 2)
        
        # Draw map
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                tile_x = self.minimap_x + 2 + x * cell_size
                tile_y = self.minimap_y + 2 + y * cell_size
                
                if self.fog_of_war[y][x]:
                    # Revealed tile
                    if self.map[y][x] == 1:
                        pygame.draw.rect(self.screen, (100, 50, 50), (tile_x, tile_y, cell_size, cell_size))
                    else:
                        pygame.draw.rect(self.screen, (50, 80, 50), (tile_x, tile_y, cell_size, cell_size))
                else:
                    # Unrevealed (fog of war)
                    pygame.draw.rect(self.screen, (30, 30, 30), (tile_x, tile_y, cell_size, cell_size))
        
        # Draw player position on minimap
        player_map_x = self.minimap_x + 2 + (self.player_x / (MAP_SIZE * TILE_SIZE)) * minimap_w
        player_map_y = self.minimap_y + 2 + (self.player_y / (MAP_SIZE * TILE_SIZE)) * minimap_h
        pygame.draw.circle(self.screen, (0, 255, 0), (int(player_map_x), int(player_map_y)), 3)

    def consume_item(self, item_name, health_restore, mana_restore):
        """Handle consumable use"""
        self.health = min(self.max_health, self.health + health_restore)
        self.mana = min(self.max_mana, self.mana + mana_restore)
        self.consume_message = f"Used {item_name}! +{health_restore}HP +{mana_restore}MP"
        self.consume_message_timer = 120  # Display for 2 seconds at 60 FPS

    def has_key(self, key_name):
        """Check if player has a specific key in inventory"""
        for item in self.inventory.items:
            if item["type"] == "key" and item["name"] == key_name and item["qty"] > 0:
                return True
        return False

    def check_nearby_doors(self):
        """Check if player is near a door and return it"""
        for door in self.doors:
            dist = math.sqrt((self.player_x - door["x"])**2 + (self.player_y - door["y"])**2)
            if dist < self.door_range:
                return door
        return None

    def try_use_door(self):
        """Attempt to use a door if nearby"""
        door = self.check_nearby_doors()
        if door:
            # Check if key is required
            if "key_required" in door:
                if not self.has_key(door["key_required"]):
                    self.consume_message = f"Need {door['key_required']}!"
                    self.consume_message_timer = 120
                    return
            # Teleport!
            self.exterior_spawn = (self.player_x, self.player_y)
            self.player_x = door["teleport_x"]
            self.player_y = door["teleport_y"]
            self.in_interior = True
            self.consume_message = f"Entered {door['name']}!"
            self.consume_message_timer = 120

    def lerp_color(self, c1, c2, t):
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    def get_smooth_ambient_light(self):
        """Calculate smooth ambient light based on time of day"""
        # Sunrise: 300-900 (transition from dark to bright)
        # Day: 900-1500 (bright)
        # Sunset: 1500-1800 (transition from bright to dark)
        # Night: 1800-300 (dark)
        
        t = self.time
        
        if 300 <= t < 900:  # Sunrise
            progress = (t - 300) / 600
            return int(70 + (255 - 70) * progress)
        elif 900 <= t < 1500:  # Full daylight
            return 255
        elif 1500 <= t < 1800:  # Sunset
            progress = (t - 1500) / 300
            return int(255 - (255 - 70) * progress)
        else:  # Night (1800-300 next cycle)
            return 70

    def get_sky_color(self):
        keys = sorted(self.sky_keyframes.keys())
        for i in range(len(keys) - 1):
            s_t, e_t = keys[i], keys[i+1]
            if s_t <= self.time <= e_t:
                progress = (self.time - s_t) / (e_t - s_t)
                return self.lerp_color(self.sky_keyframes[s_t], self.sky_keyframes[e_t], progress)
        return (5, 5, 20)

    def generate_dungeon(self):
        d_map = [[1 for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
        x, y = MAP_SIZE // 2, MAP_SIZE // 2
        d_map[y][x] = 0
        for _ in range(600):
            move = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
            nx, ny = x + move[0], y + move[1]
            if 1 <= nx < MAP_SIZE-1 and 1 <= ny < MAP_SIZE-1:
                x, y = nx, ny
                d_map[y][x] = 0
        return d_map

    def get_safe_spawn(self):
        for _ in range(100):
            r, c = random.randint(1, MAP_SIZE-1), random.randint(1, MAP_SIZE-1)
            if self.map[r][c] == 0: return (c * TILE_SIZE + 32, r * TILE_SIZE + 32)
        return (128, 128)

    def create_brick_texture(self):
        tex = pygame.Surface((TILE_SIZE, TILE_SIZE))
        tex.fill((90, 45, 35))
        for y in range(0, TILE_SIZE, 16):
            pygame.draw.line(tex, (50, 25, 20), (0, y), (TILE_SIZE, y), 2)
        return tex

    def load_floor_texture(self):
        """Load floor texture from file"""
        try:
            import os
            texture_path = os.path.join(os.path.dirname(__file__), "Dirt_Road_64x64.png")
            return pygame.image.load(texture_path).convert()
        except:
            # Fallback: create a simple dirt texture if file not found
            surf = pygame.Surface((64, 64))
            surf.fill((101, 84, 60))
            # Add some variation
            for _ in range(100):
                x = random.randint(0, 63)
                y = random.randint(0, 63)
                color = (random.randint(80, 120), random.randint(70, 100), random.randint(40, 70))
                pygame.draw.rect(surf, color, (x, y, 2, 2))
            return surf

    def load_cloud_sprite(self):
        """Load cloud sprite from file"""
        try:
            import os
            sprite_path = os.path.join(os.path.dirname(__file__), CLOUD_SPRITE_PATH)
            return pygame.image.load(sprite_path).convert_alpha()
        except:
            # Fallback: create a simple cloud shape if file not found
            surf = pygame.Surface((100, 40), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 255, 255, 200), (20, 20), 15)
            pygame.draw.circle(surf, (255, 255, 255, 200), (40, 15), 18)
            pygame.draw.circle(surf, (255, 255, 255, 200), (60, 20), 16)
            pygame.draw.rect(surf, (255, 255, 255, 200), (20, 20, 40, 20))
            return surf

    def get_scaled_cloud_sprite(self, scale):
        """Get scaled cloud sprite from cache or create new one"""
        if scale not in self.cloud_sprites_cache:
            w, h = self.cloud_sprite.get_size()
            new_size = (int(w * scale), int(h * scale))
            self.cloud_sprites_cache[scale] = pygame.transform.scale(self.cloud_sprite, new_size)
        return self.cloud_sprites_cache[scale]

    def generate_parallax_clouds(self):
        """Generate clouds with parallax depth layers"""
        clouds = []
        for layer in range(CLOUD_LAYERS):
            num_clouds = 3 + layer  # More clouds
            depth = layer / (CLOUD_LAYERS - 1) if CLOUD_LAYERS > 1 else 1.0  # 0 to 1
            for _ in range(num_clouds):
                scale = 2.0 + (depth * 2.2)  # Much bigger clouds!
                clouds.append({
                    'x': random.randint(0, WIDTH),
                    'y': random.randint(10, 100 + layer * 20),
                    'scale': scale,
                    'depth': depth,
                    'speed_mult': CLOUD_SPEED_MULTIPLIERS[layer],
                    'alpha': 150 - int(depth * 50)  # Farther clouds are dimmer
                })
        return clouds

    def init_particles(self):
        count = WEATHER_INTENSITY.get(self.weather_type, {}).get('count', 250)
        self.particles = []
        for _ in range(count):
            p = {
                'x': random.uniform(0, MAP_SIZE*TILE_SIZE),
                'y': random.uniform(0, MAP_SIZE*TILE_SIZE),
                'z': random.uniform(-180, 180),
                'speed': random.uniform(4, 8),
                'wind_accel': 0  # For sandstorm wind effect
            }
            self.particles.append(p)

    def transition_weather(self):
        """Randomly transition to a new weather type"""
        current_idx = WEATHER_TYPES.index(self.weather_type) if self.weather_type in WEATHER_TYPES else 0
        # Prefer transitioning away from current weather, but allow stay sometimes
        if random.random() < 0.3:  # 30% chance to stay same weather
            new_weather = self.weather_type
        else:
            new_weather = random.choice([w for w in WEATHER_TYPES if w != self.weather_type])
        
        self.weather_type = new_weather
        self.weather_timer = 0
        min_dur, max_dur = WEATHER_TRANSITIONS.get(new_weather, (60, 300))
        self.weather_duration = random.randint(min_dur, max_dur)
        
        # Update particle count for new weather
        old_particle_count = len(self.particles)
        new_particle_count = WEATHER_INTENSITY.get(new_weather, {}).get('count', 0)
        if new_weather == 'none':
            self.particles = []
        else:
            self.init_particles()

    def update(self):
        if self.inventory.visible: return 
        self.time = (self.time + 0.5) % 2400
        self.ambient_light = self.get_smooth_ambient_light()
        
        # Add torch lighting at night
        if self.ambient_light < 150:
            self.ambient_light = min(255, self.ambient_light + self.get_torch_lighting(self.player_x, self.player_y))
        
        # Update fog of war for minimap
        self.update_fog_of_war()
        
        # Update consume message timer
        if self.consume_message_timer > 0:
            self.consume_message_timer -= 1
        
        # Weather system update
        self.weather_timer += 1
        if self.weather_timer >= self.weather_duration:
            self.transition_weather()
        
        # Update wind for sandstorms
        if 'sand' in self.weather_type:
            self.wind_effect = math.sin(self.weather_timer * 0.02) * 2.0
        else:
            self.wind_effect = 0
        
        # Quest Pickup Logic
        dist = math.sqrt((self.player_x - self.quest_item_pos[0])**2 + (self.player_y - self.quest_item_pos[1])**2)
        if dist < QUEST_PICKUP_DISTANCE and not self.quest_completed:
            self.quest_completed = True
            self.inventory.items.append({"name": "Mystic Artifact", "qty": 1, "type": "quest"})

        for c in self.clouds: c['x'] = (c['x'] + c['speed_mult'] * 0.3) % (WIDTH + 100)

        if self.weather_type != 'none':
            for p in self.particles:
                p['z'] += p['speed']
                if p['z'] > 180: p['z'] = -180
                # Wind effect for sandstorms
                if 'sand' in self.weather_type:
                    p['wind_accel'] = self.wind_effect

    def draw(self):
        # 1. Sky & Ground
        sky_c = self.get_sky_color()
        self.screen.fill(sky_c, (0, 0, WIDTH, HEIGHT // 2))
        
        # Draw celestial objects
        self.draw_stars()
        self.draw_sun_moon()
        
        for c in self.clouds:
            scaled_sprite = self.get_scaled_cloud_sprite(c['scale'])
            
            # Darken clouds during heavy rain
            if self.weather_type == 'rain_heavy':
                cloud_alpha = max(50, c['alpha'] - 80)  # Make very dark
                tint_color = (50, 50, 50)  # Grey tint for stormy look
                scaled_sprite.fill(tint_color, special_flags=pygame.BLEND_RGB_MULT)
            else:
                cloud_alpha = c['alpha']
            
            scaled_sprite.set_alpha(cloud_alpha)
            cloud_width = scaled_sprite.get_width()
            x_pos = c['x']
            # Draw cloud wrapping at screen edges
            self.screen.blit(scaled_sprite, (x_pos, c['y']))
            if x_pos + cloud_width < WIDTH:
                self.screen.blit(scaled_sprite, (x_pos + WIDTH + 50, c['y']))
            if x_pos - cloud_width > -cloud_width:
                self.screen.blit(scaled_sprite, (x_pos - WIDTH - 50, c['y']))

        t_mult = self.ambient_light / 255.0
        # Draw textured floor with proper perspective
        for y in range(HEIGHT // 2, HEIGHT, 1):
            shade = max(0.1, min(1.0, ((y - HEIGHT/2) / (HEIGHT/2.0)) * 1.5))
            intensity = int(255 * shade * t_mult)
            
            # Calculate texture offset based on distance (for proper tiling effect)
            distance = (y - HEIGHT//2) / (HEIGHT//2)
            tex_offset = int((self.player_angle * 100 + distance * 1000) % 64)
            
            # Draw a row using the floor texture
            for x in range(0, WIDTH, 64):
                try:
                    tex_col = self.floor_tex.subsurface((tex_offset, 0, 64, 1))
                except ValueError:
                    # Fallback if subsurface fails
                    tex_col = pygame.Surface((64, 1))
                    tex_col.fill((101, 84, 60))
                
                scaled_tex = pygame.transform.scale(tex_col, (64, 1))
                scaled_tex.fill((intensity, intensity, intensity), special_flags=pygame.BLEND_RGB_MULT)
                self.screen.blit(scaled_tex, (x, y))

        # 2. Raycasting
        start_a = self.player_angle - FOV / 2
        for ray in range(NUM_RAYS):
            angle = start_a + ray * DELTA_ANGLE
            sin_a, cos_a = math.sin(angle), math.cos(angle)
            for d in range(1, MAX_DEPTH, 2):
                tx, ty = self.player_x + d * cos_a, self.player_y + d * sin_a
                if self.map[int(ty/TILE_SIZE)][int(tx/TILE_SIZE)] == 1:
                    dist = d * math.cos(self.player_angle - angle)
                    self.depth_buffer[ray] = dist
                    wh = int(WALL_HEIGHT_MULTIPLIER / (dist + PARTICLE_EPSILON))
                    off = (ty % TILE_SIZE) if abs(cos_a) > abs(sin_a) else (tx % TILE_SIZE)
                    off_clamped = max(0, min(TILE_SIZE - 1, int(off) % TILE_SIZE))
                    col_s = pygame.transform.scale(self.wall_tex.subsurface(off_clamped, 0, 1, TILE_SIZE), (int(WIDTH/NUM_RAYS)+1, wh))
                    m = (max(0, min(255, 255 - (dist / FOG_DISTANCE_DIVISOR))) / 255) * t_mult
                    col_s.fill((m*255, m*255, m*255), special_flags=pygame.BLEND_RGB_MULT)
                    self.screen.blit(col_s, (ray * (WIDTH / NUM_RAYS), HEIGHT // 2 - wh // 2))
                    break
            else: self.depth_buffer[ray] = MAX_DEPTH

        self.draw_quest_item()
        self.draw_doors()  # Draw door indicators
        self.draw_torches()  # Draw torch indicators
        self.draw_weather()
        self.draw_hud()
        self.draw_minimap()  # Draw minimap with fog of war
        self.inventory.draw(self.screen)

    def draw_torches(self):
        """Draw torch markers in the world"""
        for torch in self.torches:
            dx, dy = torch["x"] - self.player_x, torch["y"] - self.player_y
            px = dx * math.cos(-self.player_angle) - dy * math.sin(-self.player_angle)
            py = dx * math.sin(-self.player_angle) + dy * math.cos(-self.player_angle)
            if px > 10:
                sx = (py / px) * (WIDTH / (2 * math.tan(FOV/2))) + (WIDTH / 2)
                if 0 <= sx < WIDTH:
                    ray_idx = int(sx / (WIDTH / NUM_RAYS))
                    if 0 <= ray_idx < NUM_RAYS and px < self.depth_buffer[ray_idx]:
                        # Draw torch as a flickering flame
                        size = max(3, int(100 / px))
                        flicker = int(20 * math.sin(pygame.time.get_ticks() / 100))
                        # Clamp color values to valid range (0-255)
                        flame_color = (
                            max(0, min(255, 255 - flicker)),
                            max(0, min(255, 150 - flicker//2)),
                            0
                        )
                        pygame.draw.circle(self.screen, flame_color, (int(sx), HEIGHT//2 - size//2), size)

    def draw_doors(self):
        """Draw door markers in the world"""
        for door in self.doors:
            dx, dy = door["x"] - self.player_x, door["y"] - self.player_y
            px = dx * math.cos(-self.player_angle) - dy * math.sin(-self.player_angle)
            py = dx * math.sin(-self.player_angle) + dy * math.cos(-self.player_angle)
            if px > 10:
                sx = (py / px) * (WIDTH / (2 * math.tan(FOV/2))) + (WIDTH / 2)
                if 0 <= sx < WIDTH:
                    ray_idx = int(sx / (WIDTH / NUM_RAYS))
                    if 0 <= ray_idx < NUM_RAYS and px < self.depth_buffer[ray_idx]:
                        # Draw door marker
                        size = max(5, int(300 / px))
                        pygame.draw.rect(self.screen, (255, 200, 0), (int(sx) - size//2, HEIGHT//2 - size, size, size*2), 3)
                        # Draw key required indicator
                        if "key_required" in door:
                            pygame.draw.circle(self.screen, (255, 0, 0), (int(sx), HEIGHT//2 - size - 10), 5)

    def draw_hud(self):
        """Draw health and mana bars"""
        bar_width = 200
        bar_height = 20
        bar_x = 20
        bar_y = 20
        
        # Health bar background
        pygame.draw.rect(self.screen, (30, 30, 30), (bar_x, bar_y, bar_width, bar_height))
        # Health bar
        health_width = int(bar_width * (self.health / self.max_health))
        health_color = (100, 255, 100) if self.health > 50 else (255, 150, 0) if self.health > 25 else (255, 50, 50)
        pygame.draw.rect(self.screen, health_color, (bar_x, bar_y, health_width, bar_height))
        pygame.draw.rect(self.screen, (150, 255, 150), (bar_x, bar_y, bar_width, bar_height), 2)
        
        # Health text
        font = pygame.font.SysFont("georgia", 16)
        health_text = font.render(f"HP: {self.health}/{self.max_health}", True, (255, 255, 255))
        self.screen.blit(health_text, (bar_x + 5, bar_y + 2))
        
        # Mana bar background
        bar_y += 30
        pygame.draw.rect(self.screen, (30, 30, 30), (bar_x, bar_y, bar_width, bar_height))
        # Mana bar
        mana_width = int(bar_width * (self.mana / self.max_mana))
        pygame.draw.rect(self.screen, (100, 100, 255), (bar_x, bar_y, mana_width, bar_height))
        pygame.draw.rect(self.screen, (150, 150, 255), (bar_x, bar_y, bar_width, bar_height), 2)
        
        # Mana text
        mana_text = font.render(f"Mana: {self.mana}/{self.max_mana}", True, (255, 255, 255))
        self.screen.blit(mana_text, (bar_x + 5, bar_y + 2))
        
        # Consume feedback message
        if self.consume_message_timer > 0:
            font_msg = pygame.font.SysFont("georgia", 20, bold=True)
            msg_surf = font_msg.render(self.consume_message, True, (100, 255, 100))
            msg_rect = msg_surf.get_rect(center=(WIDTH // 2, HEIGHT - 50))
            # Draw with shadow
            shadow = font_msg.render(self.consume_message, True, (0, 0, 0))
            self.screen.blit(shadow, (msg_rect.x + 2, msg_rect.y + 2))
            self.screen.blit(msg_surf, msg_rect)

    def draw_quest_item(self):
        if self.quest_completed: return
        dx, dy = self.quest_item_pos[0] - self.player_x, self.quest_item_pos[1] - self.player_y
        px = dx * math.cos(-self.player_angle) - dy * math.sin(-self.player_angle)
        py = dx * math.sin(-self.player_angle) + dy * math.cos(-self.player_angle)
        if px > PLAYER_SPEED * 2:
            sx = (py / px) * (WIDTH / (2 * math.tan(FOV/2))) + (WIDTH / 2)
            ray_idx = int(sx / (WIDTH / NUM_RAYS))
            if 0 <= sx < WIDTH and 0 <= ray_idx < NUM_RAYS and px < self.depth_buffer[ray_idx]:
                size = int(500 / px)
                pygame.draw.circle(self.screen, (255, 215, 0), (int(sx), HEIGHT//2 + 20), size)

    def draw_weather(self):
        if self.weather_type == 'none': return
        
        # Determine color and properties based on weather type
        if 'rain' in self.weather_type:
            color = RAIN_COLOR
            particle_height = 12 if 'heavy' in self.weather_type else 8
        elif self.weather_type == 'snow':
            color = SNOW_COLOR
            particle_height = 4
        elif 'sand' in self.weather_type:
            color = DUST_COLOR
            particle_height = 6
        else:
            return
        
        # Draw weather particles
        for p in self.particles:
            dx, dy = p['x'] - self.player_x, p['y'] - self.player_y
            px = dx * math.cos(-self.player_angle) - dy * math.sin(-self.player_angle)
            py = dx * math.sin(-self.player_angle) + dy * math.cos(-self.player_angle)
            if px > 2:
                # Apply wind effect to x position for sandstorms
                if 'sand' in self.weather_type:
                    wind_offset = p.get('wind_accel', 0) * 2
                else:
                    wind_offset = 0
                
                sx = (py / px) * (WIDTH / (2 * math.tan(FOV/2))) + (WIDTH / 2) + wind_offset
                idx = int(sx / (WIDTH / NUM_RAYS))
                if 0 <= sx < WIDTH and 0 <= idx < NUM_RAYS and px < self.depth_buffer[idx]:
                    sy = (HEIGHT // 2) + (p['z'] * (240 / px))
                    pygame.draw.rect(self.screen, color, (sx, sy, 4, particle_height))
        
        # Add visibility obscuring effect for sandstorms
        if 'sand' in self.weather_type:
            opacity = min(200, 50 + len(self.particles) // 3)  # More opaque with more particles
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(opacity)
            overlay.fill(DUST_COLOR)
            self.screen.blit(overlay, (0, 0))

    def run(self):
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT: return
                if e.type == pygame.KEYDOWN:
                    # Inventory controls
                    if self.inventory.visible:
                        self.inventory.handle_input(e.key)
                        if e.key == pygame.K_i:
                            self.inventory.toggle()
                    else:
                        if e.key == pygame.K_i: self.inventory.toggle()
                        # Door/Teleport interaction (F key)
                        if e.key == pygame.K_f: self.try_use_door()
            
            if not self.inventory.visible:
                k = pygame.key.get_pressed()
                # Rotation (arrow keys)
                if k[pygame.K_LEFT]: self.player_angle -= PLAYER_ROTATION_SPEED
                if k[pygame.K_RIGHT]: self.player_angle += PLAYER_ROTATION_SPEED
                
                # WASD movement
                if k[pygame.K_w]:  # Forward
                    nx, ny = self.player_x + math.cos(self.player_angle)*PLAYER_SPEED, self.player_y + math.sin(self.player_angle)*PLAYER_SPEED
                    if self.map[int(ny/TILE_SIZE)][int(nx/TILE_SIZE)] == 0: self.player_x, self.player_y = nx, ny
                if k[pygame.K_s]:  # Backward
                    nx, ny = self.player_x - math.cos(self.player_angle)*PLAYER_SPEED, self.player_y - math.sin(self.player_angle)*PLAYER_SPEED
                    if self.map[int(ny/TILE_SIZE)][int(nx/TILE_SIZE)] == 0: self.player_x, self.player_y = nx, ny
                if k[pygame.K_a]:  # Strafe left
                    nx, ny = self.player_x - math.cos(self.player_angle + math.pi/2)*PLAYER_SPEED, self.player_y - math.sin(self.player_angle + math.pi/2)*PLAYER_SPEED
                    if self.map[int(ny/TILE_SIZE)][int(nx/TILE_SIZE)] == 0: self.player_x, self.player_y = nx, ny
                if k[pygame.K_d]:  # Strafe right
                    nx, ny = self.player_x + math.cos(self.player_angle + math.pi/2)*PLAYER_SPEED, self.player_y + math.sin(self.player_angle + math.pi/2)*PLAYER_SPEED
                    if self.map[int(ny/TILE_SIZE)][int(nx/TILE_SIZE)] == 0: self.player_x, self.player_y = nx, ny
            
            self.update(); self.draw(); pygame.display.flip(); self.clock.tick(FPS)

def show_main_menu():
    """Display main menu to choose between game and editor"""
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    pygame.display.set_caption("RPGW3D - Main Menu")
    clock = pygame.time.Clock()
    font_large = pygame.font.SysFont("georgia", 40, bold=True)
    font_medium = pygame.font.SysFont("georgia", 24)
    font_small = pygame.font.SysFont("georgia", 16)
    
    choice = None
    
    while choice is None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    choice = "game"
                elif event.key == pygame.K_2:
                    choice = "editor"
                elif event.key == pygame.K_ESCAPE:
                    return None
        
        screen.fill((20, 15, 10))
        
        title = font_large.render("RPGW3D", True, (200, 180, 100))
        screen.blit(title, (400//2 - title.get_width()//2, 30))
        
        option1 = font_medium.render("1 - Play Game", True, (100, 255, 100))
        screen.blit(option1, (400//2 - option1.get_width()//2, 120))
        
        option2 = font_medium.render("2 - Map Editor", True, (100, 200, 255))
        screen.blit(option2, (400//2 - option2.get_width()//2, 170))
        
        hint = font_small.render("Press ESC to quit", True, (150, 150, 100))
        screen.blit(hint, (400//2 - hint.get_width()//2, 250))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
    return choice

if __name__ == "__main__":
    choice = show_main_menu()
    if choice == "game":
        Game().run()
    elif choice == "editor":
        MapEditor().run()
