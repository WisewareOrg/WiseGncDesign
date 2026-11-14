"""The ground: a Basilisk module that runs a scenario's procedure against a flight software link.

The procedure is an `async def` driven on simulated time by the module's own loop, with no event
loop and no wall clock: each `await` yields, and each tick resumes the coroutine until it waits
again. The module also records every telemetry write the link reports, with the flight software's
time tag, and every command with its response, so one recorder serves every host.
"""

from collections.abc import Callable, Coroutine, Generator
from pathlib import Path
from typing import Any

import numpy as np
from Basilisk.architecture import sysModel

from gnc_cdh.link import Link

__all__ = ["CommandFailed", "Ground"]

_NANOSECONDS_PER_SECOND = 1e9


class CommandFailed(Exception):
    """A command the flight software answered with anything but `OK`.

    Attributes:
        name: `<instance>.<command>`.
        response: the response's name in the dictionary's `Fw.CmdResponse`.
        reason: why the flight software refused it, when it said, else `None`.
    """

    name: str
    response: str
    reason: str | None

    def __init__(self, name: str, response: str, reason: str | None = None) -> None:
        """Holds the command, its response and the reason given.

        Args:
            name: `<instance>.<command>`.
            response: the response's name.
            reason: why the flight software refused it, when it said.
        """
        super().__init__(f"{name} was answered {response}" + (f": {reason}" if reason else ""))
        self.name, self.response, self.reason = name, response, reason


class _Tick:
    """What a procedure awaits to resume at the next tick.

    Attributes:
        until: what the procedure waits for, in words, such as `t = 60.0 s`.
    """

    until: str

    def __init__(self, until: str) -> None:
        """Holds what the procedure waits for.

        Args:
            until: what the procedure waits for, in words.
        """
        self.until = until

    def __await__(self) -> Generator["_Tick", None, None]:
        """Yields once, to the ground's loop.

        Yields:
            _Tick: itself.
        """
        yield self


