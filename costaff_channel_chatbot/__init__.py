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
from .envelope import ParsedEnvelope, parse_result_envelope
from .formatters import (
    md_to_discord,
    md_to_plain,
    md_to_slack,
    md_to_telegram_html,
    strip_result_envelope,
)
from .rate_limit import RateLimiter
from .response import (
    ATTACHMENT_HINT,
    DATA_ROOT,
    extract_path_candidates,
    protect_code_blocks,
    resolve_path,
    restore_code_blocks,
    rewrite_with_hint,
    split_message,
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
    "ParsedEnvelope",
    "check_approved",
    "create_new_session",
    "delete_session",
    "extract_path_candidates",
    "md_to_discord",
    "md_to_plain",
    "md_to_slack",
    "md_to_telegram_html",
    "parse_result_envelope",
    "split_message",
    "strip_result_envelope",
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
