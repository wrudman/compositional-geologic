import numpy as np
# return items a,b,c such that b.value >= a.value*ratio and c.value >= b.value*ratio
# all such triples <a,b,c> are equiprobable.

def RandomSeparatedTriples(list,values,ratio):
    values,list = zip(*sorted(zip(values,list)))
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

#[1,2,3], [1,2,4], [1,2,4] [1,2,5], [1,2,8], [1,3,5], [1,3,8], [1,4,8], [1,4,8], [1,5,8]
#[2,3,5], [2,3,8], [2,4,8], [2,4,8], [2,5,8]
#[3,5,8]
# [1, 2, 3, 4, 4, 5, 8], 1.5
# [6,   5,  2   1,   1,   1, 0]
# [16, 10, 5, 4, 3, 2, 1, 0]
# [10, 5, 1, 0, 0, 0, 0]
# f,a,g,c,e,b,d
def TestRST(nTries):
    dict = {}
    for i in range(nTries):
        Found,a,b,c = RandomSeparatedTriples(['g','b','e','f','a','d','c'],[3,5,4,1,2,8,4],1.5)
        key = a+b+c
        if key in dict.keys():
            dict[key] += 1
        else:
            dict[key]=1
    return dict

