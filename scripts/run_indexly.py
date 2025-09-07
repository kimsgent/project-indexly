import os, shlex, sys, runpy

args = os.environ.get("INDEXLY_ARGS", "")
sys.argv = ["indexly"] + shlex.split(args)
runpy.run_module("indexly", run_name="__main__")
