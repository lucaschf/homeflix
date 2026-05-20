"""Notifications bounded context.

In-app inbox surface: every cross-BC handler that wants to ping
a specific user (e.g. ``catalog_requests`` after the requested
title lands in the catalog) writes a row through this BC and the
header bell renders it. Notifications are per-recipient — they
target a single ``usr_xxx`` external id rather than broadcasting
across the household — and are read-only from any module other
than their own; cross-BC dispatch flows through the publisher
port defined by each consumer BC (ADR-009).
"""
