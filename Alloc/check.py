#!/usr/bin/env python2
from __future__ import print_function

import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

TEST_BIN = "./test"
LIB = "libmyalloc.so"

# Only used on server, to ensure an unchanged Makefile
CLEAN_MAKEFILE = "/framework/Makefile"


# Global state - set by one (or more) test and used later to subtract points
compiler_warnings = None

# C files added by student - we need these during compilation
additional_sources = ""

# Start using calloc if we determine it's supported
use_calloc = False


class TestError(Exception):
    pass


def colored(val, color=None, bold=False, underline=False, blink=False,
        hilight=False):
    C_RESET = '\033[0m'
    C_BOLD = '\033[1m'
    C_UNDERLINE = '\033[4m'
    C_BLINK = '\033[5m'
    C_HILIGHT = '\033[7m'
    C_GRAY = '\033[90m'
    C_RED = '\033[91m'
    C_GREEN = '\033[92m'
    C_YELLOW = '\033[93m'
    C_BLUE = '\033[94m'
    C_PINK = '\033[95m'
    C_CYAN = '\033[96m'

    codes = ''
    if bold: codes += C_BOLD
    if underline: codes += C_UNDERLINE
    if blink: codes += C_BLINK
    if hilight: codes += C_HILIGHT
    if color:
        codes += {'gray': C_GRAY,
                  'red': C_RED,
                  'green': C_GREEN,
                  'yellow': C_YELLOW,
                  'blue': C_BLUE,
                  'pink': C_PINK,
                  'cyan': C_CYAN}[color]

    return '%s%s%s' % (codes, val, C_RESET)


# Test case definition
class Test():
    def __init__(self, name, func, stop_group_on_fail=False):
        self.name, self.func = name, func
        self.stop_group_on_fail = stop_group_on_fail


# Collection of testcases worth n points (i.e. one item in the grading scheme)
class TestGroup():
    def __init__(self, name, points, *tests, **kwargs):
        self.name = name
        self.points = float(points)
        self.tests = tests
        self.stop_if_fail = kwargs.get("stop_if_fail", False)

    def run(self):
        succeeded = 0
        for test in self.tests:
            print('\t' + test.name, end=': ')
            try:
                test.func()
            except TestError as e:
                print(colored("FAIL", color='red'))
                print(e.args[0])
                if self.stop_if_fail or test.stop_group_on_fail:
                    break
            else:
                print(colored("OK", color='green'))
                succeeded += 1
        return succeeded


def test_groups(groups, writer=None, force_fail=False):
    points = 0.0
    for group in groups:
        if force_fail:
            if writer: writer.write(group.name + ": 0\n")
            continue

        print(colored(group.name, color='blue', bold=True))
        succeeded = group.run()

        perc = ((1. * succeeded) / len(group.tests))
        if group.points < 0:
            perc = 1 - perc
        grouppoints = round(group.points * perc, 2)
        if group.points > 0:
            print(" Passed %d/%d tests, %.2f/%.2f points" % (succeeded,
                len(group.tests), grouppoints, group.points))
        else:
            if perc > 0:
                print(" Failed, subtracting %.2f points" % abs(grouppoints))
        if writer: writer.write(group.name + ": " + str(grouppoints) + "\n")
        points += grouppoints
        if group.stop_if_fail and succeeded != len(group.tests):
            force_fail = True
    return points


def run(writer=None):
    tests = [
        TestGroup("Valid submission", 1.0,
            Test("Make", check_compile),
            stop_if_fail=True),
        TestGroup("Malloc", 1.0,
            Test("Simple", alloc("malloc-simple")),
            Test("Zero size", alloc("malloc-zero")),
            Test("Orders", alloc("malloc-orders")),
            Test("Random", alloc("malloc-random")),
            stop_if_fail=True),
        TestGroup("Calloc", 0.5,
            Test("Calloc", test_calloc),
        ),
        TestGroup("Free", 2.0,
            Test("Reuse", alloc("free-reuse"), stop_group_on_fail=True),
            Test("Random", alloc("free-random")),
            Test("Split free chunks", alloc("free-reuse-split")),
            Test("Merge free chunks", alloc("free-reuse-merge")),
        ),
        TestGroup("Realloc", 1.0,
            Test("Basic", alloc("realloc")),
            Test("Zero", alloc("realloc-zero")),
            Test("Optimized", alloc("realloc-opt")),
        ),
        TestGroup("Batching", 1.0,
            Test("Brk can contain more allocs", alloc("batch")),
        ),
        TestGroup("Fragmentation", 2.0,
            Test("Amortized overhead <=16", alloc("fragmentation-16"),
                stop_group_on_fail=True),
            Test("Amortized overhead <=8", alloc("fragmentation-8")),
        ),
        TestGroup("Locality", 0.5,
            Test("Temporal locality", alloc("locality")),
        ),
        TestGroup("Unmap", 1.0,
            Test("Give back memory", alloc("unmap")),
        ),
        TestGroup("Alternative design", 1.0,
            Test("Out-of-band metadata", alloc("out-of-band-metadata")),
        ),
        TestGroup("System malloc", 2.0,
            Test("malloc", alloc("system-malloc"), stop_group_on_fail=True),
            Test("preload ls", test_preload("ls -al /")),
            Test("preload python", test_preload("python -c 'print(\"hello, world\\n\")'")),
            Test("preload grep", test_preload("grep -E '^ro+t' /etc/passwd")),
        ),
        TestGroup("Dynamic heap size", -2.0,
            Test("128K heap", alloc("heap-fill", ["-m", "%d" % (128 * 1024)])),
            Test("256M heap",
                alloc("heap-fill", ["-m", "%d" % (256 * 1024 * 1024)])),
        ),
        TestGroup("Compiler warnings", -1,
            Test("No warnings", check_warnings),
        ),
    ]

    points = test_groups(tests, writer)
    totalpoints = sum([g.points for g in tests if g.points > 0])

    print()
    print("Executed all tests, got %.2f/%.2f points in total" % (points,
        totalpoints))


