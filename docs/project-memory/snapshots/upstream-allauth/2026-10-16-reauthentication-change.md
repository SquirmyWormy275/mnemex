# Upstream authentication compatibility observation

Primary source: [allauth 65.20.0 release announcement](https://allauth.org/news/2026/10/django-allauth-65.20.0-released/), published October 16, 2026; consulted during this execution. This is a paraphrased source summary, not a verbatim release-note copy.

Version 65.20 requires an explicit reauthentication ceremony for protected views even when an initial login was recent. Its release also ends Python 3.10 support. MNEMEX's existing allowed dependency range selected 65.20 on current Python 3.13 CI, while the earlier isolated environment had 65.19.7.

The unchanged MNEMEX application main reproduced four enrollment-test failures under 65.20: those tests tried to read the enrollment form/secret without performing the newly required password confirmation. The existing application confirmation route already supports the intended flow. The test compatibility update performs that real route and retains all prior MFA encryption, notification and privilege assertions; no application setting or security gate was disabled. A new wrong-password test verifies that enrollment secrets remain undisclosed.

The memory tool remains standard-library-only and independently verified on Python 3.10 and 3.13; this does not claim that allauth 65.20 supports Python 3.10. Older supported dependency resolution remains separate.
