# Contributing

Thanks for considering a contribution! Contributions and bug reports are very welcome.

## Ways to contribute

- Report bugs or problems
- Suggest improvements or new features
- Submit pull requests with fixes or enhancements
- Improve documentation or add new role coverage

## Getting started

1. **Fork** the repository and create a branch for your changes:
   `git checkout -b feat/my-change`
2. Make your edits.
3. Run the full pre-commit suite locally:
   ```bash
   make pre-commit
   # or
   pre-commit run --all-files
   ```
4. Open a **pull request** against `PROD` and describe what you changed and why.

## Development setup

```bash
# Install all dev dependencies
make install

# Run linters individually
make lint       # yamllint + ansible-lint
make yamllint
make ansible-lint
```

See the [Makefile](Makefile) for all available targets.

## Reporting bugs

Please open an issue using the bug report template and include:

- What you were trying to do
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Ansible version, Python version)

## Adding a new role

1. Create the role directory under `applications/` or `operating_systems/`
2. Copy the shared `tasks/main.yml` loader from an existing role
3. Create the most-specific OS task file (e.g., `tasks/redhat_rocky_10.yml`)
4. Populate `defaults/main.yml` with namespaced defaults (`<rolename>_defaults`)
5. Add a `README.md` documenting variables, security highlights, and known gaps
6. Add a `meta/main.yml` with Galaxy metadata

## Pull request guidelines

- Keep each PR focused on a single change when you can
- Commit messages must follow Conventional Commits format -- enforced by pre-commit
- Update documentation if behavior or configuration changes
- Ensure all CI checks pass before requesting review

## Commit format

```
<type>(<scope>): <short description>

Types:  feat | fix | docs | refactor | test | chore | perf | ci | build | revert
Scope:  role name or 'framework' (e.g., python3_pip, RedHat_Rocky_10, framework)
```

## Code of Conduct

This project is governed by the CODE_OF_CONDUCT.md file in this repository.
By participating, you agree to follow it.

## Questions

If you're not sure how best to contribute, feel free to open an issue and ask.
