# Review and merge

For authors and maintainers preparing or reviewing a PR. [CONTRIBUTING](../index.md#open-and-review-a-pull-request) is the canonical policy; this page explains the procedure.

**Prerequisites:** a scoped PR with current documentation and changelog. **Inputs:** the current head SHA, change rationale, tests and scientific evidence. **Outputs:** resolved findings and a recorded review of that revision. **Success:** an eligible approval, resolved conversations and passing required checks allow the merge queue to test the prospective merged state.

1. Read the problem and expected behaviour, then identify affected users and supported inputs. Check that public contracts, migration guidance and limits describe the implementation being merged.
2. Inspect CI for the exact reviewed revision using [Understand PR checks](pr-checks.md). Spend review effort on what CI does not establish: independent reference values, counterexamples, untested configurations, units and coordinate conventions. Follow [Scientific verification](../validation/scientific.md) for scientific changes.
3. State each finding by its consequence, evidence and suggested fix. Identify findings that block approval. Resolve substantive findings before approving.
4. For a stacked PR, verify the parent PR is named and the base is its branch. Merge the parent's changes into the child before review and merge; retarget the child to `main` after the parent merges. Avoid rebasing a reviewed stack.
5. Request another review after substantive changes. GitHub does not automatically dismiss existing approvals in this repository, so an old approval does not establish that later changes were reviewed.
6. Contributors with Write access may add the PR to the merge queue when required checks pass, conversations are resolved and an eligible reviewer approves. The branch need not contain the latest `main`; the queue tests the prospective merge. Admin review bypass is an explicit permission described in CONTRIBUTING, and CI remains required.

Programme decisions belong in their [design documents](../design/index.md), with scientific evidence shipped alongside implementation. A pending governance proposal or historical discussion is not a new review requirement. Recheck this procedure when contributor policy or branch rules change.
