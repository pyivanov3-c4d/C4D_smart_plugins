import c4d,os
root=os.path.dirname(os.path.dirname(__file__))
doc=c4d.documents.LoadDocument(os.path.join(root,'tests','Outline-repro.c4d'),c4d.SCENEFILTER_OBJECTS,None)
child=doc.GetFirstObject().GetDown().GetNext()
clone=child.GetClone(); temp=c4d.documents.BaseDocument();temp.InsertObject(clone)
result=c4d.utils.SendModelingCommand(command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,list=[clone],doc=temp)
print('RESULT',result,flush=True)
def dump(n,d=0):
 while n:
  print(' '*d,n.GetName(),n.GetType(),'ml',n.GetMl(),'real',n.GetRealSpline(),flush=True)
  if isinstance(n,c4d.SplineObject):print('segments',n.GetSegmentCount(),[n.GetSegment(i) for i in range(n.GetSegmentCount())],flush=True)
  if n.GetDown():dump(n.GetDown(),d+1)
  n=n.GetNext()
for n in result or []:dump(n)
