import numpy as np
import Graph
import platform
import os
from PIL import Image, ImageColor, ImageDraw, ImageFont

def InitColors(alpha=153): 
    global colors, white, black
    black = (0, 0, 0, 255)
    white = (255, 255, 255, 255)
    def with_alpha(rgb): return rgb + (alpha,)
    light_blue = (135, 206, 250) 

    colors = [
        white, 
        with_alpha((255, 0, 0)),     # Red
        with_alpha(light_blue),      # Light Blue
        with_alpha((0, 255, 0)),     # Green
        with_alpha((255, 255, 0)),   # Yellow
        with_alpha((210, 105, 30)),  # Chocolate/Brown
        with_alpha((255, 182, 193))  # Light Pink
    ]

def GetSystemFont(size):
    """ Helper to load Arial or a similar bold font on Windows/Mac """
    system = platform.system()
    if system == "Windows":
        # Standard Windows font names
        fonts_to_try = ["arialbd.ttf", "arial.ttf", "calibrib.ttf"]
    elif system == "Darwin": # Mac
        # Standard Mac font paths
        fonts_to_try = [
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc"
        ]
    else:
        fonts_to_try = ["DejaVuSans-Bold.ttf", "FreeSans-Bold.ttf"]

    for font in fonts_to_try:
        try:
            return ImageFont.truetype(font, size)
        except OSError:
            continue
    
    # Final fallback if no TTF files are found
    return ImageFont.load_default()

def DrawGraph(faces, maxX, maxY):
    global colors, white, black
    InitColors(alpha=153) 
    
    line_width_interior = 4
    line_width_exterior = 8
    font_bold = GetSystemFont(80)
    font_small = GetSystemFont(45)

    # --- NEW: STEP 1 - PRE-CALCULATE AND LOCK DATA ---
    # We do the "random" part exactly ONCE here.
    drawing_instructions = []
    for face in faces:
        if face.bounded:
            lp, d = Graph.LetterPointFace(face)  # Randomness happens HERE
            coords = V2P(lp)
            chosen_font = font_bold if d > 0.06 else font_small
            polygon_vvs = FaceVertex2P(face)
            
            drawing_instructions.append({
                'face': face,
                'vvs': polygon_vvs,
                'coords': coords,
                'font': chosen_font
            })

    # --- STEP 2 - DRAW USING THE LOCKED DATA ---
    for mode in ["color", "bw"]:
        img = Image.new("RGBA", (int(200 + 800 * maxX), int(200 + 800 * maxY)), white)
        draw = ImageDraw.Draw(img)

        for instr in drawing_instructions:
            face = instr['face']
            fill_color = white if mode == "bw" else colors[face.color]
            
            # Draw polygon using the pre-calculated vertices
            draw.polygon(instr['vvs'], fill=fill_color, outline=black, width=line_width_interior)
            
            # Draw text using the PRE-CALCULATED coordinates and font
            draw.text(instr['coords'], face.letter, fill=black, font=instr['font'], anchor="mm")

        # Draw the heavy Outer Frame
        p_bottom_left = V2P(Graph.Vector(0, 0))
        p_top_right = V2P(Graph.Vector(maxX, maxY))
        outer_box = [p_bottom_left[0], p_top_right[1], p_top_right[0], p_bottom_left[1]]
        draw.rectangle(outer_box, outline=black, width=line_width_exterior)

        filename = f"Attempt1_{mode}.png"
        img.save(filename)
        print(f"Saved: {filename}")

def FaceVertex2P(face):
    return tuple(V2P(v.p) for v in face.vertices)

def V2P(v):
    # Mapping normalized coordinates (0-1) to pixel space (100-900)
    return (int(np.floor(100 + 800 * v.x)), int(np.floor(900 - 800 * v.y)))



'''DrawAllFaces is used in visual_tools.py
    The excat coodrinates of labels of the regions are returned, to prevent potential overlapping
'''

def DrawAllFaces(res_map, draw, manager=None, label_cache=None):
    """
    Synchronized with DrawGraph styling.
    Added label_cache to prevent stochastic drift (shaking labels).
    """
    InitColors(alpha=153)
    black = (0, 0, 0, 255)
    
    # Matching DrawGraph font sizes
    font_bold = GetSystemFont(80)
    font_small = GetSystemFont(45)

    for face in res_map.faces:
        if face.bounded:
            # 1. Draw the geometry
            vvs = FaceVertex2P(face)
            fill_color = colors[face.color]
            draw.polygon(vvs, fill=fill_color, outline=black, width=4)
            
            # 2. Handle the Label Position
            # We check the cache first to ensure we use the SAME point across different layers
            if label_cache and hasattr(face, '_cache_idx') and face._cache_idx in label_cache:
                lp, d = label_cache[face._cache_idx]
            else:
                lp, d = Graph.LetterPointFace(face)
            
            coords = V2P(lp)
            
            # 3. Draw the Text
            # Threshold 0.06 determines if the face is large enough for the bold font
            chosen_font = font_bold if d > 0.06 else font_small
            draw.text(coords, face.letter, fill=black, font=chosen_font, anchor="mm")
            
            # 4. Collision Avoidance
            if manager is not None:
                # Reserve area so other labels (vertices/angles) don't overlap the face letter
                manager.reserve(coords[0], coords[1], width=40, height=40)
            
    # 5. Draw heavy outer frame (width = 8)
    p_bl = V2P(Graph.Vector(0, 0))    # Result: (100, 900)
    p_tr = V2P(Graph.Vector(1.0, 1.0)) # Result: (900, 100)
    
    line_w = 8
    # We "shrink" the rectangle coordinates by half the line width 
    # to ensure the entire 8-pixel stroke is contained within the math bounds.
    offset = line_w / 2
    adjusted_box = [
        p_bl[0] - offset, # Left (Move left)
        p_tr[1] - offset, # Top (Move up)
        p_tr[0] + offset, # Right (Move right)
        p_bl[1] + offset  # Bottom (Move down)
    ]
    
    draw.rectangle(adjusted_box, outline=black, width=line_w)


def DrawSingleFace(face, draw, manager=None, label_cache=None):
    """
    Renders a single Face object (original or union).
    Standardized with DrawAllFaces logic.
    """
    if not face.bounded:
        return

    InitColors(alpha=153)
    black = (0, 0, 0, 255)
    font_bold = GetSystemFont(80)
    font_small = GetSystemFont(45)

    # 1. Draw the geometry
    vvs = FaceVertex2P(face)
    # If the face has a color attribute use it, otherwise default to white (0)
    color_idx = getattr(face, 'color', 0) 
    fill_color = colors[color_idx]
    
    # Draw the base polygon
    draw.polygon(vvs, fill=fill_color, outline=black, width=4)

    # 2. Determine Label Position
    if label_cache and hasattr(face, '_cache_idx') and face._cache_idx in label_cache:
        lp, d = label_cache[face._cache_idx]
    else:
        lp, d = Graph.LetterPointFace(face)
        if label_cache is not None and hasattr(face, '_cache_idx'):
            label_cache[face._cache_idx] = (lp, d)

    coords = V2P(lp)

    # 3. Draw the Label Text
    chosen_font = font_bold if d > 0.06 else font_small
    draw.text(coords, face.letter, fill=black, font=chosen_font, anchor="mm")

    # 4. Reserve space in the collision manager
    if manager is not None:
        manager.reserve(coords[0], coords[1], width=40, height=40)
