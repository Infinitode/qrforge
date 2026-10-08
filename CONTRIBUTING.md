# Contributing to qrforge

Thank you for considering contributing to **qrforge**! Contributions, whether they are bug fixes, new features, new shapes/shaders/presets, or improvements to the documentation, are always welcome. Before contributing, please read the following guidelines to ensure smooth collaboration.

## Getting Started

1. **Fork the Repository**
   Create a fork of this repository to your GitHub account and clone it locally.

2. **Set Up the Environment**
   Ensure you have Python 3.8+ installed. The core library has **no hard dependencies**; install Pillow only if you need to test non-PNG image I/O:
   ```bash
   pip install pillow
   ```

3. **Run Tests**
   Before making changes, run the test-suite to confirm everything works:
   ```bash
   python -m pytest tests -q
   ```

> [!TIP]
> The test-suite round-trips every symbol through the bundled decoder and re-rasterises the SVG geometry, so a green run means your change keeps QR codes scannable.

## How to Contribute

1. **Report Issues**
   Use the GitHub Issues page to report bugs or suggest features (the templates in `.github/ISSUE_TEMPLATE` will guide you). Please include:
   - A clear description of the issue or suggestion.
   - Steps to reproduce (for bugs), including the `qrforge` version / style options used.

2. **Make Changes**
   - Use clear and descriptive commit messages.
   - (Optional but encouraged) Write tests to show new functionality.
   - Keep the library dependency-free; anything new must run on the standard library.
   - Ensure the code is **readable**. You can learn more about Python code readability here: https://peps.python.org/pep-0008/.

3. **Submit a Pull Request**
   - Push your changes to a feature branch in your fork.
   - Submit a pull request with a detailed explanation of what you've changed or added.
   - Ensure your PR passes all automated tests and adheres to the contribution guidelines.

## Community Guidelines

To maintain a positive and welcoming community, we ask that all contributors adhere to the following principles:

1. **Be Respectful**
   Treat others with respect, regardless of their background or expertise.

2. **Provide Constructive Feedback**
   Offer helpful and actionable feedback during code reviews.

3. **Follow Licensing Requirements**
   Ensure any derivative works comply with the [license](LICENSE.md).

By contributing, you agree to abide by these guidelines and this project's [license](LICENSE.md). Thank you for helping make **qrforge** better!
