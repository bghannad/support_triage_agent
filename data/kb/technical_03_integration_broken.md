# Category: technical
# Title: Third-party integration stopped working

When a connected integration (Slack, Google Drive, etc.) stops working, the most common cause is
an expired or revoked OAuth token — usually because the customer changed their password on the
third-party service, or an IT admin revoked app access org-wide. The fix is almost always
reconnecting the integration from Settings > Integrations, which triggers a fresh OAuth flow. If
reconnecting fails with an error, capture the exact error message — that's needed to distinguish
a customer-side permissions issue from an actual outage on our end.
