"""Email sending — stub. Logs the message instead of sending it, since no
real provider (SendGrid/SES/Postmark/etc.) is wired up yet — that's a
future integration (AGENTS.md's Notifications work), not something to
fake with a real-looking but non-functional client now.

This is the ONE function every email-triggering flow calls
(verify-email, magic-link, password-reset) — swapping in a real
provider later means changing this function's body, not any caller.

Lives under notifications/, not a bare top-level email.py — that name
would shadow Python's own stdlib `email` package for any code running
from within apps/api (it's on sys.path directly), which is exactly the
kind of subtle footgun worth avoiding rather than working around later.
"""

from logging_config import get_logger

logger = get_logger(__name__)


def send_email(*, to: str, subject: str, body: str) -> None:
    logger.info("email_stub_send", to=to, subject=subject, body=body)
