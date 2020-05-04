import asyncio
import getpass
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union
from asyncio import (
    shield,
    sleep,
    wait_for,
)
from io import BytesIO

from .ansi import (
    green,
    white,
    red,
)
from .result import ShellResult

PIPE = object()

BOLD_CHECKMARK = "\u2714"
BOLD_CROSS = "\u2718"


class ShellException(Exception):
    pass


def quote(value: Union[str, Path]) -> str:
    if isinstance(value, Path):
        value = str(value)
    return shlex.quote(value)


def join_command(args: List[Union[str, Path]]):
    return " ".join([quote(arg) for arg in args])


class Command:
    def __init__(self, command, *, user=None, directory=None):
        if type(command) in (list, tuple):
            command = join_command(command)

        self.directory = directory
        self.user = user
        self.string = command

        self.full = command
        if directory:
            self.full = "cd %s && (%s)" % (quote(directory), self.full)
        self.full = ["bash", "-c", self.full]
        if user is not None:
            self.full = ["sudo", "--user=%s" % user, "--login"] + self.full

        self.full_string = " ".join([quote(arg) for arg in self.full])


class OutputHandler:
    def __init__(
        self, name: str, command, prefix=True, capture=True, display=True, quiet=False
    ):
        self.command = command
        self.name = name
        self.user = command.user
        self.is_current_user = self.user == getpass.getuser()

        self.capture = capture
        self.display = display
        self.prefix = prefix
        self.quiet = quiet

    def open(self):
        if self.quiet:
            return
        self.print(
            white(self.command.string), symbol="#" if self.user == "root" else "$",
        )

    async def _read_encoded(self, stream):
        if stream is None:
            return None
        data = await stream.read()
        return data.decode("utf-8")

    async def collect(self, stdout_stream, stderr_stream):
        if not self.display:
            return await asyncio.gather(
                self._read_encoded(stdout_stream), self._read_encoded(stderr_stream)
            )

        return await asyncio.gather(
            self._tail_stream(">", stdout_stream),
            self._tail_stream(">", stderr_stream),
        )

    def close(self, return_code):
        if self.quiet:
            return
        symbol = white(
            "[" + (green(BOLD_CHECKMARK) if return_code == 0 else red(BOLD_CROSS)) + "]"
        )

        if return_code == 0:
            self.print("", symbol=symbol)
        else:
            self.print("exit with %d" % return_code)

    def exception(self, exc):
        self.print(red("[ERR!]", bold=True) + " " + str(exc))

    def print(self, string, symbol=":"):
        print(
            "%s%s %s" % (self.name if self.name else "", symbol, string),
            file=sys.stderr,
        )

    async def _tail_stream(self, symbol, stream):
        if stream is None:
            return None

        # Don't write blank lines at the end
        line = True
        captured = []
        empty_lines = 0

        while line:
            line_promise = stream.readline()
            line_data = await line_promise

            # @TODO: give warnings if no data is coming in
            # while True:
            #   try:
            #     line_data = await wait_for(shield(line_promise), 15)
            #     break
            #   except asyncio.TimeoutError:
            #     sys.stderr.write(prefix + red('no output after 15s'))

            line = line_data.decode("utf-8")
            if self.capture:
                captured.append(line)
            if not line.strip():
                empty_lines += 1
            else:
                for index in range(empty_lines):
                    self.print("", symbol=symbol)
                self.print(line.rstrip(), symbol=symbol)
                empty_lines = 0
        return "".join(captured) if self.capture else None


async def bash_async(
    command,
    *,
    output=None,
    name: Optional[str] = None,
    tty=None,
    user=None,
    stdin=None,
    cwd=None
):
    assert type(stdin) in (type(None), bytes, str), "restrictions for now"

    command = Command(command)
    if output is None:
        output = OutputHandler(command=command, name=name)

    if type(stdin) is str:
        stdin = stdin.encode("utf-8")

    output.open()
    proc = await asyncio.create_subprocess_shell(
        command.full_string,
        stdin=subprocess.PIPE if stdin else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
    )

    collect_promise = output.collect(proc.stdout, proc.stderr)

    if stdin:
        proc.stdin.write(stdin)
        await proc.stdin.drain()
        proc.stdin.close()

    (stdout, stderr) = await collect_promise
    await proc.wait()
    output.close(proc.returncode)

    return ShellResult(proc.returncode, stdout, stderr)


def bash(command: Union[str, List[str]], **kw):
    return asyncio.run(bash_async(command, **kw))
