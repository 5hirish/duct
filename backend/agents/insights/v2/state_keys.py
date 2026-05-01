"""Session state key constants for the ADK (v2) pipeline.

Keys use bare names (no 'temp:' prefix) so they work directly in ADK
instruction template placeholders: {goal}, {supplementary_data}, etc.
"""

STATE_GOAL = "goal"
STATE_CUSTOM_GOAL = "custom_goal"
STATE_MODE = "mode"
STATE_CUSTOMER_ID = "customer_id"
STATE_DATE_FROM = "date_from"
STATE_DATE_TO = "date_to"
STATE_GA4_PROPERTY_ID = "ga4_property_id"
STATE_GSC_SITE_URL = "gsc_site_url"
STATE_CONTEXT = "context"
STATE_CONNECTED_SRCS = "connected_sources"
STATE_ALL_BRIEFS = "all_briefs"
STATE_SUPPLEMENTARY = "supplementary_data"
STATE_SYNTHESIS_TEXT = "synthesis_text"
