# ADR 0003: Secret references and envelope-encrypted provider material

- Status: Accepted for Phase 3 design
- Date: 2026-08-01

GitHub App private keys belong in the platform secret manager and are referenced by configuration. Any recoverable credential that must reside in PostgreSQL is encrypted by a `SecretCipher` abstraction backed by managed KMS envelope encryption. Rows store ciphertext, nonce/envelope metadata and key version only.

Decryption is limited to provider adapters, supports key rotation, and returns non-serializable secret values. Logs, errors, audit metadata, traces and RQ results use allowlists and redaction. No custom cryptographic primitive will be introduced.
