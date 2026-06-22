#!/usr/bin/env python3
"""
AWS Account Info Script
Gathers key account information and displays it in a plain-text,
email-friendly format. Designed to run in AWS CloudShell with full admin rights.
"""

import boto3
import datetime
import sys

from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError


def get_account_id():
    """Retrieve the 12-digit AWS account ID."""
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return identity["Account"]
    except (ClientError, NoCredentialsError, BotoCoreError) as e:
        return f"Error: Could not retrieve account ID. {e}"


def get_root_mfa_status():
    """Check if the root account has MFA enabled."""
    try:
        iam = boto3.client("iam")
        summary = iam.get_account_summary()
        mfa_enabled = summary["SummaryMap"].get("AccountMFAEnabled", 0)
        if mfa_enabled == 1:
            return "Root MFA: Enabled"
        else:
            return "Root MFA: Not Enabled"
    except (ClientError, BotoCoreError) as e:
        return f"Error: Could not retrieve root MFA status. {e}"


def get_admin_users_mfa():
    """Identify enabled IAM users with AdministratorAccess and their MFA status."""
    try:
        iam = boto3.client("iam")
        paginator = iam.get_paginator("list_users")
        admin_users = []

        for page in paginator.paginate():
            for user in page["Users"]:
                username = user["UserName"]

                # Check if user is active (has login profile or active access keys)
                is_active = False

                # Check login profile
                try:
                    iam.get_login_profile(UserName=username)
                    is_active = True
                except ClientError as e:
                    if e.response["Error"]["Code"] != "NoSuchEntity":
                        pass  # Other error, skip login profile check

                # Check active access keys if no login profile
                if not is_active:
                    try:
                        keys = iam.list_access_keys(UserName=username)
                        for key in keys.get("AccessKeyMetadata", []):
                            if key.get("Status") == "Active":
                                is_active = True
                                break
                    except ClientError:
                        pass

                if not is_active:
                    continue

                # Check for AdministratorAccess policy
                has_admin = False

                # Check directly attached policies
                try:
                    attached = iam.list_attached_user_policies(UserName=username)
                    for policy in attached.get("AttachedPolicies", []):
                        if policy.get("PolicyArn") == "arn:aws:iam::aws:policy/AdministratorAccess":
                            has_admin = True
                            break
                except ClientError:
                    pass

                # Check group policies if not directly attached
                if not has_admin:
                    try:
                        groups = iam.list_groups_for_user(UserName=username)
                        for group in groups.get("Groups", []):
                            group_policies = iam.list_attached_group_policies(
                                GroupName=group["GroupName"]
                            )
                            for policy in group_policies.get("AttachedPolicies", []):
                                if policy.get("PolicyArn") == "arn:aws:iam::aws:policy/AdministratorAccess":
                                    has_admin = True
                                    break
                            if has_admin:
                                break
                    except ClientError:
                        pass

                if not has_admin:
                    continue

                # Check MFA status
                try:
                    mfa_devices = iam.list_mfa_devices(UserName=username)
                    if mfa_devices.get("MFADevices"):
                        admin_users.append(f"{username} - MFA: Enabled")
                    else:
                        admin_users.append(f"{username} - MFA: Not Enabled")
                except ClientError:
                    admin_users.append(f"{username} - MFA: Not Enabled")

        if not admin_users:
            return "No IAM users with AdministratorAccess found"

        return "\n".join(admin_users)

    except (ClientError, BotoCoreError) as e:
        return f"Error: Could not retrieve IAM user information. {e}"


def get_org_membership():
    """Check if the account belongs to an AWS Organization."""
    try:
        org = boto3.client("organizations")
        response = org.describe_organization()
        organization = response["Organization"]

        mgmt_email = organization.get("MasterAccountEmail", "N/A")
        mgmt_id = organization.get("MasterAccountId", "N/A")

        lines = [
            f"Management Account: {mgmt_email}",
            f"Management Account ID: {mgmt_id}",
        ]
        return "\n".join(lines)

    except ClientError as e:
        if e.response["Error"]["Code"] == "AWSOrganizationsNotInUseException":
            return "Account is not part of an AWS Organization"
        return f"Error: Could not retrieve Organization information. {e}"
    except BotoCoreError as e:
        return f"Error: Could not retrieve Organization information. {e}"


