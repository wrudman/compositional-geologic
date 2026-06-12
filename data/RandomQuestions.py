import Questions
import numpy as np
import Graph
import TestQuestions
import random

global numTries
global map
global debug
global failureOutput
numTries = 10
debug = True
failureOutput = ("", "", False, 0)

def randomSetup(seed):
    global map
    TestQuestions.randomSetup(seed)
    map = TestQuestions.map

def GenRandomBenmarks(nmaps,nquestions,nfaces,x,y):
    for i in range(nmaps):    
        map=BuildRandomMap.BuildRandomMaps(nfaces,x,y,2*i)
        if GraphCheck.GraphCheck(map.vertices,map.edges,map.faces):
            qaPairs = randomQuestions(nquestions,2*i+1)
            RecordQAPairs(qaPairs)
        else:
            RecordMapBug(map)
    
def displayRandomQuestion(key,seed):
    map = TestQuestions.map
    np.random.seed(seed)
    for i in range(50):
        question, answerText, answer, quality = tryrandomQuestion(key)
        if quality > 0:
            print("Question " + str(key) +":", question)
            print("Answer:", answerText)
            return

def randomQuestions(nquestions,seed):
    np.random.seed(seed)
    count = 0
    qaPairs = []
    nums = np.random.choice(29,29,replace=False)
    for q in nums:
        qaPair = triesRandomQuestion(q+1)
        (question, answer) = qaPair
        if question != False:
            print("Question " + str(q+1) + ":", question)
            print("Answer:", answer)
            qaPairs += [qaPair]
            count += 1
            if count >= nquestions:
                return qaPairs

def triesRandomQuestion(key):
    global numTries
    qaPairs = []
    qualities = []
    n = numTries
    if key in [3,5,6,7,8,17,23]:
        n=1
    for i in range(n):
        question, answerText, answer, quality = tryrandomQuestion(key)
        if quality > 0:
            qaPairs += [(question,answerText)]
            qualities += [quality]
    if len(qaPairs) == 0: 
        return (False,False)
    s = sum(qualities)
    prob = []
    for q in qualities:
        prob += [q/s]
    i = np.random.choice(len(qaPairs),p=prob)
    return qaPairs[i]
   

def tryrandomQuestion(key):
     match key:
         case 1:
             return randomQuestion1()
         case 2:
             return randomQuestion2()
         case 3:
             return randomQuestion3()
         case 4:
             return randomQuestion4()
         case 5:
             return randomQuestion5()
         case 6:
             return randomQuestion6()
         case 7:
             return randomQuestion7()
         case 8:
             return randomQuestion8()
         case 9:
             return randomQuestion9()
         case 10:
             return randomQuestion10()
         case 11:
             return randomQuestion11()
         case 12:
             return randomQuestion12()
         case 13:
             return randomQuestion13()
         case 14:
             return randomQuestion14()
         case 15:
             return randomQuestion15()
         case 16:
             return randomQuestion16()
         case 17:
             return randomQuestion17()
         case 18:
             return randomQuestion18()
         case 19:
             return randomQuestion19()
         case 20:
             return randomQuestion20()
         case 21:
             return randomQuestion21()
         case 22:
             return randomQuestion22()
         case 23:
             return randomQuestion23()
         case 24:
             return randomQuestion24()
         case 25:
             return randomQuestion25()
         case 26:
             return randomQuestion26()
         case 27:
             return randomQuestion27()
         case 28:
             return randomQuestion28()
         case 29:
             return randomQuestion29()


def randomQuestion1():
    global map
    return Questions.Question1(np.random.choice(map.faces[1:]))

#                          RANDOM QUESTION 29
def randomQuestion2():
    global map
    # Pick two distinct random faces to compare their sides
    fa, fb = np.random.choice(map.faces[1:], size=2, replace=False)
    return Questions.Question2(fa, fb)

def randomQuestion3():
    global map
    return Questions.Question3(map)

def randomQuestion4():
    global map
    face = np.random.choice(map.faces[1:])
    v = np.random.choice(face.vertices[1:])
    direction = np.random.choice([True,False])
    return Questions.Question4(face,v,direction,randomCodes(1))

