"""Place the complete text halo beside a line, preferring the frame interior."""
import math


def line_label_position(draw, start, end, text, font, stroke_width=3, preferred=None):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    nx, ny = (-dy / length, dx / length) if length else (0, -1)
    left, top, right, bottom = draw.textbbox((0, 0), str(text), font=font,
                                           anchor='mm', stroke_width=stroke_width)
    half_w, half_h = (right-left)/2, (bottom-top)/2
    cx, cy = (left+right)/2, (top+bottom)/2
    gap = 8
    offset = abs(nx)*half_w + abs(ny)*half_h + gap
    target = preferred or ((start[0]+end[0])/2, (start[1]+end[1])/2)
    candidates = []
    for fraction in (None, .5, .35, .65, .2, .8, -100/max(length, 1), 1+100/max(length, 1)):
        px, py = target if fraction is None else (start[0]+fraction*dx, start[1]+fraction*dy)
        for side in (1, -1, 2, -2, 3, -3, 4, -4):
            x, y = px+side*nx*offset-cx, py+side*ny*offset-cy
            box = (x+left, y+top, x+right, y+bottom)
            overflow = sum((max(0, 104-box[0]), max(0, 104-box[1]),
                            max(0, box[2]-896), max(0, box[3]-896)))
            candidates.append((overflow*10000 + math.hypot(px-target[0],py-target[1]) + abs(side)*offset, (x,y)))
    return min(candidates, key=lambda c:c[0])[1]
