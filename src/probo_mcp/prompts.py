"""MCP prompts: ready-made workflows a user can pick from their client's prompt menu."""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

Language = Annotated[str, Field(description="Language for the answer (ProBo content is usually Danish).")]


def whats_new(language: Language = "English") -> str:
    """Brief me on everything new in the association since I last asked."""
    return f"""Give me a briefing on what's new in my owners' association on ProBo since I last asked.

1. Call whats_new. It returns every message, news post and document not yet in my local archive, \
already fetched in full with attachment text, and remembers them. If `remaining` is above 0, call it \
again until it is 0.
2. If an item's text is cut short and it matters, read the rest with read_document (attachment `path`), \
or from the file in `saved_to`.

Answer in {language}. Group the briefing into: decisions or votes coming up (with dates and deadlines), \
money (costs, budgets, loans: what it means for an individual owner), practical disruptions \
(water, heating, building work, access), and everything else. Mark items that are updates (a new reply \
or comment) as such. ProBo also sends notification messages announcing a news post or new documents \
("Nyhed tilføjet", "Nyt dokument"): when the post or document itself is in the results, mention it once. \
Quote amounts and dates exactly, say which document or message each point comes \
from, and flag anything I need to act on. If nothing is new, just say so."""


def summarize_document(
    document_id: Annotated[str, Field(description="Document id from the archive.")],
    language: Language = "English",
) -> str:
    """Summarise one document from the archive."""
    return f"""Read the ProBo document {document_id} (use read_document, or the resource probo://documents/{document_id}).

Summarise it in {language}: what it is and who sent it, the key points, every amount, date and deadline, \
and what it means for an individual owner. Point out anything that looks inconsistent or wrong \
(numbers that don't add up, dates that contradict each other)."""


def prepare_for_general_meeting(
    language: Language = "English",
) -> str:
    """Help me prepare for the next general meeting (generalforsamling)."""
    return f"""Help me prepare for the next general meeting (generalforsamling) of my owners' association.

1. Find the notice (indkaldelse): search messages and news for "generalforsamling" and use \
find_documents with name_contains="generalforsamling" and with added_within_days=60.
2. Read the agenda (dagsorden) and every attachment (bilag) with read_document.

Then, in {language}: give the date, time and place; list each agenda item with what is being proposed, \
the cost to me as an individual owner, and the majority needed to pass it; note proxy (fuldmagt) rules \
and deadlines; and end with a short list of questions worth asking at the meeting, including any \
errors or inconsistencies you spotted in the documents."""


def register(mcp: MCPServer) -> None:
    """Register prompts on ``mcp``."""
    mcp.prompt(title="What's new")(whats_new)
    mcp.prompt(title="Summarise a document")(summarize_document)
    mcp.prompt(title="Prepare for the general meeting")(prepare_for_general_meeting)
