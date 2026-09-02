# Plan: automatic remote-direct execution

1. Inspect existing remote-direct selection, execution, review UI, and tests.
2. Remove the stale runtime eligibility gate while retaining the Borg command
   execution path.
3. Add an informational review state for same-connection remote SSH routes.
4. Add backend regression coverage and a Storybook story for the new review
   state.
5. Run focused and frontend/backend validation, then open a dedicated PR.