def randomQuestion5():
    global map
    return Questions.Question5(map)

def randomQuestion6():
    global map
    return Questions.Question6(map)

def randomQuestion7():
    global map
    return Questions.Question7(map)

def randomQuestion8():
    global map
    k = np.random.choice([3,4,5,6],p=[1/6,1/3,1/3,1/6])
    return Questions.Question8(map,k)

def randomQuestion9():
    global map
    return Questions.Question9(np.random.choice(map.faces[1:]))

def randomQuestion10():
    global map
    vp = np.random.choice(map.vertices)
    distances = []
    alternates = []
    for v in map.vertices:
        if v != vp:
            alternates += [v]
            distances += [Graph.pointDist(vp.p,v.p)]
    found, va, vb, vc = RandomSeparatedTriples(alternates,distances,1.5)
    if not found:
        return failureOutput
    [va,vb,vc] = np.random.permutation([va,vb,vc])
    codeP,codeA,codeB,codeC = randomCodes(4)
    return Questions.Question10(vp,va,vb,vc,codeP,codeA,codeB,codeC)

def randomQuestion11():
    global map
    face = np.random.choice(map.faces[1:])
    codes = randomCodes(len(face.edges))
    return Questions.Question11(face,codes)

def randomQuestion12():
    global map
    face = np.random.choice(map.faces[1:])
    i = np.random.choice(len(face.trueVertices)-2)
    va = face.trueVertices[i]
    vb = face.trueVertices[i+1]
    if map.faces[0] in va.faces and map.faces[0] in vb.faces:
        if i == 0:
           i = len(face.trueVertices)-2
        vb = va
        va = face.trueVertices[i-1]
    return Questions.Question12(face.trueVertices[i],face.trueVertices[i+1],
                                randomCodes(1),map) 

def randomQuestion13():
    global map
    v = np.random.choice(map.vertices[1:])
    return Questions.Question13(v,randomCodes(1))

def randomQuestion14():
    global map
    while True:
          e = np.random.choice(map.edges)
          fa = e.leftFace
          fb = e.reverse.leftFace
          if fa.bounded and fb.bounded:
              return Questions.Question14(e.leftFace,e.reverse.leftFace)

def randomQuestion15():
    global map
    while True:
        e = np.random.choice(map.edges)
        if e.leftFace.bounded and e.reverse.leftFace.bounded:
            return Questions.Question15(e.leftFace,e.reverse.leftFace,map)

def randomQuestion16():
    global map
    nfaces =  np.random.choice([3,4], p=[2/3,1/3])
    facesLeft = map.faces[1:]
    facepairs = []
    for i in range(nfaces):
        fa = np.random.choice(facesLeft)
        facesLeft.remove(fa)
        options = []
        pair = np.random.choice([False,True],p=[2/3,1/3])
        if pair:
            for e in fa.edges:
                fx = e.reverse.leftFace
                if fx in facesLeft and fx not in options:
                    options += [e.reverse.leftFace]
            if len(options) > 0:
                fb = np.random.choice(options)
                facesLeft.remove(fb)
                facepairs += [[fa,fb]]
        if (not pair) or (len(options) == 0):
            facepairs += [fa]
    return Questions.Question16(facepairs,map)

# ==========================================
#                   RANDOM QUESTION 17
# ==========================================
def randomQuestion17():
    """
    Finds pairs of adjacent regions and balances the Yes/No answers.
    """
    global map
    yes_pairs = []
    no_pairs = []

    # Iterate through faces to find adjacent pairs
    # We start from 1 to skip the 'Outside' face
    for i in range(1, len(map.faces)):
        fa = map.faces[i]
        for e in fa.edges:
            fb = e.reverse.leftFace
            # Ensure fb is a valid internal face and we haven't processed this pair
            if fb and fb.num > fa.num and fb.bounded:
                # Test the union
                res = Questions.Question17(fa, fb)
                if res[0] is not None:
                    # Categorize into Yes or No pools
                    if res[2]: # is_convex is True
                        yes_pairs.append((fa, fb))
                    else:
                        no_pairs.append((fa, fb))

    # Balance selection
    if yes_pairs and no_pairs:
        # 50% chance for a Yes answer, 50% for No
        pool = random.choice([yes_pairs, no_pairs])
        fa, fb = random.choice(pool)
    elif yes_pairs or no_pairs:
        # If one pool is empty, take whatever is available
        all_pairs = yes_pairs + no_pairs
        fa, fb = random.choice(all_pairs)
    else:
        return None, None, False, 0.0

    return Questions.Question17(fa, fb)

