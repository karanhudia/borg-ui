---
layout: default
title: Contributing
nav_order: 9
description: "How to contribute to Borg Web UI"
---

# Contributing to Borg Web UI

Thank you for your interest in contributing to Borg Web UI!

## Quick Start

### Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/borg-ui.git
cd borg-ui

# Add upstream remote
git remote add upstream https://github.com/karanhudia/borg-ui.git
```

### Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### Make Changes

- Follow the existing code style
- Add tests for new features
- Update documentation as needed
- Install git hooks with `pre-commit install --hook-type pre-commit --hook-type pre-push`

### Test Your Changes

```bash
# Run repository hooks
pre-commit run --all-files

# Backend tests
pytest

# Frontend type checking
cd frontend && npm run typecheck

# Start dev environment (hot reload)
./scripts/dev.sh

# Or test the full production build
docker-compose up -d --build
```

### Submit a Pull Request

1. Push your changes to your fork
2. Open a pull request against `main`
3. Describe your changes clearly
4. Link any related issues

## Contribution Guidelines

### Code Style

**Backend (Python)**
- Follow PEP 8
- Use type hints where applicable
- Add docstrings for functions and classes
- Keep functions focused and testable

**Frontend (TypeScript/React)**
- Use TypeScript for type safety
- Follow Material-UI patterns
- Keep components small and reusable
- Use hooks for state management

### Testing

All contributions should include appropriate tests:

**Unit Tests**
- Test individual functions and components
- Mock external dependencies
- Aim for high code coverage

**Integration Tests**
- Test API endpoints
- Test database operations
- Test service interactions

Run tests before submitting:
```bash
python3 -m pytest tests/ -v
```

### Documentation

Update documentation when:
- Adding new features
- Changing existing behavior
- Fixing bugs that affect usage
- Adding new configuration options

Documentation files are in the `docs/` directory.

## Development Setup

See the full [Development Guide](development.md) for detailed instructions. Quick summary:

```bash
# Start dev environment (backend in Docker, frontend local, both hot-reload)
./scripts/dev.sh
```

- Frontend: [http://localhost:7879](http://localhost:7879)
- Dev backend: `http://localhost:DEV_PORT` (default `8083`, set in `.env`)

```bash
# Test the production build
docker-compose up -d --build
```

- Production: `http://localhost:PORT` (default `8082`, set in `.env`)

Both can run simultaneously — they use separate container names and ports.

## Reporting Issues

When reporting issues, please include:

1. **Description** - Clear description of the problem
2. **Steps to Reproduce** - Exact steps to trigger the issue
3. **Expected Behavior** - What you expected to happen
4. **Actual Behavior** - What actually happened
5. **Environment**:
   - Borg Web UI version
   - Docker version
   - OS and version
   - Browser (if frontend issue)
6. **Logs** - Relevant error messages or logs

## Feature Requests

For feature requests, please provide:

1. **Use Case** - Why this feature is needed
2. **Proposed Solution** - How you envision it working
3. **Alternatives** - Other solutions you've considered
4. **Additional Context** - Screenshots, examples, etc.

## Code Review Process

1. All pull requests require review before merging
2. Automated tests must pass
3. Code must follow style guidelines
4. Documentation must be updated
5. Maintainers may request changes

## License

By contributing to Borg Web UI, you agree that your contributions will be licensed under the GNU Affero General Public License v3.0.

## Questions?

- **GitHub Discussions** - [Ask questions](https://github.com/karanhudia/borg-ui/discussions)
- **GitHub Issues** - [Report bugs](https://github.com/karanhudia/borg-ui/issues)

We appreciate your contributions!
