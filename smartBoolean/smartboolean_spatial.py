"""Conservative bounding-box lookup; exact geometry tests remain at the caller."""

def bounds(a, b, padding=0.):
    return tuple(min(a[k], b[k])-padding for k in range(3)) + tuple(max(a[k], b[k])+padding for k in range(3))


def overlaps(a, b):
    return not (a[3]<b[0] or b[3]<a[0] or a[4]<b[1] or b[4]<a[1] or a[5]<b[2] or b[5]<a[2])


class BoxIndex:
    def __init__(self, boxes):
        self.boxes = list(boxes)
        self.root = self._build(list(range(len(self.boxes)))) if self.boxes else None

    def _build(self, ids):
        box = tuple(min(self.boxes[i][k] for i in ids) for k in range(3)) + tuple(max(self.boxes[i][k] for i in ids) for k in range(3,6))
        if len(ids)<=8:return (box, ids, None, None)
        axis=max(range(3),key=lambda k:box[k+3]-box[k])
        ids.sort(key=lambda i:self.boxes[i][axis]+self.boxes[i][axis+3])
        mid=len(ids)//2
        return (box, None, self._build(ids[:mid]), self._build(ids[mid:]))

    def query(self, box):
        found=[];todo=[self.root] if self.root else []
        while todo:
            node=todo.pop()
            if not overlaps(node[0],box):continue
            if node[1] is not None:
                found.extend(i for i in node[1] if overlaps(self.boxes[i],box))
            else:todo.extend((node[2],node[3]))
        # Preserve original evaluation order, including equal-contact tie cases.
        found.sort()
        return found
