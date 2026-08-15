"""Markdown rendering (roadmap steps 185-186, Milestone 6) -- `models/
message.py:Message.content` is already free-form text and needed no
schema change to legally hold markdown syntax; the real, new
capability these steps add is a server-side markdown -> HTML renderer,
exposed through `schemas/message.py:MessageRead.content_html`, so any
client (the eventual chat UI at step 194, a future non-web client, an
API integration) gets safe, already-rendered HTML without needing its
own markdown parser.

Python-Markdown (BSD-3-Clause, verified via importlib.metadata before
picking it) over mistune/markdown-it-py -- its official `fenced_code`/
`tables` extensions are exactly what step 186 needs, so picking the
library whose own extension names match the roadmap's next step's
literal wording avoided a second migration one step later, confirmed
now that 186 has actually landed: both extensions enabled here,
nothing else changed about how 185's own renderer works.

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

As of step 186, `_ATTRIBUTES`/`_attribute_filter` add ONE narrow
exception to that default allow-list: `<code class="language-xxx">`,
the fenced-code language hint `fenced_code` emits, needed for a future
frontend syntax highlighter to know what language to highlight --
nh3's own default strips ANY `class` attribute (confirmed live before
adding this), which would silently throw that hint away. Restricted
via `attribute_filter` to values starting with `language-` specifically
(not a blanket "allow any class on code") -- verified live that
Python-Markdown's own fence-info-string parser already only ever
emits a clean `language-<identifier>` token (an adversarial fence info
string like `evil"><script>` doesn't even parse as a language at all,
falling back to an unlabeled block), so this filter is real defense in
depth on top of an input that's already safe at the source, not the
only thing standing between a raw class value and the page. No such
allowance needed for `<table>`/`<thead>`/`<tbody>`/`<tr>`/`<th>`/`<td>`
-- nh3's own default tag allow-list already includes all five with no
extra attributes needed, confirmed live before assuming so.

Computed fresh on every read (`MessageRead`'s own `@computed_field`),
not stored on `Message` -- unlike `Chunk.search_vector` (a genuine
Postgres `GENERATED` column with zero staleness risk), a Python-side
render has no such database-native guarantee, so caching it would need
real invalidation machinery nothing has asked for; re-rendering a
short message string on each read is cheap enough not to need one.
"""

import copy

import markdown
import nh3

_EXTENSIONS = ["fenced_code", "tables"]

_ATTRIBUTES = copy.deepcopy(nh3.ALLOWED_ATTRIBUTES)
_ATTRIBUTES.setdefault("code", set())
_ATTRIBUTES["code"].add("class")


def _attribute_filter(tag: str, attr: str, value: str) -> str | None:
    if tag == "code" and attr == "class":
        return value if value.startswith("language-") else None
    return value


def render_markdown(content: str) -> str:
    html = markdown.markdown(content, extensions=_EXTENSIONS)
    return nh3.clean(html, attributes=_ATTRIBUTES, attribute_filter=_attribute_filter)