def get_identity_center():
    """Check if IAM Identity Center is enabled and in which region."""
    # Get current account for ownership check
    try:
        sts = boto3.client("sts")
        current_account = sts.get_caller_identity()["Account"]
    except (ClientError, BotoCoreError):
        current_account = None

    # Get default region
    session = boto3.session.Session()
    default_region = session.region_name or "us-east-1"

    # Regions to check (current first, then common ones)
    regions_to_check = [default_region]
    for r in ["us-east-1", "eu-west-1", "eu-central-1", "us-west-2", "ap-southeast-1", "ap-northeast-1"]:
        if r not in regions_to_check:
            regions_to_check.append(r)

    for region in regions_to_check:
        try:
            sso_admin = boto3.client("sso-admin", region_name=region)
            response = sso_admin.list_instances()
            instances = response.get("Instances", [])

            if instances:
                instance = instances[0]
                owner_account = instance.get("OwnerAccountId")

                # Extract region from ARN or use the region we queried
                instance_arn = instance.get("InstanceArn", "")
                arn_parts = instance_arn.split(":")
                instance_region = arn_parts[3] if len(arn_parts) > 3 and arn_parts[3] else region

                # If instance is owned by a different account, it's an org-level instance
                if owner_account and current_account and owner_account != current_account:
                    lines = [
                        "IAM Identity Center: Not Enabled in this account",
                        f"Organization has IAM Identity Center enabled (managed by account {owner_account}, region: {instance_region})",
                    ]
                    return "\n".join(lines)

                return f"IAM Identity Center: Enabled\nRegion: {instance_region}"

        except (ClientError, BotoCoreError):
            continue

    return "IAM Identity Center: Not Enabled in this account"


def get_past_due_payments():
    """Check for past due invoices on the account."""
    try:
        # Get account ID for the selector
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
    except (ClientError, BotoCoreError) as e:
        return f"Error: Could not retrieve billing information. Unable to determine account ID. {e}"

    try:
        invoicing = boto3.client("invoicing", region_name="us-east-1")
        today = datetime.date.today()

        # API limits TimeInterval to 1 month max.
        # Use BillingPeriod for current month to check current payment status.
        response = invoicing.list_invoice_summaries(
            Selector={
                "ResourceType": "ACCOUNT_ID",
                "Value": account_id
            },
            Filter={
                "BillingPeriod": {
                    "Month": today.month,
                    "Year": today.year
                }
            }
        )

        invoices = response.get("InvoiceSummaries", [])
        past_due = []

        def check_invoices(invoice_list):
            for invoice in invoice_list:
                due_date = invoice.get("DueDate")
                if not due_date:
                    continue

                # due_date may be a datetime object or string
                if isinstance(due_date, datetime.datetime):
                    due_date_obj = due_date.date()
                elif isinstance(due_date, str):
                    due_date_obj = datetime.date.fromisoformat(due_date[:10])
                else:
                    continue

                if due_date_obj < today:
                    currency_info = invoice.get("BaseCurrencyAmount", invoice.get("PaymentCurrencyAmount", {}))
                    amount = currency_info.get("TotalAmount", "N/A")
                    currency = currency_info.get("CurrencyCode", "N/A")
                    past_due.append(f"Amount: {amount} {currency} - Due: {due_date_obj.isoformat()}")

        check_invoices(invoices)

        # Check for additional pages
        while response.get("NextToken"):
            response = invoicing.list_invoice_summaries(
                Selector={
                    "ResourceType": "ACCOUNT_ID",
                    "Value": account_id
                },
                Filter={
                    "BillingPeriod": {
                        "Month": today.month,
                        "Year": today.year
                    }
                },
                NextToken=response["NextToken"]
            )
            check_invoices(response.get("InvoiceSummaries", []))

        if not past_due:
            return "No past due payments"

        return "\n".join(past_due)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if "AccessDenied" in error_code or "Unauthorized" in error_code:
            return "Error: Could not retrieve billing information. Access denied - billing permissions required."
        return f"Error: Could not retrieve billing information. {e}"
    except (BotoCoreError, Exception) as e:
        return f"Error: Could not retrieve billing information. {e}"


def format_section(title, content):
    """Format a section with uppercase header, dashes separator, and content."""
    return f"\n{title.upper()}\n---\n{content}\n"


def main():
    account_id = get_account_id()
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Print report header
    print("=" * 40)
    print(f"AWS ACCOUNT REPORT - {account_id}")
    print(f"Generated: {timestamp}")
    print("=" * 40)

    # Section 1: Account ID
    print(format_section("Account ID", account_id))

    # Section 2: Root MFA Status
    print(format_section("Root MFA Status", get_root_mfa_status()))

    # Section 3: IAM Users with Administrator Access
    print(format_section("IAM Users with Administrator Access", get_admin_users_mfa()))

    # Section 4: Organization Membership
    print(format_section("Organization Membership", get_org_membership()))

    # Section 5: IAM Identity Center Status
    print(format_section("IAM Identity Center Status", get_identity_center()))

    # Section 6: Past Due Payments
    print(format_section("Past Due Payments", get_past_due_payments()))


if __name__ == "__main__":
    main()
    sys.exit(0)
