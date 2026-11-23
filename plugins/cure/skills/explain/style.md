# Writing and provenance

## Writing

- Say the literal thing: "a way to use it without adopting sd-event", not "an escape hatch".
- Define an acronym in the sentence where it first appears.
- A paragraph opens with the claim, then supports it.
- Give the mechanism before the recommendation.
- Prefer worked numbers to adjectives: "roughly 1 KB per socket endpoint, so ~240 endpoints is under 1 MB".
- Draw a short ASCII diagram for anything with two or more moving parts.
- State a correction in one plain sentence, then continue. No apology, no preamble, no count of earlier mistakes.

## Three confusions to check before sending

1. One word covering two objects. "Socket" is the listening one and the connected one. "Library" is theirs and ours. Name each sense before using either. This includes numbers: write "heading 2.7" and "control 2.7", never a bare number, when a document cites an external numbered list.
2. Direction of control across a boundary (FFI, event loop, callback, IPC). State who calls whom.
3. The layer a fact belongs to. A tunnel has two MTUs. An encrypted link has a handshake key and a traffic key. Name the layer with the fact.

## Provenance tags

Tag every claim that decides something.

| Tag | Meaning |
|---|---|
| verified | Read from the primary source this session. Name the file. |
| upstream | Known about a project, not checked against its source |
| proposal | Someone's suggestion in a document, not agreed |
| inference | Yours |

- Never cite a proposal as a requirement. Write "the notes propose", not "the design is".
- Never cite a document as if the user has read it. Quote the line.
- Check a claim that moves an estimate or a recommendation: branch existence, recipe versions, symbol names, whether a feature is in the shipped release.
- Prefer the primary source (header, recipe, branch list, manual page). Check the local checkout before the web.
- State what you verified and how.
