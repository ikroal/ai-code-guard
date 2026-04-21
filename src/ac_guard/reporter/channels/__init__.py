"""Reporter channels — physical output destinations for rendered reports.

A *channel* is a physical destination for an already-rendered string
payload. Each channel implements a single method::

    def output(self, payload: str) -> None: ...

Built-in channels (auto-registered on import):

    - :class:`TerminalChannel` — print to a text stream (default stdout).
    - :class:`FileChannel` — write to a local file.
    - :class:`GitHubChannel` / :class:`GitLabChannel` / :class:`GiteaChannel`
      / :class:`BitbucketChannel` — HTTP POST to a PR/MR comments endpoint.

Shared Git-platform plumbing lives in :class:`GitPlatformChannel`; the
:func:`post_pr_comment` convenience wrapper dispatches by platform name
and swallows failures non-blockingly.

Register a third-party channel with the :func:`register_channel`
decorator, then call :func:`get_channel` to look it up by name.
"""

from ac_guard.reporter.channels.base import (
    ChannelError,
    NoPrContextError,
    ReportChannel,
    get_channel,
    register_channel,
)
from ac_guard.reporter.channels.bitbucket import BitbucketChannel
from ac_guard.reporter.channels.file import FileChannel
from ac_guard.reporter.channels.git_platform import (
    GitPlatformChannel,
    post_pr_comment,
)
from ac_guard.reporter.channels.gitea import GiteaChannel
from ac_guard.reporter.channels.github import GitHubChannel
from ac_guard.reporter.channels.gitlab import GitLabChannel
from ac_guard.reporter.channels.terminal import TerminalChannel

__all__ = [
    "BitbucketChannel",
    "ChannelError",
    "FileChannel",
    "GitHubChannel",
    "GitLabChannel",
    "GitPlatformChannel",
    "GiteaChannel",
    "NoPrContextError",
    "ReportChannel",
    "TerminalChannel",
    "get_channel",
    "post_pr_comment",
    "register_channel",
]
