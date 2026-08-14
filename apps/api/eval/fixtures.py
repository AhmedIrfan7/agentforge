"""Labeled fixtures (roadmap step 128) -- a small, real, hardcoded
corpus with topics distinct enough that retrieval must actually
discriminate between them; a corpus where every document is relevant
to every query couldn't distinguish a real retriever from a random
one. `EvalDocument.key` is a fixture-local label, not a real UUID --
harness.py assigns each one a real Document/Chunk row on seeding and
resolves `EvalCase.relevant_document_keys` against the real ids it
gets back, since nothing here can know a real UUID in advance.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalDocument:
    key: str
    text: str


@dataclass(frozen=True)
class EvalCase:
    query: str
    relevant_document_keys: set[str]


@dataclass(frozen=True)
class EvalFixtureSet:
    documents: list[EvalDocument]
    cases: list[EvalCase]


RETRIEVAL_FIXTURES = EvalFixtureSet(
    documents=[
        EvalDocument(
            key="refund_policy",
            text=(
                "Our refund policy allows returns within thirty days of purchase. "
                "Items must be unused and in their original packaging to qualify "
                "for a full refund."
            ),
        ),
        EvalDocument(
            key="shipping_policy",
            text=(
                "Standard shipping takes five to seven business days. Express "
                "shipping delivers within two business days for an additional fee. "
                "We currently ship to most countries worldwide."
            ),
        ),
        EvalDocument(
            key="warranty_policy",
            text=(
                "All products come with a one year limited warranty covering "
                "manufacturing defects. The warranty does not cover damage caused "
                "by misuse or normal wear and tear."
            ),
        ),
        EvalDocument(
            key="company_history",
            text=(
                "The company was founded in a small garage and has since grown "
                "into a team of hundreds of employees across three countries, "
                "building tools for small businesses."
            ),
        ),
        EvalDocument(
            key="privacy_policy",
            text=(
                "We collect only the personal data necessary to process orders "
                "and never sell customer data to third parties. Customers may "
                "request deletion of their data at any time."
            ),
        ),
    ],
    # Query wording deliberately echoes vocabulary each target document
    # actually contains, verified live against real Postgres before
    # finalizing: repositories/chunk.py:search_by_keyword uses
    # plainto_tsquery, which ANDs every non-stopword term together, so a
    # single query word absent from the target document makes the whole
    # AND match nothing, not just rank lower -- a first draft used "how
    # long does shipping take", which failed for exactly this reason:
    # "long" is not a stopword and never appears anywhere in the
    # shipping document's own text.
    cases=[
        EvalCase(query="refund policy returns", relevant_document_keys={"refund_policy"}),
        EvalCase(query="shipping business days", relevant_document_keys={"shipping_policy"}),
        EvalCase(
            query="warranty manufacturing defects", relevant_document_keys={"warranty_policy"}
        ),
        EvalCase(query="customer data deletion request", relevant_document_keys={"privacy_policy"}),
        EvalCase(query="company founded garage", relevant_document_keys={"company_history"}),
    ],
)
