import subprocess

def call(cmd, **kwargs):
    """ Runs cmd in a shell, returns its return code. """
    print("EXECUTING:", cmd)
    cp = subprocess.run(cmd, shell=True, **kwargs)
    return cp.returncode

def ccall(cmd,  **kwargs):
    """ Runs cmd in a shell, returns its return code. Raises exception on error """
    return call(cmd, check = True, **kwargs)
    

import os

def get_tests(root = os.getcwd()):
    """ List of all available system tests """
    return[s[5:] for s in os.listdir(root) if s.startswith("Test_")]


from contextlib import contextmanager

@contextmanager
def chdir(path):
    """ Changes and restores the current working directory. """
    oldpwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(oldpwd)


def get_diff_files(dcmp):
    """ Given a filecmp.dircmp object, recursively compares files.
    Returns three lists: files that differ and files that exist only in left/right directory. """
    diff_files = dcmp.diff_files
    left_only = dcmp.left_only
    right_only = dcmp.right_only

    for sub_dcmp in dcmp.subdirs.values():
        ret = get_diff_files(sub_dcmp)
        diff_files += ret[0]
        left_only += ret[1]
        right_only += ret[2]

    return diff_files, left_only, right_only
