# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest `main` | Yes |
| older tags | No |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, report them privately by emailing the maintainers at the address listed in the repository's profile, or by using [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) feature.

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

We will acknowledge receipt within **48 hours** and aim to provide a fix or mitigation within **7 days** for critical issues.

## Sensitive Files

The following files contain credentials and must **never** be committed to version control:

| File | Contents |
|------|----------|
| `.env` | API keys and configuration |
| `credentials.json` | Google OAuth client secret |
| `token.json` | YouTube access + refresh tokens |

All three are listed in `.gitignore`. If you accidentally commit any of these, revoke the credentials immediately and rotate them.

## Dependency Security

Dependencies are pinned in `requirements.txt`. Run `pip audit` or enable GitHub Dependabot to monitor for known CVEs in direct and transitive dependencies.

## API Key Hygiene

- Store all API keys in `.env`, never in source code.
- Use the most restrictive permissions possible for each API key.
- Rotate keys regularly and immediately after any potential exposure.
- The Pexels API key should be scoped read-only.
- The YouTube OAuth scope is limited to `youtube.upload` — it cannot read or delete existing content.
