import datetime
import os
from pathlib import Path

import param


class BaseLogAnalyzer(param.Parameterized):
    new_lines = param.List()
    """New lines to be added"""

    def __init__(self, log_file: Path) -> None:
        super().__init__()
        self._name = log_file.parent.name
        self._path: Path = log_file
        self._file = log_file.open("r")
        self.update()

    def update(self) -> None:
        """Parse new lines of log file and update parsed information"""
        # Update externally visible state
        log_lines = []
        for line in self._file:
            log_lines.append(line)

        self.param.update(new_lines=self.new_lines + log_lines)

    def pop_new_lines(self):
        """Get new lines from log file and reset self.new_lines"""
        popped_lines, self.new_lines = self.new_lines, []
        return popped_lines

    def file_last_updated(self) -> datetime.datetime:
        """Get last time file was modified"""
        return datetime.datetime.fromtimestamp(os.path.getmtime(self._file.name))
