# Category: technical
# Title: Files/data not syncing across devices

Sync issues are most commonly caused by (1) the local app being on an outdated version, (2) a
stale auth token after a password change, requiring re-login, or (3) a temporary regional outage
of the sync service. First step: check the status page for known incidents. Second: have the
customer log out and back in on the affected device to refresh their token. If sync is broken
account-wide (not just one device) and there's no active incident, this should be escalated to
engineering with the account ID and approximate time syncing stopped.
