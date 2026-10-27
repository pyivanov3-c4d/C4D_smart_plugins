import c4d,os
p=os.path.join(os.path.dirname(__file__),'Mask-experiment.c4d')
doc=c4d.documents.LoadDocument(p,c4d.SCENEFILTER_OBJECTS,None)
n=doc.GetFirstObject().GetDown().GetNext();s=n.GetRealSpline();h=c4d.utils.SplineHelp();h.InitSplineWith(n,c4d.SPLINEHELPFLAGS_RETAINLINEOBJECT)
l=h.GetLineObject();data=l.GetTag(c4d.Tline).GetAllHighlevelData();start=0
for segment in range(h.GetSegmentCount()):
 count=h.GetVertexCount(segment)
 error=max((s.GetSplinePoint(data[i]['t'],segment)-l.GetPoint(i)).GetLength() for i in range(start,start+count))
 print('SEGMENT',segment,'ERROR',error,flush=True)
 assert error<1e-5
 start+=count
print('PASSED',flush=True)
