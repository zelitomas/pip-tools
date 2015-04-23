import os
from contextlib import nested
from itertools import chain, cycle
from os.path import basename

from click import unstyle
from first import first

from .io import AtomicSaver
from .logging import log
from .utils import comment, format_requirement


class OutputWriter(object):
    def __init__(self, src_file, dry_run, header, annotate, default_index_url,
                 index_urls):
        self.src_file = src_file
        self.dry_run = dry_run
        self.header = header
        self.annotate = annotate
        self.default_index_url = default_index_url
        self.index_urls = index_urls

    @property
    def dst_file(self):
        base_name, _, _ = self.src_file.rpartition('.')
        return base_name + '.txt'

    def _sort_key(self, ireq):
        return (not ireq.editable, str(ireq.req).lower())

    def write_header(self):
        if self.header:
            yield comment('#')
            yield comment('# This file is autogenerated by pip-compile')
            yield comment('# Make changes in {}, then run this to update:'.format(basename(self.src_file)))
            yield comment('#')
            yield comment('#    pip-compile {}'.format(basename(self.src_file)))
            yield comment('#')

    def write_index_options(self):
        emitted = False
        option_values = chain(['--index-url'], cycle(['--extra-index-url']))
        for option, index_url in zip(option_values, self.index_urls):
            if index_url == self.default_index_url:
                continue
            yield '{} {}'.format(option, self.index_urls[0])
            emitted = True
        if emitted:
            yield ''  # extra line of whitespace

    def _iter_lines(self, results, reverse_dependencies, primary_packages):
        for line in self.write_header():
            yield line
        for line in self.write_index_options():
            yield line

        UNSAFE_PACKAGES = {'setuptools', 'distribute', 'pip'}
        unsafe_packages = {r for r in results if r.name in UNSAFE_PACKAGES}
        packages = {r for r in results if r.name not in UNSAFE_PACKAGES}

        packages = sorted(packages, key=self._sort_key)
        unsafe_packages = sorted(unsafe_packages, key=self._sort_key)

        for ireq in packages:
            line = self._format_requirement(ireq, reverse_dependencies, primary_packages)
            yield line

        if unsafe_packages:
            yield ''
            yield comment('# The following packages are commented out because they are ')
            yield comment('# considered to be unsafe in a requirements file:')

            for ireq in unsafe_packages:
                line = self._format_requirement(ireq, reverse_dependencies, primary_packages)
                yield comment('# ' + line)

    def write(self, results, reverse_dependencies, primary_packages):
        managers = []
        if not self.dry_run:
            managers.append(AtomicSaver(self.dst_file))
        with nested(*managers) as files:
            f = first(files)
            for line in self._iter_lines(results, reverse_dependencies, primary_packages):
                log.info(line)
                if f:
                    f.write(unstyle(line))
                    f.write(os.linesep)

    def _format_requirement(self, ireq, reverse_dependencies, primary_packages):
        line = format_requirement(ireq)
        if not self.annotate or ireq.name in primary_packages:
            return line

        # Annotate what packages this package is required by
        required_by = reverse_dependencies.get(ireq.name, [])
        if required_by:
            line = line.ljust(24)
            annotation = ', '.join(sorted(required_by))
            line += comment('  # via ' + annotation)
        return line
