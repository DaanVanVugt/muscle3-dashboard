import re
import signal
from datetime import datetime
from enum import Enum
from pathlib import Path

import param
from bokeh.core.serialization import Serializable, Serializer

_LOGPARSER = re.compile(
    r"""
    ^(?P<component>\S+)         # Source of log message: muscle_manager or remote component
    \ (?P<datetime>\S+\ \S+)    # Lazy way to capture the date + time
    \ (?P<loglevel>\S+)         # Log level: INFO / DEBUG / etc.
    \ +(?P<name>\S+):           # Python module for manager logs, or remote component name
    \s*(?P<message>.*)$         # Log message
    """,
    re.VERBOSE,
)


class ComponentStatus(Serializable, Enum):
    NOT_STARTED = "Not started"
    PLANNED = "Planned"
    INSTANTIATING = "Instantiating"
    REGISTERED = "Registered"
    DEREGISTERED = "Deregistered"
    FINISHED = "Finished"

    def to_serializable(self, serializer: Serializer) -> str:
        """Converts this object to a serializable representation."""
        return self.value


class ManagerLogAnalyzer(param.Parameterized):
    muscle_manager_version = param.String(default="unknown")
    """Version string of the muscle manager"""
    start_time = param.Date()
    """Time of the first log message"""
    last_update_time = param.Date()
    """Time of the most recent log message"""
    status = param.String()
    """Current status of the muscle manager"""

    lines_read = param.Integer(0)
    """Number of log lines read"""
    lines_parsed = param.Integer(0)
    """Number of log lines successfully parsed"""

    messages_per_level = param.Dict()
    """Number of parsed messages per log level"""
    components = param.Dict()

    def __init__(self, logfile: Path, components: list[str]) -> None:
        super().__init__()
        self._path: Path = logfile
        self.components: dict[str, Component] = {
            component: Component(
                component, status=ComponentStatus.NOT_STARTED, exit_code=""
            )
            for component in components
        }
        self._file = logfile.open("r")
        self._messages_per_level: dict[str, int] = {
            "DEBUG": 0,
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
            "unknown": 0,
        }
        self._lines_read = 0
        self._lines_parsed = 0

        self.update()

    def update(self) -> None:
        # Parse currently available log lines
        for line in self._file:
            self._lines_read += 1
            match = _LOGPARSER.match(line)
            if match is None:
                continue  # FIXME: notify user about this?
            self._lines_parsed += 1
            if self.start_time is None:
                self.start_time = datetime.fromisoformat(match.group("datetime"))
            self.last_update_time = datetime.fromisoformat(match.group("datetime"))

            if match.group("component") == "muscle_manager":
                # TODO: suppress any exceptions when parsing the message?
                self._parse_manager_log_message(match.group("message"))

            loglevel = match.group("loglevel")
            if loglevel not in self._messages_per_level:
                loglevel = "unknown"
            self._messages_per_level[loglevel] += 1

        # Update externally visible state
        self.param.update(
            lines_read=self._lines_read,
            lines_parsed=self._lines_parsed,
            messages_per_level=self._messages_per_level.copy(),
            components=self.components.copy(),
        )

    def _parse_manager_log_message(self, message: str) -> None:
        component = None
        exit_code = None
        status = None
        if message.startswith("Libmuscle version"):
            self.muscle_manager_version = message.split()[-1]
        elif message.startswith("Planned"):
            _, component, _ = message.split(maxsplit=2)
            status = ComponentStatus.PLANNED
        elif message.startswith("Instantiating"):
            _, component = message.split(maxsplit=1)
            status = ComponentStatus.INSTANTIATING
        elif message.startswith("Registered"):
            _, _, component = message.split(maxsplit=2)
            status = ComponentStatus.REGISTERED
        elif message.startswith("Deregistered"):
            _, _, component = message.split(maxsplit=2)
            status = ComponentStatus.DEREGISTERED
        elif any(word in message for word in ["finished", "quit", "crashed"]):
            if message.startswith("Instance"):
                _, component, _ = message.split(maxsplit=2)
                status = ComponentStatus.FINISHED
                if "crashed" in message:
                    exit_code = "crashed"
                else:
                    _, exit_code = message.rsplit(maxsplit=1)
            else:
                # The simulation finished
                self.status = message
                return
        else:
            # Continue to next message
            return
        # fill in components
        if component is not None and component not in self.components.keys():
            self.components[component] = Component(
                name=component, status=status, exit_code=exit_code
            )
        if exit_code is not None:
            self.components[component].exit_code = exit_code
        if status is not None:
            self.components[component].status = status

    def var_dict(self, var):
        my_dict = {
            name: getattr(self.components[name], var)
            for name in self.components.keys()
            if getattr(self.components[name], var)
        }
        return my_dict


class Component:
    def __init__(self, name, exit_code="", status=ComponentStatus.NOT_STARTED):
        self.name = name
        self.exit_code = exit_code
        self.status: ComponentStatus = status

    @property
    def exit_code_message(self):
        if is_int(self.exit_code) and int(self.exit_code) < 0:
            msg = f"{str(self.exit_code)}: {signal.strsignal(-1 * int(self.exit_code))}"
        else:
            msg = str(self.exit_code)
        return msg


def is_int(s: str):
    try:
        int(s)
        return True
    except ValueError:
        return False
