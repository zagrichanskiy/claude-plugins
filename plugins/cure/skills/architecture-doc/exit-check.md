# Exit check

A section is `done` when all of these hold. Run the table checks first, then the review.

| Check | Pass condition |
|---|---|
| Description | The section meets its description in the layout |
| Size | The document so far stays within the size limit of `core.md` |
| Left out | The section holds no content that `core.md` leaves out, and no writer context |
| Open items | Open items are in the handoff file. For the open-decisions and risks section: all of them are in its tables, or it states there are none |
| Diagrams | Each one, in the document and in companion files, renders and follows the project's convention. Mermaid: extract each block and run `npx -y @mermaid-js/mermaid-cli -i <file>.mmd -o <file>.svg` |
| Consistency | Names and terms match the sections already `done` and the companion files |
| Decisions | Each decision made in the session appears in the document or in the handoff file |
| Review | At least one `cure:architect` REVIEW round ran, and the last ends with `SATISFIED` or its open findings were reported to the user after round 5 |

A failed table check returns the section to step 3.4 and is reported to the user. A REVIEW that ends with `NOT SATISFIED` follows step 3.5.
