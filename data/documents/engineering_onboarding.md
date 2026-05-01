# Engineering Onboarding Guide

**Document ID:** eng-onboarding-v5  
**Category:** Engineering  
**Last Updated:** 2025-02-01  
**Owner:** Engineering Enablement

## Welcome to Engineering at Acme Corp

This guide covers everything you need to get your local development environment set up and make your first contribution within your first two weeks.

## Week 1: Environment Setup

### Prerequisites

- MacBook Pro (issued by IT on Day 1) with macOS 14+
- 1Password for secrets management — IT will provision your account
- GitHub Enterprise account linked to your Acme Corp email

### Step 1: Install Core Tools

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install core CLI tools
brew install git awscli terraform kubectl helm

# Install mise for language version management
brew install mise
mise install node@20 python@3.12 go@1.22
```

### Step 2: Clone the Monorepo

```bash
git clone git@github.acme-corp.example.com:acme/monorepo.git ~/code/acme
cd ~/code/acme
./scripts/bootstrap.sh   # Installs all dependencies and sets up pre-commit hooks
```

### Step 3: Configure AWS Access

1. Open 1Password and find the "AWS SSO" entry.
2. Run `aws configure sso` and follow prompts using the provided SSO URL.
3. Run `aws sso login --profile acme-dev` to authenticate.

### Step 4: Start Local Services

```bash
cd ~/code/acme
docker compose up -d   # Starts Postgres, Redis, and LocalStack
make dev               # Starts the API server on port 8080
```

The local API is available at `http://localhost:8080`. The dev dashboard is at `http://localhost:3000`.

## Week 2: Making Your First Contribution

### Branch Naming Convention

All branches must follow: `{type}/{ticket-id}-{short-description}`

Examples:
- `feat/ENG-1234-add-user-auth`
- `fix/ENG-5678-fix-null-pointer`
- `chore/ENG-9012-update-dependencies`

### Pull Request Process

1. Create your branch and push commits.
2. Open a PR against `main` in GitHub Enterprise.
3. PR titles must follow the format: `[ENG-XXXX] Brief description of change`.
4. Required reviewers: at least **2 engineers** from your team.
5. All CI checks (lint, unit tests, integration tests) must pass before merge.
6. PRs are automatically merged via the merge queue once approved.

### Code Review Guidelines

- Respond to review comments within 1 business day.
- Use the "Request Changes" option only for blocking issues.
- Prefer suggestions over mandates in review comments.

## Key Contacts

| Role | Name | Slack |
|---|---|---|
| Engineering Enablement | Platform Team | #eng-enablement |
| Security | AppSec Team | #security-help |
| Infrastructure | Infra Team | #infra-oncall |

## Additional Resources

- [Architecture Decision Records (ADRs)](https://wiki.acme-corp.example.com/engineering/adrs)
- [Runbooks](https://wiki.acme-corp.example.com/engineering/runbooks)
- [Engineering Blog](https://engineering.acme-corp.example.com)
