"""Planar UVs shared by the base and every relief surface."""
from st_geometry import sub, cross, dot, unit, GeometryError


def planar_uvs(base, points):
    origin=base[0]
    normal=unit(tuple(sum(cross(sub(base[i-1],origin),sub(p,origin))[k]
                          for i,p in enumerate(base)) for k in range(3)))
    if normal[max(range(3),key=lambda k:abs(normal[k]))]<0:
        normal=tuple(-x for x in normal)
    u=unit(sub(base[1],origin))
    v=unit(cross(normal,u))
    def project(p):
        d=sub(p,origin)
        return dot(d,u),dot(d,v)
    boundary=[project(p) for p in base]
    low=[min(p[k] for p in boundary) for k in (0,1)]
    extent=[max(p[k] for p in boundary)-low[k] for k in (0,1)]
    if min(extent)<=0:
        raise GeometryError('Base has no usable UV area.')
    return [tuple(max(0.,min(1.,(q[k]-low[k])/extent[k])) for k in (0,1))+(0.,)
            for q in map(project,points)]
