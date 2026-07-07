#!/usr/bin/env bash
#
# ADR-028 enforcement (deterministic gate).
#
# The base `DomainException` is reserved for domain-framework invariants and
# must only be raised from within `src/building_blocks/domain/`. Everywhere else
# in `src/`, code MUST use the semantically specific subclass
# (DomainValidationException / BusinessRuleViolationException /
# DomainNotFoundException / DomainConflictException). See
# docs/adr/ADR-028-domain-exception-semantics.md.
#
# This check fails the pipeline if a raw `raise DomainException(...)` appears in
# production code outside the allowlisted directory. It matches only the base
# class — `raise DomainNotFoundException(` and the other subclasses do not match.
#
# Runs in CI (ci.yml lint job) and locally via `make lint`.

set -euo pipefail

# Match `raise DomainException(` with flexible whitespace; the trailing `(`
# excludes bare re-raises and ensures we only catch instantiations of the base.
PATTERN='raise[[:space:]]+DomainException[[:space:]]*\('
ALLOWED_DIR='src/building_blocks/domain/'

# grep exits 1 when there are no matches — that's the success case here, so guard it.
offenders="$(grep -rEn --include='*.py' "${PATTERN}" src/ | grep -v "${ALLOWED_DIR}" || true)"

if [[ -n "${offenders}" ]]; then
  echo "ADR-028 violation: raw 'raise DomainException(...)' found outside ${ALLOWED_DIR}"
  echo "The base DomainException is reserved for domain-framework invariants."
  echo "Use the specific subclass (DomainValidationException / BusinessRuleViolationException /"
  echo "DomainNotFoundException / DomainConflictException). See docs/adr/ADR-028-domain-exception-semantics.md"
  echo
  echo "${offenders}"
  exit 1
fi

echo "ADR-028 gate OK: no raw base DomainException raises outside ${ALLOWED_DIR}"
