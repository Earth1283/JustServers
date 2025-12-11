import asyncio
import subprocess
from typing import Optional, AsyncGenerator
from pathlib import Path

class ServerProcess:
    """
    Handles the lifecycle of a Minecraft server process.
    """
    def __init__(self, jar_path: str, working_dir: str, min_mem: str = "2G", max_mem: str = "4G"):
        self.jar_path = jar_path
        self.working_dir = Path(working_dir)
        self.min_mem = min_mem
        self.max_mem = max_mem
        self.process: Optional[asyncio.subprocess.Process] = None

    @property
    def is_running(self) -> bool:
        """Asks \"Are you alive?\" to the server proc"""
        return self.process is not None and self.process.returncode is None

    async def start(self) -> bool:
        """
        Starts the Java process asynchronously.
        Returns True if started successfully.
        """
        if self.is_running:
            return False

        # Construct the command list (safe, no shell=True injection risks)
        cmd = [
            "java",
            f"-Xms{self.min_mem}",
            f"-Xmx{self.max_mem}",
            "-jar", self.jar_path,
            "nogui"
        ]

        try:
            # stdin=PIPE allows us to write commands
            # stdout=PIPE allows us to read logs
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT  # Merge error logs into standard output
            )
            return True
        except FileNotFoundError:
            # Java not installed or path wrong
            return False

    async def stop(self):
        """
        Gracefully stops the server.
        """
        # 1. Explicit check for Pylance (Type Narrowing)
        if self.process is None:
            return

        # 2. Check if it's already dead so we don't try to stop a corpse
        if self.process.returncode is not None:
            self.process = None
            return

        # Now Pylance knows self.process is DEFINITELY a Process object
        await self.write_command("stop")
        
        try:
            await asyncio.wait_for(self.process.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            self.process.kill()
        
        self.process = None

    async def write_command(self, command: str):
        """
        Sends a command to the Minecraft console (stdin).
        """
        # Check both process existence AND stdin pipe existence
        if self.process is None or self.process.stdin is None:
            return

        # Pylance is happy because we explicitly checked for None above
        try:
            self.process.stdin.write(f"{command}\n".encode())
            await self.process.stdin.drain()
        except BrokenPipeError:
            # Server crashed or closed unexpectedly
            pass

    async def stream_logs(self) -> AsyncGenerator[str, None]:
        """
        Yields log lines.
        """
        # Check process AND stdout pipe
        if self.process is None or self.process.stdout is None:
            return

        async for line in self.process.stdout:
            yield line.decode('utf-8').strip()
