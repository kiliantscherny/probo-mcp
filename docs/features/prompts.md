# Prompts

Prompts are ready-made workflows. In Claude Desktop you'll find them in the **+** menu of the chat box.
Each one tells Claude which tools to use and what a good answer looks like.

| Prompt | Arguments | What it does |
|---|---|---|
| **What's new** (`whats_new`) | `days` (default 7), `language` | A briefing on recent messages, news and newly uploaded documents, grouped into upcoming decisions, money, practical disruptions and other. |
| **Summarise a document** (`summarize_document`) | `document_id`, `language` | Key points, every amount and deadline, what it means for an individual owner, and anything inconsistent. |
| **Prepare for the general meeting** (`prepare_for_general_meeting`) | `language` | Finds the notice (*indkaldelse*) and its attachments (*bilag*), then goes through each agenda item, its cost to you and the majority it needs, plus proxy rules and questions worth asking. |

ProBo content is usually in Danish, and `language` controls the language of the answer. It completes as
you type.

The prompts are plain instructions with no network access of their own, so they appear instantly. The
work happens when Claude follows them and calls the tools.
