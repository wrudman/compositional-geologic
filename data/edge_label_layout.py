"""Keep edge names near their edges without colliding with other edge names."""
import math


def edge_label_position(draw, start, end, label, font, preferred, stroke_width=2):
    placed = getattr(draw, '_edge_label_boxes', {})
    if label in placed:
        return placed[label][0]
    dx, dy = end[0]-start[0], end[1]-start[1]
    length = max(math.hypot(dx, dy), 1)
    nx, ny = -dy/length, dx/length
    box = draw.textbbox((0, 0), label, font=font, anchor='mm', stroke_width=stroke_width)
    margin = max(4, (box[3]-box[1])*.25)
    offset = max(abs(nx)*(box[2]-box[0])/2 + abs(ny)*(box[3]-box[1])/2 + margin, 12)
    candidates = [preferred]
    for t in (.5, .35, .65, .2, .8):
        for side in (1, -1, 1.5, -1.5, 2, -2):
            candidates.append((start[0]+t*dx+side*offset*nx,
                               start[1]+t*dy+side*offset*ny))
    width, height = draw._image.size
    def bounds(p):return (p[0]+box[0],p[1]+box[1],p[0]+box[2],p[1]+box[3])
    def score(p):
        b=bounds(p)
        overlap=sum(max(0,min(b[2]+margin,q[2])-max(b[0]-margin,q[0])) *
                    max(0,min(b[3]+margin,q[3])-max(b[1]-margin,q[1]))
                    for _,q in placed.values())
        overflow=max(0,-b[0])+max(0,-b[1])+max(0,b[2]-width)+max(0,b[3]-height)
        return overlap*10000+overflow*10000+math.dist(p,preferred)
    chosen=min(candidates,key=score)
    placed[label]=(chosen,bounds(chosen));draw._edge_label_boxes=placed
    return chosen
