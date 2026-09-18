# Shuttle Privacy Policy

**Effective date: September 18, 2026**

Shuttle is an open-source desktop application for accessing Amazon S3 through
AWS IAM Identity Center.

## Information Shuttle handles

Shuttle reads AWS profile configuration stored on the user's computer. This
configuration may include profile names, AWS account identifiers, role names,
regions, and IAM Identity Center URLs. Shuttle also handles S3 bucket names,
object paths, local file paths, and transfer settings needed to perform actions
requested by the user.

AWS IAM Identity Center login tokens are stored in the user's local
application-data directory and are used only until their AWS-provided expiration
time. Temporary AWS credentials remain in memory and are not persisted by
Shuttle. Saved jobs contain non-secret settings and are stored locally on the
user's computer.

## How information is used and transmitted

Shuttle uses this information only to authenticate with Amazon Web Services and
perform the S3 browsing and transfer operations requested by the user.
Authentication requests and file transfers occur directly between the user's
computer and Amazon Web Services.

When automatic update checks are enabled, Shuttle contacts GitHub to determine
whether a newer release is available. Users can disable automatic update checks
in Shuttle's settings. These requests are subject to the privacy practices of
GitHub.

## Data collection

Shuttle's developers do not receive, collect, store, sell, or share users'
personal information, AWS credentials, analytics, or details about transferred
files. Shuttle does not include advertising, analytics, telemetry, or tracking
services.

Amazon Web Services and GitHub may process information associated with requests
sent to their services under their respective privacy policies.

## Data retention and removal

Shuttle retains settings, saved jobs, and unexpired IAM Identity Center login
tokens locally on the user's computer. Users can remove this information by
deleting Shuttle's application-data directory.

## Contact

Questions or privacy requests can be submitted through the Shuttle issue
tracker:

https://github.com/aldi-f/shuttle/issues
