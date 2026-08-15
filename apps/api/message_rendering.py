"""Markdown rendering (roadmap step 185, Milestone 6) -- `models/
message.py:Message.content` is already free-form text and needed no
schema change to legally hold markdown syntax; the real, new
capability this step adds is a server-side markdown -> HTML renderer,
exposed through `schemas/message.py:MessageRead.content_html`, so any
client (the eventual chat UI at step 194, a future non-web client, an
API integration) gets safe, already-rendered HTML without needing its
own markdown parser.

Python-Markdown (BSD-3-Clause, verified via importlib.metadata before
picking it) over mistune/markdown-it-py -- its official `fenced_code`/
`tables` extensions are exactly what step 186 ("code-block/table
formatting support") will layer on top of this same renderer, so
picking the library whose own extension names match the roadmap's next
step's literal wording avoids a second migration one step later.
Deliberately ZERO extensions enabled here -- step 186's own job, not
this one's; Python-Markdown's default (no extensions) already covers
what "markdown rendering" alone means: paragraphs, headings, bold/
italic, lists, links, blockquotes, inline code.

Sanitized with `nh3` (MIT, Mozilla's `ammonia` binding) after
rendering -- verified live before trusting it: a raw `<script>` tag
embedded in message content passes through Python-Markdown's own
output completely unescaped (confirmed by direct inspection, not
assumed from docs), a real XSS surface AGENTS.md SECTION 9's own
prompt-injection/zero-trust stance already calls out, especially once
a real LLM (still unwired to generation) starts producing this
content instead of only today's static/retrieved text. Uses nh3's own
default allow-list rather than hand-rolling one -- a vetted, maintained
default beats a bespoke list for exactly the same reason this
codebase already prefers a real library's own defaults over reinventing
them (e.g. table_infer_header at step 093).

Computed fresh on every read (`MessageRead`'s own `@computed_field`),
not stored on `Message` -- unlike `Chunk.search_vector` (a genuine
Postgres `GENERATED` column with zero staleness risk), a Python-side
render has no such database-native guarantee, so caching it would need
real invalidation machinery nothing has asked for; re-rendering a
short message string on each read is cheap enough not to need one.
"""

import markdown
import nh3


def render_markdown(content: str) -> str:
    html = markdown.markdown(content)
    return nh3.clean(html)
