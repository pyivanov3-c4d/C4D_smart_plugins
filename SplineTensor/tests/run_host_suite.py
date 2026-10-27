import os,runpy
root=os.path.dirname(__file__)
runpy.run_path(os.path.join(root,'c4d_generated_inputs.py'),run_name='__main__')
runpy.run_path(os.path.join(root,'c4d_smoke.py'),run_name='__main__')
