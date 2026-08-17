from pydantic import BaseModel


class ConversationMetricsRead(BaseModel):
    total_conversations: int
    total_messages: int
    average_messages_per_conversation: float
    conversations_last_7_days: int


class KnowledgeMetricsRead(BaseModel):
    total_documents: int
    duplicate_document_count: int
    low_confidence_document_count: int
    unused_document_count: int
