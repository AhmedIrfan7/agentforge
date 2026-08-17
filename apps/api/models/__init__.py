"""Import every model module here so its table registers on db.Base.metadata
for Alembic autogenerate — see migrations/env.py."""

from models.agent_execution_log import AgentExecutionLog
from models.api_key import ApiKey
from models.assistant import Assistant
from models.audit_log import AuditLog
from models.chunk import Chunk
from models.conversation import Conversation
from models.document import Document
from models.document_version import DocumentVersion
from models.invitation import Invitation
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.memory import Memory
from models.message import Message
from models.mfa_backup_code import MfaBackupCode
from models.oauth_identity import OAuthIdentity
from models.organization import Organization
from models.permission import Permission, RolePermission
from models.role import Role
from models.security_settings import SecuritySettings
from models.session import Session
from models.user import User
from models.verification_token import VerificationToken
from models.voice_session import VoiceSession
from models.workspace import Workspace

__all__ = [
    "AgentExecutionLog",
    "ApiKey",
    "Assistant",
    "AuditLog",
    "Chunk",
    "Conversation",
    "Document",
    "DocumentVersion",
    "Invitation",
    "KnowledgeBase",
    "Membership",
    "Memory",
    "Message",
    "MfaBackupCode",
    "OAuthIdentity",
    "Organization",
    "Permission",
    "Role",
    "RolePermission",
    "SecuritySettings",
    "Session",
    "User",
    "VerificationToken",
    "VoiceSession",
    "Workspace",
]
