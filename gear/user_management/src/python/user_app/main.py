"""Run method for user management."""

import logging

from users.user_processes import UserProcess, UserQueue

log = logging.getLogger(__name__)


def run(*, user_queue: UserQueue, user_process: UserProcess):
    """Manages users based on user list.

    Args:
      user_process: the user process for handling user entries from directory
      user_queue: the queue of user entries
    """
    user_process.execute(user_queue)
