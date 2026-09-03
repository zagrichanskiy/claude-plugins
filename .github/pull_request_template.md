## Summary

[What changes and why]

## Checklist

- [ ] `version` bumped in the changed plugin's `plugin.json`
- [ ] `claude plugin validate .` passes
- [ ] `claude plugin details <plugin>` lists every agent and skill — the manifest validator does not
      catch an agent skipped for bad frontmatter
