"""Page registry for metiger.ca (Canada market).

Each entry maps a URL path to a self-contained Jinja template (under
templates/pages/) that extends base_page.html and carries its own SEO metadata
and JSON-LD via template blocks. app.py registers a simple render view for each
and builds the sitemap from these lists. Keep this the single source of truth
for CA marketing routes.
"""

# (url_path, template, endpoint_name, sitemap_priority)
SERVICE_PAGES = [
    ("/canada-electrical-estimating-services/", "pages/canada_electrical_estimating_services.html", "canada_estimating", "0.9"),
    ("/electrical-takeoff-services-canada/",     "pages/takeoff.html",           "takeoff_ca",     "0.8"),
    ("/commercial-electrical-estimating-canada/", "pages/commercial.html",        "commercial_ca",  "0.8"),
    ("/industrial-electrical-estimating-canada/", "pages/industrial.html",        "industrial_ca",  "0.8"),
    ("/electrical-bid-review-canada/",           "pages/bid_review.html",        "bid_review_ca",  "0.8"),
    ("/restaurant-electrical-estimating-canada/", "pages/restaurant.html",        "restaurant_ca",  "0.7"),
    ("/retail-electrical-estimating-canada/",    "pages/retail.html",            "retail_ca",      "0.7"),
    ("/municipal-utility-electrical-estimating-canada/", "pages/municipal_utility.html", "municipal_ca", "0.7"),
    ("/pricing/",       "pages/pricing.html",      "pricing",      "0.7"),
    ("/samples/",       "pages/samples.html",      "samples",      "0.6"),
    ("/case-studies/",  "pages/case_studies.html", "case_studies", "0.6"),
]

# (url_path, template, endpoint_name, sitemap_priority)
PROVINCE_PAGES = [
    ("/ontario-electrical-estimating-services/",              "pages/province_ontario.html",             "prov_on",  "0.6"),
    ("/alberta-electrical-estimating-services/",              "pages/province_alberta.html",             "prov_ab",  "0.6"),
    ("/british-columbia-electrical-estimating-services/",     "pages/province_british_columbia.html",    "prov_bc",  "0.6"),
    ("/nova-scotia-electrical-estimating-services/",          "pages/province_nova_scotia.html",         "prov_ns",  "0.6"),
    ("/new-brunswick-electrical-estimating-services/",        "pages/province_new_brunswick.html",       "prov_nb",  "0.6"),
    ("/manitoba-electrical-estimating-services/",             "pages/province_manitoba.html",            "prov_mb",  "0.6"),
    ("/saskatchewan-electrical-estimating-services/",         "pages/province_saskatchewan.html",        "prov_sk",  "0.6"),
    ("/quebec-electrical-estimating-services/",               "pages/province_quebec.html",              "prov_qc",  "0.6"),
    ("/prince-edward-island-electrical-estimating-services/", "pages/province_prince_edward_island.html","prov_pe",  "0.5"),
    ("/newfoundland-labrador-electrical-estimating-services/","pages/province_newfoundland_labrador.html","prov_nl", "0.5"),
]

# Static/bespoke routes to include in sitemap (rendered by dedicated views in app.py).
# (url_path, template, sitemap_priority) — template is relative to templates/ and is
# used to source the sitemap <lastmod> from the file's mtime.
CORE_PAGES = [
    ("/", "home.html", "1.0"),
    ("/contact/", "quote.html", "0.8"),
    ("/estimate-calculator", "estimate_calculator.html", "0.6"),
    ("/electrical-budget-guide", "budget_guide.html", "0.6"),
]

ALL_REGISTRY_PAGES = SERVICE_PAGES + PROVINCE_PAGES


def sitemap_entries():
    """Return list of (path, template) for every indexable page.

    template is relative to the templates/ directory; app.py derives each URL's
    <lastmod> from that file's modification time.
    """
    entries = [(path, tmpl) for path, tmpl, _prio in CORE_PAGES]
    for path, tmpl, _ep, _prio in ALL_REGISTRY_PAGES:
        entries.append((path, tmpl))
    return entries
