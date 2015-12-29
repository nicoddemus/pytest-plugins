from __future__ import absolute_import

import pytest
import os
import cProfile
import pstats
import pipes
import six
import errno
from hashlib import md5


LARGE_FILENAME_HASH_LEN = 8


def clean_filename(s):
    forbidden_chars = set('/?<>\:*|"')
    return "".join(
        c if c not in forbidden_chars and ord(c) < 127 else '_'
        for c in six.text_type(s)
    )


class Profiling(object):
    """Profiling plugin for pytest."""
    svg = False
    svg_name = None
    profs = []
    combined = None

    def __init__(self, svg):
        self.svg = svg
        self.profs = []

    def pytest_sessionstart(self, session):  # @UnusedVariable
        try:
            os.makedirs("prof")
        except OSError:
            pass

    def pytest_sessionfinish(self, session, exitstatus):  # @UnusedVariable
        if self.profs:
            combined = pstats.Stats(self.profs[0])
            for prof in self.profs[1:]:
                combined.add(prof)
            self.combined = os.path.join("prof", "combined.prof")
            combined.dump_stats(self.combined)
            if self.svg:
                self.svg_name = os.path.join("prof", "combined.svg")
                t = pipes.Template()
                t.append("gprof2dot -f pstats $IN", "f-")
                t.append("dot -Tsvg -o $OUT", "-f")
                t.copy(self.combined, self.svg_name)

    def pytest_terminal_summary(self, terminalreporter):
        if self.combined:
            terminalreporter.write("Profiling (from {prof}):\n".format(prof=self.combined))
            pstats.Stats(self.combined, stream=terminalreporter).strip_dirs().sort_stats('cumulative').print_stats(20)
        if self.svg_name:
            terminalreporter.write("SVG profile in {svg}.\n".format(svg=self.svg_name))

    @pytest.mark.tryfirst
    def pytest_pyfunc_call(self, __multicall__, pyfuncitem):
        """Hook into pytest_pyfunc_call; marked as a tryfirst hook so that we
        can call everyone else inside `cProfile.runctx`.
        """
        prof = cProfile.Profile()
        prof.runctx("fn()", globals(), dict(fn=__multicall__.execute))
        prof_filename = os.path.join("prof", clean_filename(pyfuncitem.name) + ".prof")
        try:
            prof.dump_stats(prof_filename)
        except EnvironmentError as err:
            if err.errno != errno.ENAMETOOLONG:
                raise

            if len(pyfuncitem.name) < LARGE_FILENAME_HASH_LEN:
                raise

            hash_str = md5(pyfuncitem.name).hexdigest()[:LARGE_FILENAME_HASH_LEN]
            prof_filename = os.path.join("prof", hash_str + ".prof")
            prof.dump_stats(prof_filename)
        self.profs.append(prof_filename)


def pytest_addoption(parser):
    """pytest_addoption hook for profiling plugin"""
    group = parser.getgroup('Profiling')
    group.addoption("--profile", action="store_true",
                    help="generate profiling information")
    group.addoption("--profile-svg", action="store_true",
                    help="generate profiling graph (using gprof2dot and dot -Tsvg)")


def pytest_configure(config):
    """pytest_configure hook for profiling plugin"""
    profile_enable = any(config.getvalue(x) for x in ('profile', 'profile_svg'))
    if profile_enable:
        config.pluginmanager.register(Profiling(config.getvalue('profile_svg')))
