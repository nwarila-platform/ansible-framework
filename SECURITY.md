# Security Policy

## Supported versions

Only the latest commit on the `PROD` branch is actively maintained and receives security fixes.

| Branch | Supported |
|--------|-----------|
| `PROD` (latest) | Yes |
| Older commits | No |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability, please email:

**reports@TrinityTechnicalServices.com**

Include the following in your report:

- A description of the vulnerability and its potential impact
- The affected component (Ansible role, CI workflow, pre-commit hook, template, etc.)
- Steps to reproduce or a proof-of-concept (if applicable)
- Any suggested remediation

### What to expect

- **Acknowledgement** within 48 hours
- **Initial assessment** within 5 business days
- **Resolution or mitigation plan** communicated before any public disclosure

We follow coordinated disclosure. Please allow reasonable time to address the issue before publishing details publicly.

## Security controls in this repository

This repository enforces the following security controls at every commit and in CI:

| Control | Tool | Stage |
|---|---|---|
| Secret detection | `detect-private-key` (pre-commit-hooks) | pre-commit |
| YAML correctness | `yamllint` | pre-commit, CI |
| Ansible security rules | `ansible-lint` (safety profile) | pre-commit, CI |
| Dependency updates | Dependabot | Automated weekly PRs |
| Pinned Action SHAs | Manual + Dependabot | CI workflows |
| No persisted credentials in CI | `persist-credentials: false` | CI workflows |
| Minimal workflow permissions | `permissions: read-all` baseline | CI workflows |
| Conventional commit enforcement | `conventional-pre-commit` | pre-commit (commit-msg) |

## Scope

The following are **in scope** for vulnerability reports:

- Secrets or credentials accidentally committed or exposed
- CI/CD pipeline vulnerabilities (e.g., injection, privilege escalation)
- Insecure defaults in Ansible roles or `pip.conf` configuration shipped by this framework
- Dependency vulnerabilities with known exploits

The following are **out of scope**:

- Your specific infrastructure or downstream Ansible inventory
- Vulnerabilities in third-party tools (report those upstream)
- Issues requiring physical access to infrastructure
