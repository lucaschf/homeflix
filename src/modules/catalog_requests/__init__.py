"""Catalog Requests bounded context.

Tracks user-initiated requests to add titles to the catalog and
optional "notify when available" subscriptions. Exists primarily
to power the missing-from-catalog flow on the Collection Detail
page: each TMDB title that the platform doesn't yet host can be
flagged for inclusion and/or notification, and other bounded
contexts (Media) read this state via a cross-BC port.
"""
