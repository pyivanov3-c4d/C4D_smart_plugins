"""Conservative broad-phase searches; exact geometric tests remain mandatory."""


def segment_pairs(segments, eps):
    """Original-order pairs whose XY boxes overlap within tolerance."""
    boxes=[(min(a[0],b[0]),max(a[0],b[0]),min(a[1],b[1]),max(a[1],b[1]),i)
           for i,(a,b) in enumerate(segments)]
    active=[]; pairs=[]
    for box in sorted(boxes):
        x0,x1,y0,y1,i=box
        active=[other for other in active if other[1]+eps>=x0]
        for other in active:
            if other[3]+eps<y0 or y1+eps<other[2]:continue
            j=other[4]
            pairs.append((min(i,j),max(i,j)))
        active.append(box)
    return sorted(pairs)
