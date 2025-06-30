# Contributing to OpenVPN Cluster Manager

We love your input! We want to make contributing to OpenVPN Cluster Manager as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

### Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. Issue that pull request!

## Development Setup

### Prerequisites

- Python 3.7+
- OpenVPN 2.4+
- EasyRSA 3.0+
- Git

### Local Development

```bash
# Clone your fork
git clone https://github.com/yourusername/openvpn-manager.git
cd openvpn-manager

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Run the application
python app.py
```

### Docker Development

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run with monitoring stack
docker-compose --profile monitoring up
```

## Code Style

### Python Code Style

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

- Line length: 88 characters (Black default)
- Use double quotes for strings
- Use f-strings for string formatting when possible

### Code Formatting

We use several tools to maintain code quality:

```bash
# Install development tools
pip install black isort flake8 mypy pytest

# Format code
black .
isort .

# Lint code
flake8 .
mypy .

# Run tests
pytest
```

### Pre-commit Hooks

We recommend using pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_app.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Write tests for all new functionality
- Aim for at least 80% code coverage
- Use descriptive test names
- Follow the Arrange-Act-Assert pattern

Example test:

```python
def test_client_creation():
    # Arrange
    client_name = "test_client"
    
    # Act
    result = OpenVPNManager.add_client(client_name)
    
    # Assert
    assert result["success"] is True
    assert result["client_name"] == client_name
```

## Documentation

### Code Documentation

- Use docstrings for all public functions and classes
- Follow Google-style docstrings
- Include type hints where appropriate

Example:

```python
def add_client(client_name: str, expiry_days: int = 3650) -> Dict[str, Any]:
    """Add a new OpenVPN client.
    
    Args:
        client_name: Name of the client to create
        expiry_days: Certificate validity period in days
        
    Returns:
        Dictionary containing operation result and client data
        
    Raises:
        ValueError: If client_name is invalid
        RuntimeError: If client creation fails
    """
    pass
```

### API Documentation

When adding new API endpoints:

1. Add docstring to the function
2. Update the API documentation in README.md
3. Include example requests/responses
4. Document any new parameters or response fields

## Reporting Bugs

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/yourusername/openvpn-manager/issues).

### Bug Report Template

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

### Bug Report Example

```markdown
## Summary
Brief description of the bug

## Environment
- OS: Ubuntu 20.04
- Python: 3.8.5
- OpenVPN Manager: 2.0.0

## Steps to Reproduce
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

## Expected Behavior
What you expected to happen

## Actual Behavior
What actually happened

## Additional Context
Any other context about the problem here
```

## Feature Requests

We welcome feature requests! Please:

1. Check if the feature already exists or is planned
2. Open an issue with the "feature request" label
3. Describe the feature and its use case
4. Explain why this feature would be useful to users

## Security Issues

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please send an email to security@your-domain.com with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Code of Conduct

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

### Our Standards

Examples of behavior that contributes to creating a positive environment include:

- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

### Enforcement

Project maintainers are responsible for clarifying the standards of acceptable behavior and are expected to take appropriate and fair corrective action in response to any instances of unacceptable behavior.

## Getting Help

- Join our [Discussions](https://github.com/yourusername/openvpn-manager/discussions)
- Check the [Wiki](https://github.com/yourusername/openvpn-manager/wiki)
- Open an [Issue](https://github.com/yourusername/openvpn-manager/issues)

## Recognition

Contributors will be recognized in our README.md file and release notes.

---

Thank you for contributing to OpenVPN Cluster Manager! 🎉 