"""Usage providers. Each provider module exposes:
    NAME                       provider id used by --provider
    default_homes(args)        -> {label: path} when the user gives no --home
    parse_homes(specs)         -> {label: path} from ["label=path", "path", ...]
    scan(homes)                -> (records, ratelimits)
        records    : list of (ts_iso_utc, account_label, model, input_tokens, cached_input_tokens, output_tokens, request_input_size, service_tier, tier_source)
                     where service_tier is standard, fast, or unknown and tier_source is direct, timeline, or unknown
        ratelimits : {account_label: [(ts_iso_utc, used_percent, resets_at_epoch)]}  weekly-window samples (may be empty)
Only the codex provider exists today; add a module here and register it in PROVIDERS.
"""
from . import codex
PROVIDERS = {codex.NAME: codex}
