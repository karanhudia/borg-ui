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

### Test Your Changes

```bash
# Backend tests
python3 -m pytest tests/

# Frontend build
cd frontend && npm run build

# Start the application
docker compose up -d --build
```

### Submit a Pull Request

1. Push your changes to your fork
2. Open a pull request against `main`
3. Describe your changes clearly
4. Link any related issues

## Contribution Guidelines

### Code Style

**Python (Backend)**
- Follow PEP 8
- Use type hints
- Add docstrings to functions
- Maximum line length: 100 characters

**TypeScript/React (Frontend)**
- Use functional components with hooks
- Use TypeScript for type safety
- Follow existing component structure

### Commit Messages

Follow conventional commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test changes
- `chore:` - Build/tooling changes

Examples:
```
feat: add notification system with Apprise integration
fix: resolve database migration issue in notifications
docs: update installation guide for Unraid
```

### Pull Request Requirements

Your PR should:
- Reference related issues (e.g., "Fixes #123")
- Have a clear title and description
- Include tests for new features
- Pass all existing tests
- Update documentation as needed

## Testing

Before submitting:

```bash
# Backend tests
python3 -m pytest tests/ -v

# Frontend tests (if you modified frontend)
cd frontend && npm test

# Frontend build (must succeed)
cd frontend && npm run build
```

## Development Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Node.js 18+

### Local Development

```bash
# Start development environment
docker compose up -d --build

# View logs
docker compose logs -f

# Access the application
# Frontend: http://localhost:8081
# API Docs: http://localhost:8081/api/docs
```

### Frontend Development (with hot reload)

```bash
cd frontend
npm install
npm run dev
# Access at http://localhost:5173
```

## What We're Looking For

We welcome contributions for:

- Bug fixes
- Documentation improvements
- New features (discuss first via issues)
- Test coverage improvements
- UI/UX enhancements
- Performance optimizations

## Reporting Issues

- Check if the issue already exists
- Provide clear description and reproduction steps
- Include relevant logs, screenshots, or error messages
- Specify your environment (OS, Docker version, etc.)

## Questions?

- Open an issue with the "question" label
- Check existing issues and discussions
- Be respectful and patient

## License

By contributing, you agree that your contributions will be licensed under the GNU General Public License v3.0, the same license as this project.

All contributions become part of the project and are subject to the terms in the [LICENSE](../LICENSE) file.

## Recognition

Contributors will be recognized in:
- Release notes
- Project documentation
- GitHub contributors page

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help make this a welcoming community

## Need Help?

- **Documentation**: [Full Documentation](https://karanhudia.github.io/borg-ui)
- **Issues**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)

Thank you for contributing to Borg Web UI!
