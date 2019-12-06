from math import tan, radians, atan2

def smooth(path, size=2):
    smoothed = []
    smoothed.append(path[0])
    for i in range(size, len(path)-size):
        xx = [x for (x,y) in path[i-size:i+size]]
        yy = [y for (x,y) in path[i-size:i+size]]
        x = sum(xx)/(len(xx)*1.0)
        y = sum(yy)/(len(yy)*1.0)
        smoothed.append((x,y))
    smoothed.append(path[-1])
    return smoothed

def simplify(path, tolerance = 2):
    previous = None
    previousfactor = None
    nodes_to_delete = []
    tolerance = tan(radians(tolerance))
    for i, node in enumerate(path):
        if not previous: 
            previous = node
            continue
        factor = atan2((node[0]-previous[0]),(node[1]-previous[1]))
        #factor = ((node[0]-previous[0]),(node[1]-previous[1]))
        if not previousfactor:
            previousfactor = factor
            continue
        if abs(factor-previousfactor) < tolerance: nodes_to_delete.append(i-1)
        #print factor, previousfactor, abs(factor-previousfactor), tolerance
        previous = node
        previousfactor = factor

    for i in nodes_to_delete[::-1]:
        path.pop(i)
    return path
