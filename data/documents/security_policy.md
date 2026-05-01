# Information Security Policy

**Document ID:** sec-infosec-policy-v4  
**Category:** Security  
**Last Updated:** 2025-03-10  
**Owner:** Information Security (InfoSec)

## Purpose

This policy establishes the minimum security requirements for all Acme Corp employees, contractors, and systems to protect company data and ensure compliance with SOC 2 Type II and ISO 27001 requirements.

## Password and Authentication Requirements

### Passwords

- Minimum length: **16 characters**
- Must include: uppercase, lowercase, numbers, and special characters
- Must not reuse the last 10 passwords
- All passwords must be stored in **1Password** (personal vault or shared team vault)
- Sharing passwords via Slack, email, or any chat tool is strictly prohibited

### Multi-Factor Authentication (MFA)

MFA is **mandatory** for:
- All corporate SSO applications (Okta)
- AWS Console access
- GitHub Enterprise
- VPN access

Approved MFA methods: hardware security keys (YubiKey) or authenticator apps (Okta Verify, Google Authenticator). SMS-based MFA is not permitted.

## Device Security

### Managed Devices

All company-issued devices must:
- Run the latest macOS version within 30 days of release
- Have disk encryption (FileVault) enabled
- Have the Jamf MDM profile installed
- Never have corporate data stored in unencrypted form outside approved storage

### Personal Devices (BYOD)

Personal devices may not access production systems or handle customer data. Limited access to corporate email and calendar via managed apps is permitted with MDM enrollment.

## Data Classification

| Class | Description | Examples |
|---|---|---|
| **Public** | Approved for external sharing | Press releases, public docs |
| **Internal** | For employees only | Policies, internal guides |
| **Confidential** | Limited distribution | Financial data, contracts |
| **Restricted** | Strict need-to-know | PII, credentials, source code |

Restricted data must be encrypted at rest and in transit and may not be shared externally without InfoSec approval.

## Incident Reporting

Any suspected security incident (phishing email, unauthorized access, lost device) must be reported **immediately** to:

- Slack: **#security-incidents** (24/7 monitored)
- Email: security@acme-corp.example.com
- Emergency hotline: +1-800-ACME-SEC

**Do not attempt to investigate a suspected incident yourself.** Notify InfoSec first.

## Acceptable Use

Employees may not:
- Install unapproved software on company devices
- Connect company devices to public/untrusted Wi-Fi without VPN
- Access or exfiltrate customer data for non-business purposes
- Use personal cloud storage (Dropbox, personal Google Drive) for company data

## Compliance and Auditing

InfoSec conducts quarterly access reviews and annual security awareness training (mandatory). Non-compliance may result in disciplinary action up to and including termination.

## Contact

InfoSec Team: security@acme-corp.example.com | Slack #security-help