class Ground(sysModel.SysModel):
    """Runs a scenario's procedure against a flight software link, and records what crosses it.

    The simulation runs the module every `period_s`, a whole multiple of the flight software's
    period, after the flight software at each instant. Once the procedure returns, the module
    calls `stop` and is not run again; the flight goes on, and `telemetry_datasets` takes every
    write the link still holds.

    Attributes:
        period_s: s, the period of the task the simulation runs this module in.
        failure: the procedure's exception, kept whole, else `None`.
        command_log: one entry per command sent: `t_s`, `name`, `args`, `context`, `response`
            (the response's name, `None` until answered), `response_t_s` and `reason` (why the
            flight software refused it, when it said, else `None`).
    """

    period_s: float
    failure: BaseException | None
    command_log: list[dict[str, Any]]

    def __init__(
        self,
        procedure: Callable[["Ground"], Coroutine[Any, Any, None]],
        link: Link,
        truth: Callable[[], dict[str, np.ndarray]],
        stop: Callable[[], None],
        *,
        period_s: float | None = None,
    ) -> None:
        """Holds the procedure, the link, the stand-in for tracking and what stops the module.

        Args:
            procedure: the scenario's `async def`, called with this ground when the run starts.
            link: the flight software host.
            truth: reads the vehicle's true state now, the stand-in for tracking.
            stop: stops the simulation running this module, called once the procedure returns.
            period_s: s, the module's period; the flight software's when `None`.

        Raises:
            ValueError: naming both periods, when `period_s` is not a whole multiple of the flight
                software's.
        """
        super().__init__()
        self.period_s = link.period_s if period_s is None else period_s
        ground_ns = round(self.period_s * _NANOSECONDS_PER_SECOND)
        fsw_ns = round(link.period_s * _NANOSECONDS_PER_SECOND)
        if ground_ns < fsw_ns or ground_ns % fsw_ns:
            raise ValueError(
                f"the ground's period {self.period_s} s is not a whole multiple of the flight"
                f" software's {link.period_s} s"
            )
        self._procedure, self._link, self._truth, self._stop = procedure, link, truth, stop
        self._coroutine: Coroutine[Any, Any, None] | None = None
        self._now_ns = 0
        self._context = 0
        self._answers: dict[int, tuple[int, str | None]] = {}
        self._waiting = _Tick("its first tick")
        self._writes: list[tuple[int, int, Any]] = []
        self._latest: dict[int, Any] = {}
        self.failure = None
        self.command_log = []

    @property
    def now_s(self) -> float:
        """s, the simulation time of the tick being run."""
        return self._now_ns / _NANOSECONDS_PER_SECOND

    async def sleep(self, duration_s: float) -> None:
        """Waits until the first tick at or after `duration_s` from now.

        Args:
            duration_s: s, how long to wait.
        """
        wake_ns = self._now_ns + round(duration_s * _NANOSECONDS_PER_SECOND)
        while self._now_ns < wake_ns:
            await _Tick(f"t = {wake_ns / _NANOSECONDS_PER_SECOND} s")

    async def until(self, condition: Callable[[], bool], *, timeout_s: float) -> None:
        """Waits until `condition` holds, checking now and then at each tick.

        A `TimeoutError` names the condition by its file and line, and the time when `condition`
        still fails at the first tick at or after `timeout_s` from now.

        Args:
            condition: reads the ground's view of the flight software.
            timeout_s: s, how long to wait.
        """
        code = condition.__code__
        named = f"at {Path(code.co_filename).name}:{code.co_firstlineno}"
        await self._until(condition, timeout_s, f"the condition {named} holds")

    async def _until(self, condition: Callable[[], bool], timeout_s: float, what: str) -> None:
        """Waits until `condition` holds, checking now and then at each tick.

        Args:
            condition: reads the ground's view of the flight software.
            timeout_s: s, how long to wait.
            what: what `condition` means, in words, for the messages.

        Raises:
            TimeoutError: naming `what` and the time, when `condition` still fails at the first
                tick at or after `timeout_s` from now.
        """
        deadline_ns = self._now_ns + round(timeout_s * _NANOSECONDS_PER_SECOND)
        until = f"{what}, by t = {deadline_ns / _NANOSECONDS_PER_SECOND} s"
        while not condition():
            if self._now_ns >= deadline_ns:
                raise TimeoutError(f"timed out at t = {self.now_s} s waiting until {until}")
            await _Tick(until)

    async def send(self, name: str, *, timeout_s: float = 5.0, **args: Any) -> None:
        """Uplinks a command and waits for its response.

        A `TimeoutError` names the command and the time when no response has come by the first tick
        at or after `timeout_s` from now.

        Args:
            name: `<instance>.<command>`, as the dictionary names it.
            timeout_s: s, how long to wait for the response.
            **args: the command's arguments by parameter name.

        Raises:
            CommandFailed: the response is not `OK`.
        """
        packet = self._link.dictionary.encode_command(name, args)
        self._context += 1
        context = self._context
        entry = {
            "t_s": self.now_s,
            "name": name,
            "args": {param: np.asarray(value).tolist() for param, value in args.items()},
            "context": context,
            "response": None,
            "response_t_s": None,
            "reason": None,
        }
        self.command_log.append(entry)
        self._link.uplink(packet, context)
        await self._until(lambda: context in self._answers, timeout_s, f"{name} is answered")
        names = {value: key for key, value in self._link.dictionary.responses.items()}
        response, entry["reason"] = self._answers.pop(context)
        entry["response"], entry["response_t_s"] = names[response], self.now_s
        if entry["response"] != "OK":
            raise CommandFailed(name, entry["response"], entry["reason"])

    def tlm(self, name: str) -> Any:
        """One channel's latest write.

        Args:
            name: `<instance>.<channel>`.

        Returns:
            The value, as the run file records it, or `None` before the channel is written.
        """
        channel = self._link.dictionary.channel(name)
        if channel.id not in self._latest:
            return None
        return self._link.values(channel, [self._latest[channel.id]])[0]

    def truth(self) -> dict[str, np.ndarray]:
        """The vehicle's true state now, the stand-in for tracking.

        Returns:
            The state as the vehicle's tracking reads it.
        """
        return self._truth()

    def Reset(self, CurrentSimNanos: int) -> None:
        """Starts the procedure, which runs to its first wait at the first tick.

        Args:
            CurrentSimNanos: ns, the reset time, as Basilisk passes it.

        Raises:
            BaseException: what calling the procedure raised, kept whole in `failure`.
        """
        self._now_ns = CurrentSimNanos
        try:
            self._coroutine = self._procedure(self)
        except BaseException as error:
            self.failure = error
            raise

    def UpdateState(self, CurrentSimNanos: int) -> None:
        """Takes the link's responses and telemetry, and runs the procedure to its next wait.

        Args:
            CurrentSimNanos: ns, the current simulation time, as Basilisk passes it.

        Raises:
            BaseException: the procedure's exception, kept whole in `failure`.
        """
        self._now_ns = CurrentSimNanos
        try:
            self._answers.update(
                (context, (response, reason))
                for context, response, reason in self._link.responses()
            )
            writes = self._link.telemetry()
            self._writes += writes
            self._latest.update((channel, payload) for channel, _, payload in writes)
            if self._coroutine is not None:
                try:
                    self._waiting = self._coroutine.send(None)
                except StopIteration:
                    self._coroutine = None
                    self._stop()
        except BaseException as error:
            self.failure = error
            raise

    def ensure_returned(self) -> None:
        """Checks that the procedure returned within the flight.

        Raises:
            TimeoutError: naming what the procedure still waited for when the flight ended.
        """
        if self._coroutine is not None:
            raise TimeoutError(
                f"the flight ended at t = {self.now_s} s with the procedure waiting until"
                f" {self._waiting.until}"
            )

    def telemetry_datasets(self) -> dict[str, tuple[np.ndarray, str]]:
        """Every telemetry write of the run, as run-file datasets, each channel in one batch.

        The writes the link still holds are taken first, so a write after the module's last tick
        is recorded too.

        Returns:
            For each channel written at least once, `tlm/<instance>.<channel>` to its values and
            units, and `tlm_t/<instance>.<channel>` to each write's flight software time tag in s.
        """
        self._writes += self._link.telemetry()
        by_channel: dict[int, tuple[list[int], list[Any]]] = {}
        for channel, t_ns, payload in self._writes:
            times, payloads = by_channel.setdefault(channel, ([], []))
            times.append(t_ns)
            payloads.append(payload)
        datasets = {}
        for channel_id, (times, payloads) in by_channel.items():
            channel = self._link.dictionary.channels_by_id[channel_id]
            datasets[f"tlm/{channel.name}"] = (self._link.values(channel, payloads), channel.units)
            datasets[f"tlm_t/{channel.name}"] = (
                np.array(times) / _NANOSECONDS_PER_SECOND,
                "s",
            )
        return datasets
