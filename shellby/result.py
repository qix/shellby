from dataclasses import dataclass
from typing import Union


@dataclass
class ShellResult:
    returncode: int
    stdout: Union[str, bytes]
    stderr: Union[str, bytes]

    @property
    def code(self):
        return self.returncode