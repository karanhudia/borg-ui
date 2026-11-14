# Preserve the chosen SSH key when resetting deployment presets

- [x] Reproduce selecting an extra key, switching from the Hetzner preset to Custom setup, and seeing the picker silently revert to the system key.
- [x] Preserve the selected SSH key alongside host, username and password when applying preset defaults. Assert the submitted deployment payload uses that key while resetting the port and path.
- [x] Add a Storybook state for Custom setup with an extra key selected.
- [x] Verify 28 SSH UI tests, locale parity, typecheck, lint, formatting, production build and whitespace checks. Build the scoped dialog Storybook and capture desktop/mobile screenshots with the existing snapshot script; inspect the selected-key state.

The regression failed before the one-line fix. Existing UI components and layouts remain unchanged. Screenshots are ignored under frontend/argos-screenshots and are not committed. Existing build chunk warnings remain.
