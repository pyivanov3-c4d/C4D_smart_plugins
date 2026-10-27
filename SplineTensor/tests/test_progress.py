import importlib.util, pathlib, sys, types, unittest
from unittest.mock import patch

class ProgressTests(unittest.TestCase):
 def setUp(self):
  self.calls=[];self.main=True
  gui=types.SimpleNamespace(**{name:(lambda *args,n=name:self.calls.append((n,args))) for name in ('StatusClear','StatusSetText','StatusSetSpin','StatusSetBar')})
  self.c4d=types.SimpleNamespace(gui=gui,threading=types.SimpleNamespace(GeIsMainThread=lambda:self.main),SpecialEventAdd=lambda *a:self.calls.append(('event',a)),plugins=types.SimpleNamespace(MessageData=object))
  spec=importlib.util.spec_from_file_location('progress_test_module',pathlib.Path(__file__).parents[1]/'st_progress.py')
  self.module=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,{'c4d':self.c4d}):spec.loader.exec_module(self.module)
 def test_worker_only_posts_events(self):
  self.main=False;p=self.module.Progress();p.stage(30,'Building',True)
  self.assertEqual([c[0] for c in self.calls],['event'])
  self.main=True;self.module.flush()
  self.assertIn(('StatusSetSpin',()),self.calls)
  p.close();self.assertEqual(self.calls[-1][0],'StatusClear')
 def test_two_jobs_do_not_clear_each_other(self):
  a=self.module.Progress();b=self.module.Progress();a.stage(2,'Read');b.stage(85,'UV')
  a.close();self.assertFalse(any(c[0]=='StatusClear' for c in self.calls))
  b.close();self.assertEqual(self.calls[-1][0],'StatusClear')
 def test_idle_does_not_touch_status_bar(self):
  self.module.flush();self.assertEqual(self.calls,[])
 def test_cleanup_after_failure(self):
  p=self.module.Progress()
  try:
   p.stage(15,'Union');raise ValueError('invalid geometry')
  except ValueError:pass
  finally:p.close()
  self.assertFalse(self.module._jobs);self.assertEqual(self.calls[-1][0],'StatusClear')

if __name__=='__main__':unittest.main()