def randomQuestion18():
    global map
    va,vb = np.random.choice(map.vertices,size=2,replace=False)
    codeA,codeB = randomCodes(2)
    return Questions.Question18(va,vb,codeA,codeB,map)

#                          RANDOM QUESTION 19
def randomQuestion19():
    """
    Randomly selects a vertex and a cardinal direction to trace a ray.
    """
    global map
    # Pick a vertex that is not on the very edge if possible, 
    # but Q19Check will handle the boundary logic anyway.
    v = np.random.choice(map.vertices)
    
    # Randomly choose one of the 4 cardinal directions:
    # 0: Right, 1: Up, 2: Left, 3: Down
    direction = np.random.choice([0, 1, 2, 3])
    
    code = randomCodes(1)
    
    # Question19 internal logic (Q19ComputeRobust) will now use the 0.06 guard
    return Questions.Question19(v, direction, code, map)

def randomQuestion20():
    global map
    va,vb,vc = np.random.choice(map.vertices,size=3,replace=False)
    direction = np.random.choice([0,1])
    codeA, codeB, codeC = randomCodes(3)
    return Questions.Question20(va,vb,vc,direction,codeA,codeB,codeC)

def randomQuestion21():
    global map
    va,vb,vc = np.random.choice(map.vertices,size=3,replace=False)
    codeA, codeB, codeC = randomCodes(3)
    return Questions.Question21(va,vb,vc,codeA,codeB,codeC)

def randomQuestion22():
    global map
    va,vb,vc,vd = np.random.choice(map.vertices,size=4,replace=False)
    codeA, codeB, codeC, codeD = randomCodes(4)
    return Questions.Question22(va,vb,vc,vd,codeA,codeB,codeC,codeD)


def randomQuestion23():
    global map
    dir = np.random.choice(2)
    return Questions.Question23(dir,map)

def randomQuestion24():
    global map, numTries
    for i in range(numTries):
        fa,fb,fc = np.random.choice(map.faces[1:],size=3,replace=False)
        question, answerText, answer, quality = Questions.Question24(fa,fb,fc)
        if quality > 0:
            return question, answerText, answer, quality   
        


#                          RANDOM QUESTION 25
def randomQuestion25():
    global map
    # 1. Filter out the 'Outside' face (Face 0/@)
    valid_faces = [f for f in map.faces if f.num > 0 and f.bounded]
    
    if not valid_faces:
        return None, None, False, 0.0
        
    bounds = getattr(map, 'bounds', (1.0, 1.0))
    
    # 2. Sort faces into 'Yes' and 'No' pools
    yes_pool = []
    no_pool = []
    
    for f in valid_faces:
        # We run the logic check silently to categorize
        _, _, touches, _ = Questions.Question25(f, bounds)
        if touches:
            yes_pool.append(f)
        else:
            no_pool.append(f)
            
    # 3. 50/50 Selection Logic
    # If both pools have candidates, flip a coin
    if yes_pool and no_pool:
        if random.random() > 0.5:
            selected_face = random.choice(yes_pool)
        else:
            selected_face = random.choice(no_pool)
    elif yes_pool:
        selected_face = random.choice(yes_pool)
    elif no_pool:
        selected_face = random.choice(no_pool)
    else:
        return None, None, False, 0.0

    return Questions.Question25(selected_face, bounds)

#                          RANDOM QUESTION 26
def randomQuestion26():
    global map
    return Questions.Question26(map)

