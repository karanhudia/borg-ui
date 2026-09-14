# Archive folder download implementation plan

1. Add a binary Borg command stream and version-specific `export-tar` command
   builders.
2. Add the authenticated server endpoint, including direct and agent-relayed
   streaming paths.
3. Add the matching agent operation and classify it as a request-scoped
   repository read.
4. Add the version-aware frontend client and download utility.
5. Surface the directory-only action in the archive details pane, translations,
   tests, and Storybook state.
6. Run focused backend and frontend checks.
