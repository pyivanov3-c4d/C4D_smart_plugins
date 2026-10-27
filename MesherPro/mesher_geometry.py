"""Profile and topology helpers, independent of Cinema 4D."""
import math


def circle(radius, segments):
    segments = max(3, min(200, int(segments)))
    return [(radius * math.cos(i * math.tau / segments),
             radius * math.sin(i * math.tau / segments)) for i in range(segments)]


def rectangle(width, height, radius, segments):
    x, y = max(0.001, width) / 2, max(0.001, height) / 2
    radius = max(0.0, min(radius, x, y))
    if radius < 1e-9:
        return [(x, y), (-x, y), (-x, -y), (x, -y)]
    segments = max(1, min(200, int(segments)))
    points = []
    for cx, cy, start in ((x-radius, y-radius, 0),
                          (-x+radius, y-radius, math.pi/2),
                          (-x+radius, -y+radius, math.pi),
                          (x-radius, -y+radius, 3*math.pi/2)):
        for j in range(segments + 1):
            angle = start + math.pi/2 * j/segments
            p = (cx + radius*math.cos(angle), cy + radius*math.sin(angle))
            if not points or math.dist(p, points[-1]) > 1e-9:
                points.append(p)
    if math.dist(points[0], points[-1]) < 1e-9:
        points.pop()
    return points


def sides(rings, count, closed=False, base=0):
    result = []
    for j in range(rings if closed else rings-1):
        a, b = base+j*count, base+((j+1) % rings)*count
        for i in range(count):
            k = (i+1) % count
            result.append((a+i, a+k, b+k, b+i))
    return result