# ==========================================
#                   RANDOM QUESTION 27
# ==========================================
def randomQuestion27():
    """
    Global wrapper for Question 27. 
    Note: This question doesn't need a random face input because 
    it evaluates the whole map to find the 'max'.
    """
    global map
    # We only pass 'map'. 
    # Passing 'face' here would cause the "2 given but 1 expected" error.
    return Questions.Question27(map)

#                          RANDOM QUESTION 28
def randomQuestion28():
    global map
    # Pick two distinct random faces
    fa, fb = np.random.choice(map.faces[1:], size=2, replace=False)
    return Questions.Question28(fa, fb)

#                          RANDOM QUESTION 29
def randomQuestion29():
    """
    Randomly selects two distinct bounded faces to find the maximum 
    number of intermediate regions between them.
    """
    global map
    # Ensure we have at least 2 bounded faces
    bounded_faces = [f for f in map.faces[1:] if f.bounded]
    if len(bounded_faces) < 2:
        return failureOutput
        
    fa, fb = np.random.choice(bounded_faces, size=2, replace=False)
    
    # Calls the new sampling-based Question 29
    return Questions.Question29(fa, fb, map)


def randomCodes(k):
    if k==1:
        return np.random.choice(2520)
    else:
        return np.random.choice(2520,size=k)

# return items a,b,c such that b.value >= a.value*ratio and c.value >= b.value*ratio
# all such triples <a,b,c> are equiprobable.

def RandomSeparatedTriples(list,values,ratio):      
#    values,list = zip(*sorted(zip(values,list))) Keeps giving erratic bugs
    values, list = Questions.parallelSort(values,list)
    n = len(list)
    num1step, num2step = CountTriples(values,ratio)
    if num2step[0] == 0:
        return False,False,False,False
    t2 = sum(num2step)
    prob = [0]*n
    for i in range(n):
        prob[i] = num2step[i]/t2
    first = np.random.choice(n,p=prob)
    for i in range(n):
        if values[i] < values[first]*ratio:
            num1step[i]=0
    t1 = sum(num1step)
    prob = [0]*n
    for i in range(n):
        prob[i] = num1step[i]/t1
    second = np.random.choice(n,p=prob)
    for i in range(second+1,n):
        if values[i] >= values[second]*ratio:
           istart = i
           break
    prob = [0]*(istart) + [1/(n-istart)]*(n-istart)
    third = np.random.choice(n,p=prob) 
    return True,list[first],list[second],list[third]   
        
    

def CountTriples(values,ratio):
    n = len(values)
    i=0
    j=1
    num1step=[0]*n    # num1step[i] The number of values j such that value[j] >= ratio*value[i]
    while (j < n):
        if values[j] >= ratio*values[i]:
            num1step[i] = n-j
            i += 1
        else:
            j += 1
    sum = [0]*n
    for i in range(2,n):
        sum[n-i] = sum[n+1-i]+num1step[n-i]
    i=0
    j=1
    num2step=[0]*n    # num2step[i] = The number of pairs j,k such that i,j,k is a valid triple
    while (j < n):
        if values[j] >= ratio*values[i]:
            num2step[i] = sum[j]
            i += 1
        else:
            j += 1
    return num1step, num2step


#generate problems by a specific complexity tier
def get_questions_by_tier(mymap, tier, count):

    global map
    map = mymap

    buckets = {
        "easy": [1, 8, 9, 13, 26, 27],
        "medium": [2, 3, 5, 6, 7, 10, 11, 14, 15, 16, 20, 23, 24, 25, 28],
        "hard": [4, 12, 17, 18, 19, 21, 22, 29] 
    }
    
    selected_questions = []
    pool = buckets[tier].copy()
    np.random.shuffle(pool)
    
    while len(selected_questions) < count and len(pool) > 0:
        key = pool.pop()
        # triesRandomQuestion is your existing function that runs the logic
        qaPair = triesRandomQuestion(key) 
        if qaPair[0] != False:
            selected_questions.append(qaPair)
            
    return selected_questions