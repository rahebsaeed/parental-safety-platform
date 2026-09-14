# Security docs (partial)

The full threat model (Section 38 of the spec) covers subsystems that don't
exist yet (remote dashboard, database, alerts). It will be written
incrementally as each phase lands, rather than speculatively now.

What Phase 1 needs is covered in `docs/architecture/phase-1-discovery.md`
under "Security considerations" — privilege requirements for the ARP scan,
local-only storage, and the no-payload-data rule.
