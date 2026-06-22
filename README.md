# AWS Account Info Script

A Python script designed to run in AWS CloudShell that gathers key account information and displays it in a plain-text, email-friendly format.

## Usage

Open AWS CloudShell and paste the following commands:

```bash
git clone https://github.com/apserdev/apser-check_account.git
cd apser-check_account
python3 check_account.py
```

## AWS API Calls Made

The script makes the following **read-only** API calls. No data is modified.

| Section | API Call | Purpose |
|---------|----------|---------|
| Account ID | `sts:GetCallerIdentity` | Get the 12-digit account ID |
| Root MFA | `iam:GetAccountSummary` | Check if root account has MFA enabled |
| Admin Users | `iam:ListUsers` | List all IAM users |
| Admin Users | `iam:GetLoginProfile` | Check if user has console access |
| Admin Users | `iam:ListAccessKeys` | Check if user has active access keys |
| Admin Users | `iam:ListAttachedUserPolicies` | Check for directly attached AdministratorAccess |
| Admin Users | `iam:ListGroupsForUser` | Get user's group memberships |
| Admin Users | `iam:ListAttachedGroupPolicies` | Check groups for AdministratorAccess |
| Admin Users | `iam:ListMFADevices` | Check if admin user has MFA enabled |
| Organization | `organizations:DescribeOrganization` | Get org membership and management account info |
| Identity Center | `sso-admin:ListInstances` | Check if IAM Identity Center is enabled |
| Past Due Payments | `invoicing:ListInvoiceSummaries` | Check for past due invoices |

## Minimum IAM Policy Required

The following IAM policy grants the minimum permissions needed to run this script:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AccountInfo",
            "Effect": "Allow",
            "Action": [
                "sts:GetCallerIdentity"
            ],
            "Resource": "*"
        },
        {
            "Sid": "RootMFACheck",
            "Effect": "Allow",
            "Action": [
                "iam:GetAccountSummary"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AdminUsersCheck",
            "Effect": "Allow",
            "Action": [
                "iam:ListUsers",
                "iam:GetLoginProfile",
                "iam:ListAccessKeys",
                "iam:ListAttachedUserPolicies",
                "iam:ListGroupsForUser",
                "iam:ListAttachedGroupPolicies",
                "iam:ListMFADevices"
            ],
            "Resource": "*"
        },
        {
            "Sid": "OrganizationCheck",
            "Effect": "Allow",
            "Action": [
                "organizations:DescribeOrganization"
            ],
            "Resource": "*"
        },
        {
            "Sid": "IdentityCenterCheck",
            "Effect": "Allow",
            "Action": [
                "sso:ListInstances"
            ],
            "Resource": "*"
        },
        {
            "Sid": "BillingCheck",
            "Effect": "Allow",
            "Action": [
                "invoicing:ListInvoiceSummaries"
            ],
            "Resource": "*"
        }
    ]
}
```

## Notes

- All API calls are **read-only** — the script does not create, modify, or delete any resources.
- The script handles errors gracefully per section — if one check fails due to missing permissions, the rest still execute.
- `sts:GetCallerIdentity` does not actually require any IAM permissions (it always works for any authenticated caller), but is listed for transparency.
- The billing check (`invoicing:ListInvoiceSummaries`) may require that billing access is enabled for IAM users in the account's billing settings.
- Identity Center check queries multiple AWS regions to find the instance.
