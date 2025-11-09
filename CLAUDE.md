- Always run test suite before pushing to github
- Always add a new test or update existing when a new feature is added or a bug is fixed
- Ask every time you push if a release is required, if i answer yes, you decide if minor, major or patch and do it

## Release Process
- Creating a git tag automatically triggers a GitHub release
- Use `git tag vX.Y.Z` to create the tag
- Tag format: semantic versioning (vMAJOR.MINOR.PATCH)
  - MAJOR: Breaking changes or major new features
  - MINOR: New features, backward compatible
  - PATCH: Bug fixes and small improvements
- Push tags with `git push --tags`