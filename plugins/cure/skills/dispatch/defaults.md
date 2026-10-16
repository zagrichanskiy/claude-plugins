# Example defaults

This file is an example. The live file is `${CURE_JOB_ROOT:-~/.claude/cure}/defaults.md`. Copy this
file there and edit it. The plugin never reads this copy.

`cure:dispatch` omits `base` and `delivery` unless the user stated them; a row supplies them.
`cure:goal` asks no fork that a row answers and marks the decision `(default)` under Settled. It
copies each matching `resource risk` row into Settled, marked `(default)`.

| key | value | scope |
|---|---|---|
| delivery | commit | all |
| base | main | all |
| branch | current | all |
| resource risk | bench is a test stand; any action on it is approved | device: bench |
