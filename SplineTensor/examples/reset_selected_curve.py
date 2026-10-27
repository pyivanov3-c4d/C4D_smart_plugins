"""Run in Script Manager after restart to reset selected SplineTensor curves."""
import c4d

def main():
    doc = c4d.documents.GetActiveDocument()
    selected = [o for o in doc.GetActiveObjects(0) if o.GetType() == 1069998]
    if not selected:
        c4d.gui.MessageDialog('Select one or more SplineTensor generators first.')
        return
    fresh = c4d.BaseObject(1069998)
    doc.StartUndo()
    try:
        for obj in selected:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE,obj)
            obj[1002] = fresh[1002]
            obj.Message(c4d.MSG_UPDATE)
    finally:
        doc.EndUndo()
    c4d.EventAdd()

if __name__ == '__main__':
    main()
