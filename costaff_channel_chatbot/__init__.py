"""costaff-channel-chatbot — shared runtime for chatbot-style channels."""
from .adapter import ChannelAdapter, IncomingMessage
from .adk_client import (
    check_approved,
    create_new_session,
    delete_session,
    get_active_session_id,
    get_user_id,
    run_adk_prompt,
    set_active_session_id,
    setup_logging,
    sync_identity,
)
from .dedup import MessageDedup
from .rate_limit import RateLimiter
from .response import (
    ATTACHMENT_HINT,
    DATA_ROOT,
    extract_path_candidates,
    protect_code_blocks,
    resolve_path,
    restore_code_blocks,
    rewrite_with_hint,
    strip_leftover_hints,
    truncate,
)
from .runtime import (
    ChannelRuntime,
    DEFAULT_ERROR_MSG,
    DEFAULT_PENDING_MSG,
    DEFAULT_RATE_LIMIT_MSG,
    DEFAULT_RESET_MSG,
    ERROR_MSG,
    PENDING_MSG,
    RATE_LIMIT_MSG,
)

__version__ = "0.1.0"

__all__ = [
    "ChannelAdapter",
    "ChannelRuntime",
    "IncomingMessage",
    "MessageDedup",
    "RateLimiter",
    "ATTACHMENT_HINT",
    "DATA_ROOT",
    "DEFAULT_ERROR_MSG",
    "DEFAULT_PENDING_MSG",
    "DEFAULT_RATE_LIMIT_MSG",
    "DEFAULT_RESET_MSG",
    "ERROR_MSG",
    "PENDING_MSG",
    "RATE_LIMIT_MSG",
    "check_approved",
    "create_new_session",
    "delete_session",
    "extract_path_candidates",
    "get_active_session_id",
    "get_user_id",
    "protect_code_blocks",
    "resolve_path",
    "restore_code_blocks",
    "rewrite_with_hint",
    "strip_leftover_hints",
    "run_adk_prompt",
    "set_active_session_id",
    "setup_logging",
    "sync_identity",
    "truncate",
]
