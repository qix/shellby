from dataclasses import dataclass
from typing import Union


@dataclass
class ShellResult:
    code: int
    stdout: Union[str, bytes]
    stderr: Union[str, bytes]
