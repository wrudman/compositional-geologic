def Question24(map):
    question = "Which region is furthest from the center of the overall rectangle, "     
    question += "where the distance from a point p to region X is defined "
    question += "as the distance from p to the closest point in X?"
    maxFace = False
    maxD = 0
    secondD = 0
    (x,y) = map.bounds
    pc = Graph.Vector(x/2,y/2)
    for f in map.faces[1:]:
        d = Graph.distPointFromFaceCutoff(pc,f,secondD)
        if d > maxD:
           secondD = maxD
           secondFace = maxFace
           sl = ml
           maxD = d
           maxFace = f
        elif d > secondD:
            secondD = d
            secondFace = f
    quality = maxD/secondD
    if quality < 1.3:
        return failureOutput
    else:
        return question, maxFace.letter, maxFace, quality
