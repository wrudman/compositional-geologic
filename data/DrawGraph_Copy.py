import numpy as np
import Graph
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
        with_alpha((180, 180, 180))  # Light Gray
    ]

def DrawGraph(faces, maxX, maxY):
    global colors, white, black
    InitColors(alpha=153) 
    
    # --- DEFINE WIDTHS HERE ---
    line_width_interior = 4
    line_width_exterior = 8
    
    for mode in ["color", "bw"]:
        img = Image.new("RGBA", (int(200 + 800 * maxX), int(200 + 800 * maxY)), white)
        draw = ImageDraw.Draw(img)
        
        try:
            font_bold = ImageFont.truetype("Arial Bold.ttf", 50)
            font_small = ImageFont.truetype("Arial Bold.ttf", 25)
        except:
            font_bold = ImageFont.load_default()
            font_small = ImageFont.load_default()

        for face in faces:  
            if face.bounded:
                vvs = FaceVertex2P(face)
                fill_color = white if mode == "bw" else colors[face.color]
                
                # Use the interior width defined above
                draw.polygon(vvs, fill=fill_color, outline=black, width=line_width_interior)
                
                lp, d = Graph.LetterPointFace(face)
                (x, y) = V2P(lp)
                if d > 0.03:
                    draw.text((x, y), face.letter, fill=black, font=font_bold, anchor="mm")
                else:
                    draw.text((x, y), face.letter, fill=black, font=font_small, anchor="mm")

        # Draw the heavy Outer Frame
        p_bottom_left = V2P(Graph.Vector(0, 0))
        p_top_right = V2P(Graph.Vector(maxX, maxY))
        outer_box = [p_bottom_left[0], p_top_right[1], p_top_right[0], p_bottom_left[1]]
        
        # Now line_width_exterior is defined!
        draw.rectangle(outer_box, outline=black, width=line_width_exterior)

        filename = f"Attempt1_{mode}.png"
        img.save(filename)
        print(f"Saved: {filename}")

def FaceVertex2P(face):
    return tuple(V2P(v.p) for v in face.vertices)

def V2P(v):
    return (int(np.floor(100 + 800 * v.x)), int(np.floor(900 - 800 * v.y)))