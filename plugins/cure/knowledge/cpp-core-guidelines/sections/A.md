# A (Architectural ideas)

## A.1: Separate stable code from less stable code

Isolating less stable code facilitates its unit testing, interface improvement, refactoring, and eventual deprecation.

## A.4: There should be no cycles among libraries

* A cycle complicates the build process.
* Cycles are hard to understand and might introduce indeterminism (unspecified behavior).