def check_cmd(cmd, add_env=None):
    args = shlex.split(cmd)
    env = os.environ.copy()
    if add_env:
        env.update(add_env)
    p = subprocess.Popen(args, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    stdout, stderr = p.communicate()

    if p.returncode:
        raise TestError("Command returned non-zero value.\n" +
                "Command: %s\nReturn code: %d\nstdout: %s\nstderr: %s" %
                (cmd, p.returncode, stdout, stderr))
    return stdout, stderr


def run_alloc_test_bin(test, args=None):
    args = args or []

    args = [TEST_BIN] + args + [test]

    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode < 0:
        signame = dict((getattr(signal, n), n) \
            for n in dir(signal) if n.startswith('SIG') and '_' not in n)
        sig = -proc.returncode
        err += "%s (%d)" % (signame.get(sig, "Unknown"), sig)
    return proc.returncode, out, err


def alloc(test, args=None):
    args = args or []
    def alloc_inner():
        if use_calloc:
            args.append("-c")
        ret, out, err = run_alloc_test_bin(test, args)
        if ret:
            testname = '"%s"' % test
            if args:
                testname += ' (with %s)' % ' '.join(args)
            raise TestError("Test %s exited with error: %s" % (testname, err))
    return alloc_inner

def test_calloc():
    global use_calloc
    alloc("calloc")()
    use_calloc = True

def test_preload(cmd):
    env = {"LD_PRELOAD": "%s/%s" % (os.getcwd(), LIB)}
    def _inner():
        check_cmd(cmd, env)
    return _inner

def check_warnings():
    if compiler_warnings is not None:
        raise TestError("Got compiler warnings:\n%s" % compiler_warnings)


def check_compile():
    check_cmd("make clean ADDITIONAL_SOURCES=\"%s\"" %
              additional_sources)

    out, err = check_cmd("make ADDITIONAL_SOURCES=\"%s\"" %
                         additional_sources)
    err = '\n'.join([l for l in err.split("\n") if not l.startswith("make:")])
    if "warning" in err:
        global compiler_warnings
        compiler_warnings = err

    check_cmd("%s -h" % TEST_BIN)


def do_additional_params(lst, name, suffix=''):
    for f in lst:
        if not f.endswith(suffix):
            raise TestError("File does not end with %s in %s: '%s'" %
                    (suffix, name, f))
        if '"' in f:
            raise TestError("No quotes allowed in %s: '%s'" % (name, f))
        if '/' in f:
            raise TestError("No slashes allowed in %s: '%s'" % (name, f))
        if '$' in f:
            raise TestError("No $ allowed in %s: '%s'" % (name, f))
        if f.startswith('-'):
            raise TestError("No flags allowed in %s: '%s'" % (name, f))


def fix_makefiles():
    with open('Makefile', 'r') as f:
        addsrc, addhdr = [], []
        for l in f:
            l = l.strip()
            if l.startswith("ADDITIONAL_SOURCES = "):
                addsrc = filter(bool, l.split(' ')[2:])
            if l.startswith("ADDITIONAL_HEADERS = "):
                addhdr = filter(bool, l.split(' ')[2:])
    do_additional_params(addsrc, "ADDITIONAL_SOURCES", ".c")
    do_additional_params(addhdr, "ADDITIONAL_HEADERS", ".h")

    global additional_sources
    additional_sources = ' '.join(addsrc)

    # On the server we overwrite the submitted makefile with a clean one. For
    # local tests this will fail, which is fine.
    try:
        shutil.copyfile(CLEAN_MAKEFILE, 'Makefile')
    except IOError:
        pass



if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]) or '.')
    try:
        fix_makefiles()
        run(open(sys.argv[1], 'w') if len(sys.argv) > 1 else None)
    except Exception as e:
        print("\n\nTester got exception: %s" % str(e))
