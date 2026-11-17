# Contributing to Rezen

Thank you for your interest in contributing to Rezen!

Rezen is an open-source, cross-platform tool for remote device and screen control over a local network. It enables users to discover devices, establish connections, stream screens, and control remote machines without relying on cloud services or relay servers.

Contributions of all kinds are welcome, including bug fixes, feature improvements, documentation, tests, and platform compatibility enhancements.

This document explains how to set up the project, make changes, and submit contributions.

## Getting Started

### Prerequisites

Before setting up the project, make sure you have:

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- Git

### Setting Up the Development Environment

1. Fork the [Rezen repository](https://github.com/Sibsankar-de/rezen) using GitHub.
2. Clone your fork. You can copy its clone URL from the GitHub repository page.

   ```bash
   git clone <your-fork-clone-url>
   cd rezen
   ```

3. Install the project dependencies:

   ```bash
   uv sync
   ```

4. Run Rezen:

   ```bash
   uv run rezen
   ```

### Running Rezen

Rezen provides a terminal UI and headless CLI modes.

Start the terminal UI:

```bash
uv run rezen
```

Start broadcasting your device on the local network:

```bash
uv run rezen --start-broadcast
```

Discover other Rezen devices:

```bash
uv run rezen --start-discover
```

Both headless modes run continuously until interrupted with `Ctrl+C`.

## Before Making Changes

Before starting work on an issue or feature:

- Check existing issues and pull requests to avoid duplicating ongoing work.
- For significant changes, open an issue first to discuss the proposed implementation.
- Keep contributions focused on a specific bug fix or feature.
- Avoid introducing unnecessary dependencies.
- Consider the impact of your changes on existing functionality and cross-platform compatibility.

For larger architectural changes, discussing the approach before implementation can save time for both contributors and maintainers.

## Development Guidelines

Please follow the existing code structure and conventions throughout the project.

### General Guidelines

- Write clean, readable, and maintainable Python code.
- Use type hints wherever appropriate.
- Keep modules and classes focused on specific responsibilities.
- Prefer simple and understandable implementations over unnecessary abstractions.
- Handle exceptions explicitly instead of silently ignoring errors.
- Avoid introducing blocking operations into asynchronous execution paths.
- Release resources properly, including sockets, connections, threads, and streaming resources.
- Update relevant documentation when changing commands, configuration, installation, or user-facing behaviour.

### Networking and Protocol

Rezen relies on local network communication for device discovery and remote connections.

When working on networking or protocol-related functionality:

- Maintain compatibility with the existing protocol unless a protocol change is intentional.
- Handle malformed, incomplete, and unexpected network data safely.
- Account for connection failures, timeouts, and unexpected disconnections.
- Avoid assumptions about network interfaces, IP addresses, or subnet configurations.
- Ensure resources are properly released when connections terminate.

### Screen Streaming

When modifying screen capture, encoding, decoding, or streaming functionality:

- Consider performance, latency, and memory consumption.
- Avoid unnecessary frame copies and allocations.
- Handle encoding and decoding failures gracefully.
- Ensure streaming resources are cleaned up when a session ends.
- Consider different screen resolutions and aspect ratios.

### Cross-Platform Compatibility

Rezen aims to support multiple operating systems.

- Avoid introducing operating-system-specific assumptions into shared modules.
- Keep platform-specific implementations isolated where practical.
- Consider differences in screen capture, input handling, networking, and system permissions.
- Test changes on the relevant platforms whenever possible.
- Clearly mention any platform-specific limitations introduced by a change.

### Remote Input and Device Access

Changes involving keyboard and mouse forwarding should be handled carefully.

- Ensure input events are sent only to the intended connected device.
- Handle connection termination and interrupted input sessions safely.
- Avoid unintended interactions with the local machine.
- Test remote-control functionality only on devices and networks you own or have permission to access.

## Code Quality Checks

Run the following checks before submitting a pull request.

### Tests

```bash
uv run pytest
```

Add or update tests when introducing new functionality or modifying existing behaviour.

Bug fixes should include regression tests whenever practical.

### Linting

```bash
uv run ruff check .
```

### Formatting

```bash
uv run ruff format .
```

### Type Checking

```bash
uv run mypy src/
```

Please ensure that the relevant checks pass before submitting your changes. If a check cannot be performed in your environment, mention that in your pull request.

## Submitting a Pull Request

Once your changes are ready:

1. Create a new branch from the latest `main` branch.

   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/your-feature-name
   ```

2. Implement your changes.
3. Add or update tests and documentation where necessary.
4. Run the code quality checks.
5. Commit your changes with a clear and descriptive commit message.

   ```bash
   git add .
   git commit -m "Add descriptive commit message"
   ```

6. Push your branch to your fork.

   ```bash
   git push origin feature/your-feature-name
   ```

7. Open a pull request against the `main` branch of the original Rezen repository.

### Pull Request Guidelines

A good pull request should include:

- A clear description of the problem being addressed.
- An explanation of the proposed changes.
- Relevant issue references, if applicable.
- Testing steps or instructions to verify the changes.
- The operating systems and environments on which the changes were tested.
- Screenshots or logs when they help explain UI or runtime changes.

Keep pull requests focused and avoid combining unrelated changes.

Please be open to feedback and make the necessary adjustments during the review process.

## Reporting Bugs

If you encounter a bug, please open an issue in the [GitHub Issues](https://github.com/Sibsankar-de/rezen/issues) section.

Include the following information whenever possible:

- A clear description of the problem.
- Steps to reproduce the issue.
- Expected behaviour and actual behaviour.
- Operating system and version.
- Python version.
- Relevant error messages or logs.

Rezen writes logs to `logs/rezen.log`. Including relevant log output can help identify the cause of a problem.

Before sharing logs, make sure to remove sensitive information such as private IP addresses, credentials, and tokens.

## Suggesting Features

Feature suggestions are welcome!

When proposing a new feature, open an issue describing:

- The problem you are trying to solve.
- The proposed functionality.
- Why the feature would be useful.
- Any alternative approaches you have considered.

For significant features, discuss the design and implementation approach with the maintainer before starting development.

## Community Guidelines

Please keep all project discussions respectful and constructive.

- Be considerate of other contributors.
- Provide helpful and actionable feedback during code reviews.
- Be open to different approaches and suggestions.
- Avoid unnecessary discussions unrelated to the project.
- Help new contributors understand the codebase whenever possible.

## License

By contributing to Rezen, you agree that your contributions will be licensed under the [MIT License](https://github.com/Sibsankar-de/rezen/blob/main/LICENSE), under which the project is distributed.

Thank you for taking the time to contribute to Rezen. Every contribution, whether big or small, is appreciated!
