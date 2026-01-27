"""
Async Task Registry for tracking background tasks.

Replaces fire-and-forget pattern with proper task lifecycle management.
"""

import asyncio
import logging
from typing import Any, Coroutine, Dict, Optional, Set
import time

logger = logging.getLogger("aicc.task_registry")


class TaskRegistry:
    """
    Registry for tracking and managing async tasks.

    Features:
    - Track all background tasks with names
    - Log failures with context
    - Graceful shutdown with timeout
    - Metrics for failed task count
    """

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._failed_tasks: Set[str] = set()
        self._completed_count: int = 0
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task:
        """
        Register and start an async task.

        Args:
            name: Unique task name for tracking
            coro: Coroutine to execute

        Returns:
            The created asyncio.Task
        """
        task = asyncio.create_task(coro)
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_complete(name, t))
        logger.debug(f"Task registered: {name}")
        return task

    def _on_task_complete(self, name: str, task: asyncio.Task) -> None:
        """Handle task completion callback."""
        # Remove from active tasks
        self._tasks.pop(name, None)
        self._completed_count += 1

        # Check for exceptions
        try:
            exc = task.exception()
            if exc:
                self._failed_tasks.add(name)
                logger.error(f"Task '{name}' failed with exception: {exc}", exc_info=exc)
        except asyncio.CancelledError:
            logger.debug(f"Task '{name}' was cancelled")
        except asyncio.InvalidStateError:
            # Task not done yet (shouldn't happen in done callback)
            pass

    @property
    def active_count(self) -> int:
        """Number of currently active tasks."""
        return len(self._tasks)

    @property
    def failed_count(self) -> int:
        """Number of tasks that failed with exceptions."""
        return len(self._failed_tasks)

    @property
    def completed_count(self) -> int:
        """Total number of completed tasks."""
        return self._completed_count

    def get_active_tasks(self) -> Dict[str, asyncio.Task]:
        """Get dictionary of active tasks."""
        return dict(self._tasks)

    def get_failed_task_names(self) -> Set[str]:
        """Get set of failed task names."""
        return set(self._failed_tasks)

    async def cancel_task(self, name: str) -> bool:
        """
        Cancel a specific task by name.

        Returns:
            True if task was found and cancelled
        """
        task = self._tasks.get(name)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

    async def shutdown(self, timeout: float = 5.0) -> None:
        """
        Gracefully shutdown all tasks.

        Args:
            timeout: Maximum time to wait for tasks to complete
        """
        if not self._tasks:
            logger.debug("No active tasks to shutdown")
            return

        task_count = len(self._tasks)
        logger.info(f"Shutting down {task_count} active tasks (timeout={timeout}s)")

        # Cancel all tasks
        for name, task in list(self._tasks.items()):
            task.cancel()

        # Wait for all tasks to complete or timeout
        if self._tasks:
            tasks = list(self._tasks.values())
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                remaining = len([t for t in tasks if not t.done()])
                logger.warning(f"Shutdown timeout: {remaining} tasks still running")

        logger.info(f"Task registry shutdown complete. Failed tasks: {len(self._failed_tasks)}")

    def clear_failed_tasks(self) -> None:
        """Clear the set of failed task names."""
        self._failed_tasks.clear()


# Global instance for convenience
_default_registry: Optional[TaskRegistry] = None


def get_default_registry() -> TaskRegistry:
    """Get or create the default task registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = TaskRegistry()
    return _default_registry


def safe_task(
    coro: Coroutine[Any, Any, Any],
    name: Optional[str] = None,
    registry: Optional[TaskRegistry] = None,
) -> asyncio.Task:
    """
    Create a tracked async task (replacement for _safe_task).

    Args:
        coro: Coroutine to execute
        name: Optional task name (auto-generated if not provided)
        registry: TaskRegistry to use (uses default if not provided)

    Returns:
        The created asyncio.Task
    """
    if registry is None:
        registry = get_default_registry()

    if name is None:
        name = f"task_{time.time()}_{id(coro)}"

    return registry.register(name, coro)
