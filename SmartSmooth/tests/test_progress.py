import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.main=True
        gui=types.SimpleNamespace(**{name:(lambda *a,n=name:self.calls.append((n,a))) for name in
            ('StatusClear','StatusSetText','StatusSetBar','StatusSetSpin')})
        fake=types.SimpleNamespace(gui=gui,threading=types.SimpleNamespace(GeIsMainThread=lambda:self.main),
            SpecialEventAdd=lambda *a:self.calls.append(('event',a)))
        path=Path(__file__).resolve().parents[1]/'smartsmooth_progress.py'
        spec=importlib.util.spec_from_file_location('isolated_progress',path)
        self.p=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,c4d=fake):spec.loader.exec_module(self.p)

    def test_worker_coalesces_and_never_calls_ui(self):
        self.main=False;job=self.p.Progress()
        for i in range(100):job.stage(str(i),i)
        self.assertEqual([n for n,a in self.calls],['event'])
        self.main=True;self.p.flush()
        self.assertEqual(self.calls[-1],('StatusSetBar',(99,)))
        job.close();self.assertEqual(self.calls[-1][0],'StatusClear')

    def test_completion_before_event_leaves_idle_status_untouched(self):
        self.main=False;job=self.p.Progress();job.stage('brief');job.close()
        self.main=True;self.p.flush()
        self.assertEqual([n for n,a in self.calls],['event'])

    def test_nested_jobs_restore_outer_status(self):
        a=self.p.Progress();a.stage('outer')
        b=self.p.Progress();b.stage('inner',50);b.close()
        self.assertIs(self.p.current(),a)
        self.assertEqual(self.calls[-2],('StatusSetText',('SmartSmooth: outer',)))
        self.assertFalse(any(n=='StatusClear' for n,args in self.calls))
        a.close();self.assertEqual(self.calls[-1][0],'StatusClear')

    def test_cancellation_closes_status(self):
        thread=types.SimpleNamespace(TestBreak=lambda:False)
        job=self.p.Progress(thread);job.stage('working')
        thread.TestBreak=lambda:True
        with self.assertRaises(self.p.Cancelled):
            try:job.count(1,10,'checking')
            finally:job.close()
        self.assertFalse(self.p._jobs)
        self.assertEqual(self.calls[-1][0],'StatusClear')

    def test_idle_flush_never_touches_status(self):
        for i in range(10):self.p.flush()
        self.assertEqual(self.calls,[])
