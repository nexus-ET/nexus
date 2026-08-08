"""Metro / campus-local employer & job packs for Future Insights."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from app.schemas.nexus_intel import (
    FutureInsightsCityLiving,
    FutureInsightsEmployer,
    FutureInsightsJob,
)

_AS_OF = date.today().isoformat()


def _logo_from_website(website_url: str) -> str | None:
    try:
        host = urlparse(website_url).hostname or ""
        host = host.removeprefix("www.")
        if not host:
            return None
        return f"https://www.google.com/s2/favicons?domain={host}&sz=128"
    except Exception:
        return None


def _employer(
    name: str,
    website_url: str,
    city_or_region: str | None = None,
    sectors: list[str] | None = None,
) -> FutureInsightsEmployer:
    return FutureInsightsEmployer(
        name=name,
        website_url=website_url,
        logo_url=_logo_from_website(website_url),
        city_or_region=city_or_region,
        sectors=sectors or [],
    )


def _job(
    title: str,
    employer_name: str,
    location: str,
    apply_url: str,
    disciplines: list[str] | None = None,
) -> FutureInsightsJob:
    return FutureInsightsJob(
        title=title,
        employer_name=employer_name,
        location=location,
        apply_url=apply_url,
        program_disciplines=disciplines or [],
        as_of=_AS_OF,
    )


# metro_key -> pack. aliases match institution name, city, or state text.
METRO_PACKS: dict[str, dict] = {
    "los-angeles": {
        "label": "Los Angeles, CA",
        "country_codes": {"US"},
        "aliases": [
            "los angeles",
            "ucla",
            "university of california, los angeles",
            "university of california los angeles",
            "usc",
            "university of southern california",
            "caltech",
            "california institute of technology",
            "pasadena",
            "westwood",
            "hollywood hills",
            "long beach",
        ],
        "employers": [
            _employer("Netflix", "https://jobs.netflix.com", "Los Angeles", ["tech", "media"]),
            _employer("The Walt Disney Company", "https://jobs.disneycareers.com", "Burbank / LA", ["media", "business"]),
            _employer("SpaceX", "https://www.spacex.com", "Hawthorne, LA", ["aerospace", "engineering"]),
            _employer("Amgen", "https://careers.amgen.com", "Thousand Oaks / LA", ["biotech", "pharma"]),
            _employer("Deloitte", "https://www2.deloitte.com", "Los Angeles", ["consulting"]),
            _employer("Google", "https://careers.google.com", "Playa Vista / LA", ["tech"]),
        ],
        "jobs": [
            _job("Software Engineer (New Grad)", "Netflix", "Los Angeles, CA", "https://jobs.netflix.com", ["CS", "SOFTWARE"]),
            _job("Early Career Engineer", "SpaceX", "Hawthorne, CA", "https://www.spacex.com/careers", ["ENGINEERING", "AEROSPACE", "MECHANICAL"]),
            _job("Analyst / Associate", "Deloitte", "Los Angeles, CA", "https://www2.deloitte.com/careers", ["BUSINESS", "CONSULTING"]),
            _job("Rotational / Early Career", "The Walt Disney Company", "Burbank, CA", "https://jobs.disneycareers.com", ["BUSINESS", "MEDIA", "HOSPITALITY"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $1,000–$1,600 (shared near Westwood/Koreatown)",
            private_rent_monthly="USD $2,200–$3,500+ (1BR near UCLA / Santa Monica)",
            transit_index_note="Metro + Big Blue Bus / BruinBus; car still common for many internships",
            grocery_index_note="Moderate-high; Trader Joe’s / ethnic markets help stretch budgets",
            climate_snapshot="Mediterranean — mild winters, dry summers; wildfire/smoke seasons",
            safety_snapshot="Campus security strong; neighbourhood choice matters off-campus",
        ),
    },
    "san-francisco-bay": {
        "label": "San Francisco Bay Area, CA",
        "country_codes": {"US"},
        "aliases": [
            "san francisco",
            "stanford",
            "berkeley",
            "university of california, berkeley",
            "uc berkeley",
            "santa clara",
            "san jose",
            "palo alto",
            "silicon valley",
            "bay area",
        ],
        "employers": [
            _employer("Google", "https://careers.google.com", "Mountain View", ["tech"]),
            _employer("Meta", "https://www.metacareers.com", "Menlo Park", ["tech"]),
            _employer("Apple", "https://www.apple.com/careers", "Cupertino", ["tech"]),
            _employer("Salesforce", "https://www.salesforce.com/company/careers", "San Francisco", ["tech", "saas"]),
            _employer("Genentech", "https://www.gene.com/careers", "South San Francisco", ["biotech"]),
        ],
        "jobs": [
            _job("Software Engineering New Grad", "Google", "Bay Area, CA", "https://careers.google.com", ["CS", "SOFTWARE"]),
            _job("University Grad Software Engineer", "Meta", "Menlo Park, CA", "https://www.metacareers.com", ["CS", "SOFTWARE"]),
            _job("Early Career Analyst", "Salesforce", "San Francisco, CA", "https://www.salesforce.com/company/careers", ["BUSINESS", "CS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $1,200–$2,000 (shared)",
            private_rent_monthly="USD $2,800–$4,500+ (1BR core Bay)",
            transit_index_note="BART/Caltrain/Muni; many tech shuttles",
            grocery_index_note="High; cooking at home is essential",
            climate_snapshot="Cool summers near SF; hotter inland East Bay / South Bay",
            safety_snapshot="Campus areas generally fine; city-centre awareness needed",
        ),
    },
    "new-york": {
        "label": "New York City Metro, NY",
        "country_codes": {"US"},
        "aliases": [
            "new york",
            "nyc",
            "columbia",
            "nyu",
            "new york university",
            "cornell tech",
            "brooklyn",
            "manhattan",
        ],
        "employers": [
            _employer("JPMorgan Chase", "https://careers.jpmorgan.com", "New York", ["finance"]),
            _employer("Goldman Sachs", "https://www.goldmansachs.com/careers", "New York", ["finance"]),
            _employer("Google", "https://careers.google.com", "New York", ["tech"]),
            _employer("IBM", "https://www.ibm.com/careers", "New York / Armonk", ["tech"]),
            _employer("Deloitte", "https://www2.deloitte.com", "New York", ["consulting"]),
        ],
        "jobs": [
            _job("Investment Banking Analyst", "JPMorgan Chase", "New York, NY", "https://careers.jpmorgan.com", ["FINANCE", "BUSINESS", "ECONOMICS"]),
            _job("Software Engineering New Grad", "Google", "New York, NY", "https://careers.google.com", ["CS", "SOFTWARE"]),
            _job("Business Analyst", "Deloitte", "New York, NY", "https://www2.deloitte.com/careers", ["BUSINESS", "CONSULTING"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $1,200–$2,000 (shared / roommates)",
            private_rent_monthly="USD $3,000–$5,000+ (Manhattan/Brooklyn 1BR)",
            transit_index_note="Subway-first city; unlimited MetroCard budgeting is standard",
            grocery_index_note="High; borough markets help",
            climate_snapshot="Four seasons; humid summers, cold winters",
            safety_snapshot="Very campus-dependent; stick to well-trafficked areas at night",
        ),
    },
    "boston": {
        "label": "Boston / Cambridge, MA",
        "country_codes": {"US"},
        "aliases": [
            "boston",
            "cambridge",
            "mit",
            "massachusetts institute of technology",
            "harvard",
            "northeastern",
            "boston university",
            "tufts",
        ],
        "employers": [
            _employer("Google", "https://careers.google.com", "Cambridge, MA", ["tech"]),
            _employer("Microsoft", "https://careers.microsoft.com", "Cambridge / Boston", ["tech"]),
            _employer("Vertex Pharmaceuticals", "https://www.vrtx.com/careers", "Boston", ["biotech"]),
            _employer("State Street", "https://www.statestreet.com/careers", "Boston", ["finance"]),
            _employer("HubSpot", "https://www.hubspot.com/careers", "Cambridge", ["tech", "saas"]),
        ],
        "jobs": [
            _job("Software Engineering New Grad", "Google", "Cambridge, MA", "https://careers.google.com", ["CS", "SOFTWARE"]),
            _job("Early Career Scientist / Analyst", "Vertex Pharmaceuticals", "Boston, MA", "https://www.vrtx.com/careers", ["BIOTECH", "LIFE SCIENCES", "CHEMISTRY"]),
            _job("Graduate Analyst", "State Street", "Boston, MA", "https://www.statestreet.com/careers", ["FINANCE", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $1,000–$1,700 (shared)",
            private_rent_monthly="USD $2,400–$3,800 (Cambridge/Boston 1BR)",
            transit_index_note="MBTA T + buses; walkable campus cores",
            grocery_index_note="Moderate-high",
            climate_snapshot="Cold snowy winters; mild summers",
            safety_snapshot="Generally strong campus security; standard urban awareness",
        ),
    },
    "seattle": {
        "label": "Seattle, WA",
        "country_codes": {"US"},
        "aliases": ["seattle", "university of washington", "uw seattle", "redmond", "bellevue"],
        "employers": [
            _employer("Amazon", "https://www.amazon.jobs", "Seattle", ["tech"]),
            _employer("Microsoft", "https://careers.microsoft.com", "Redmond", ["tech"]),
            _employer("Boeing", "https://jobs.boeing.com", "Seattle / Everett", ["aerospace", "engineering"]),
            _employer("Starbucks", "https://www.starbucks.com/careers", "Seattle", ["business", "retail"]),
        ],
        "jobs": [
            _job("SDE New Grad", "Amazon", "Seattle, WA", "https://www.amazon.jobs", ["CS", "SOFTWARE"]),
            _job("University Graduate", "Microsoft", "Redmond, WA", "https://careers.microsoft.com", ["CS", "SOFTWARE"]),
            _job("Early Career Engineer", "Boeing", "Seattle area, WA", "https://jobs.boeing.com", ["ENGINEERING", "AEROSPACE"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $900–$1,500 (shared)",
            private_rent_monthly="USD $2,000–$3,200 (1BR)",
            transit_index_note="Link light rail + buses; growing bike network",
            grocery_index_note="Moderate-high",
            climate_snapshot="Mild, rainy winters; dry summers",
            safety_snapshot="Campus areas generally fine; downtown variation",
        ),
    },
    "chicago": {
        "label": "Chicago, IL",
        "country_codes": {"US"},
        "aliases": ["chicago", "northwestern", "university of chicago", "uic", "illinois institute of technology"],
        "employers": [
            _employer("McKinsey & Company", "https://www.mckinsey.com/careers", "Chicago", ["consulting"]),
            _employer("Boeing", "https://jobs.boeing.com", "Chicago", ["aerospace"]),
            _employer("CME Group", "https://www.cmegroup.com/careers", "Chicago", ["finance"]),
            _employer("Accenture", "https://www.accenture.com/careers", "Chicago", ["consulting", "tech"]),
        ],
        "jobs": [
            _job("Business Analyst", "McKinsey & Company", "Chicago, IL", "https://www.mckinsey.com/careers", ["BUSINESS", "CONSULTING"]),
            _job("Technology Analyst", "Accenture", "Chicago, IL", "https://www.accenture.com/careers", ["CS", "IT", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="USD $800–$1,300 (shared)",
            private_rent_monthly="USD $1,800–$2,800 (1BR)",
            transit_index_note="CTA L + buses; winter commute planning matters",
            grocery_index_note="Moderate",
            climate_snapshot="Cold windy winters; humid summers",
            safety_snapshot="Neighbourhood-specific — use university housing guidance",
        ),
    },
    "toronto": {
        "label": "Toronto, ON",
        "country_codes": {"CA"},
        "aliases": ["toronto", "university of toronto", "uoft", "york university", "ryerson", "toronto metropolitan", "mississauga"],
        "employers": [
            _employer("Shopify", "https://www.shopify.com/careers", "Toronto", ["tech"]),
            _employer("RBC", "https://jobs.rbc.com", "Toronto", ["finance"]),
            _employer("TD Bank", "https://jobs.td.com", "Toronto", ["finance"]),
            _employer("Google", "https://careers.google.com", "Toronto", ["tech"]),
            _employer("CGI", "https://www.cgi.com/careers", "Toronto", ["tech", "consulting"]),
        ],
        "jobs": [
            _job("Software Engineer (New Grad)", "Shopify", "Toronto, ON", "https://www.shopify.com/careers", ["CS", "SOFTWARE"]),
            _job("Graduate Analyst", "RBC", "Toronto, ON", "https://jobs.rbc.com", ["FINANCE", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="CAD $900–$1,400 (shared)",
            private_rent_monthly="CAD $2,000–$3,000 (1BR downtown/midtown)",
            transit_index_note="TTC subway/streetcar; PRESTO card",
            grocery_index_note="Moderate-high",
            climate_snapshot="Cold winters; humid summers",
            safety_snapshot="Generally safe student neighbourhoods near U of T / York",
        ),
    },
    "vancouver": {
        "label": "Vancouver, BC",
        "country_codes": {"CA"},
        "aliases": ["vancouver", "ubc", "university of british columbia", "sfu", "simon fraser", "burnaby"],
        "employers": [
            _employer("Amazon", "https://www.amazon.jobs", "Vancouver", ["tech"]),
            _employer("Microsoft", "https://careers.microsoft.com", "Vancouver", ["tech"]),
            _employer("EA (Electronic Arts)", "https://www.ea.com/careers", "Burnaby / Vancouver", ["gaming", "tech"]),
            _employer("HSBC Canada", "https://www.hsbc.ca/careers", "Vancouver", ["finance"]),
        ],
        "jobs": [
            _job("SDE New Grad", "Amazon", "Vancouver, BC", "https://www.amazon.jobs", ["CS", "SOFTWARE"]),
            _job("Software Engineer New Grad", "EA (Electronic Arts)", "Burnaby, BC", "https://www.ea.com/careers", ["CS", "GAMING"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="CAD $900–$1,500 (shared)",
            private_rent_monthly="CAD $2,200–$3,200 (1BR)",
            transit_index_note="SkyTrain + buses; UBC strong transit links",
            grocery_index_note="High vs Canadian averages",
            climate_snapshot="Mild rainy winters; pleasant summers",
            safety_snapshot="Generally very safe student areas",
        ),
    },
    "london": {
        "label": "London, UK",
        "country_codes": {"UK"},
        "aliases": [
            "london",
            "ucl",
            "university college london",
            "imperial",
            "lse",
            "king's college",
            "kings college",
            "queen mary",
            "city university of london",
        ],
        "employers": [
            _employer("HSBC", "https://www.hsbc.com/careers", "London", ["finance"]),
            _employer("Barclays", "https://home.barclays/careers", "London", ["finance"]),
            _employer("Google", "https://careers.google.com", "London", ["tech"]),
            _employer("DeepMind", "https://deepmind.google/careers", "London", ["tech", "ai"]),
            _employer("Deloitte", "https://www2.deloitte.com", "London", ["consulting"]),
        ],
        "jobs": [
            _job("Graduate Analyst", "HSBC", "London, UK", "https://www.hsbc.com/careers", ["FINANCE", "BUSINESS"]),
            _job("Software Engineering New Grad", "Google", "London, UK", "https://careers.google.com", ["CS", "SOFTWARE"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="£700–£1,100 (zone 2–4 shared)",
            private_rent_monthly="£1,800–£2,800+ (1BR central/zone 1–2)",
            transit_index_note="Tube/Overground; Student Oyster / 18+ Student Railcard",
            grocery_index_note="High in central London",
            climate_snapshot="Mild, damp; grey winters",
            safety_snapshot="Standard major-city awareness; campus areas generally fine",
        ),
    },
    "sydney": {
        "label": "Sydney, NSW",
        "country_codes": {"AU"},
        "aliases": ["sydney", "university of sydney", "unsw", "uts", "macquarie university"],
        "employers": [
            _employer("Atlassian", "https://www.atlassian.com/company/careers", "Sydney", ["tech"]),
            _employer("Commonwealth Bank", "https://www.commbank.com.au/about-us/careers.html", "Sydney", ["finance"]),
            _employer("Google", "https://careers.google.com", "Sydney", ["tech"]),
            _employer("Deloitte", "https://www2.deloitte.com", "Sydney", ["consulting"]),
        ],
        "jobs": [
            _job("Graduate Software Engineer", "Atlassian", "Sydney, NSW", "https://www.atlassian.com/company/careers", ["CS", "SOFTWARE"]),
            _job("Graduate Program", "Commonwealth Bank", "Sydney, NSW", "https://www.commbank.com.au/about-us/careers.html", ["FINANCE", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="AUD $900–$1,400 (shared)",
            private_rent_monthly="AUD $2,200–$3,200 (1BR inner)",
            transit_index_note="Trains + buses + ferries; Opal card",
            grocery_index_note="Moderate-high",
            climate_snapshot="Warm summers; mild winters",
            safety_snapshot="High livability; standard urban awareness",
        ),
    },
    "melbourne": {
        "label": "Melbourne, VIC",
        "country_codes": {"AU"},
        "aliases": ["melbourne", "university of melbourne", "monash", "rmit", "deakin"],
        "employers": [
            _employer("ANZ", "https://www.anz.com.au/careers", "Melbourne", ["finance"]),
            _employer("Telstra", "https://careers.telstra.com", "Melbourne", ["telecom", "tech"]),
            _employer("Deloitte", "https://www2.deloitte.com", "Melbourne", ["consulting"]),
            _employer("BHP", "https://www.bhp.com/careers", "Melbourne", ["resources", "engineering"]),
        ],
        "jobs": [
            _job("Graduate Program", "ANZ", "Melbourne, VIC", "https://www.anz.com.au/careers", ["FINANCE", "BUSINESS"]),
            _job("Graduate Technology", "Telstra", "Melbourne, VIC", "https://careers.telstra.com", ["CS", "IT"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="AUD $800–$1,300 (shared)",
            private_rent_monthly="AUD $1,900–$2,800 (1BR)",
            transit_index_note="Trams + trains; myki card",
            grocery_index_note="Moderate",
            climate_snapshot="Four seasons in a day reputation — variable weather",
            safety_snapshot="Generally very safe student suburbs",
        ),
    },
    "berlin": {
        "label": "Berlin, Germany",
        "country_codes": {"DE"},
        "aliases": ["berlin", "tu berlin", "humboldt", "freie universität", "freie universitat"],
        "employers": [
            _employer("SAP", "https://jobs.sap.com", "Berlin", ["tech"]),
            _employer("Zalando", "https://jobs.zalando.com", "Berlin", ["tech", "commerce"]),
            _employer("Siemens", "https://jobs.siemens.com", "Berlin", ["engineering"]),
            _employer("Delivery Hero", "https://careers.deliveryhero.com", "Berlin", ["tech"]),
        ],
        "jobs": [
            _job("Graduate / Working Student (Tech)", "Zalando", "Berlin, Germany", "https://jobs.zalando.com", ["CS", "SOFTWARE"]),
            _job("Early Career Engineer", "Siemens", "Berlin, Germany", "https://jobs.siemens.com", ["ENGINEERING"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="EUR €400–€700 (WG)",
            private_rent_monthly="EUR €900–€1,500 (1BR)",
            transit_index_note="Excellent U/S-Bahn; semester ticket common",
            grocery_index_note="Moderate; discounters help",
            climate_snapshot="Cold winters; mild summers",
            safety_snapshot="Very safe overall",
        ),
    },
    "tokyo": {
        "label": "Tokyo, Japan",
        "country_codes": {"JP"},
        "aliases": ["tokyo", "university of tokyo", "todai", "waseda", "keio", "tokyo institute of technology", "science tokyo"],
        "employers": [
            _employer("Sony", "https://www.sony.com/en/jobs", "Tokyo", ["tech", "electronics"]),
            _employer("Rakuten", "https://corp.rakuten.co.jp/careers", "Tokyo", ["tech", "commerce"]),
            _employer("SoftBank", "https://group.softbank/en/careers", "Tokyo", ["tech", "telecom"]),
            _employer("Mizuho", "https://www.mizuhogroup.com/careers", "Tokyo", ["finance"]),
        ],
        "jobs": [
            _job("Global New Grad (Engineering)", "Sony", "Tokyo, Japan", "https://www.sony.com/en/jobs", ["ENGINEERING", "CS"]),
            _job("New Graduate (Product/Tech)", "Rakuten", "Tokyo, Japan", "https://corp.rakuten.co.jp/careers", ["CS", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="¥50k–¥80k (share-house)",
            private_rent_monthly="¥80k–¥140k (1R/1K central)",
            transit_index_note="JR + Metro; IC cards (Suica/Pasmo)",
            grocery_index_note="Moderate; konbini culture",
            climate_snapshot="Humid summers; cool winters",
            safety_snapshot="Extremely safe",
        ),
    },
    "paris": {
        "label": "Paris, France",
        "country_codes": {"FR"},
        "aliases": ["paris", "sorbonne", "sciences po", "polytechnique", "hec paris", "université paris"],
        "employers": [
            _employer("Capgemini", "https://www.capgemini.com/careers", "Paris", ["consulting", "tech"]),
            _employer("BNP Paribas", "https://group.bnpparibas/en/careers", "Paris", ["finance"]),
            _employer("L'Oréal", "https://careers.loreal.com", "Paris", ["consumer", "business"]),
            _employer("Thales", "https://www.thalesgroup.com/en/careers", "Paris / Île-de-France", ["engineering", "aerospace"]),
        ],
        "jobs": [
            _job("Graduate Consultant", "Capgemini", "Paris, France", "https://www.capgemini.com/careers", ["BUSINESS", "IT"]),
            _job("Graduate Programme", "BNP Paribas", "Paris, France", "https://group.bnpparibas/en/careers", ["FINANCE", "BUSINESS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="EUR €500–€800 (shared / CROUS)",
            private_rent_monthly="EUR €1,100–€1,800 (studio/1BR)",
            transit_index_note="Metro/RER; Navigo pass",
            grocery_index_note="Moderate; marchés help",
            climate_snapshot="Mild; grey winters",
            safety_snapshot="Standard European capital awareness",
        ),
    },
    "dublin": {
        "label": "Dublin, Ireland",
        "country_codes": {"IE"},
        "aliases": ["dublin", "trinity college", "university college dublin", "ucd", "dublin city university", "dcu"],
        "employers": [
            _employer("Google", "https://careers.google.com", "Dublin", ["tech"]),
            _employer("Meta", "https://www.metacareers.com", "Dublin", ["tech"]),
            _employer("Accenture", "https://www.accenture.com/careers", "Dublin", ["consulting", "tech"]),
            _employer("Pfizer", "https://www.pfizer.com/about/careers", "Dublin / Cork corridor", ["pharma"]),
        ],
        "jobs": [
            _job("Software Engineering New Grad", "Google", "Dublin, Ireland", "https://careers.google.com", ["CS", "SOFTWARE"]),
            _job("Technology Consulting Analyst", "Accenture", "Dublin, Ireland", "https://www.accenture.com/careers", ["BUSINESS", "IT"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="EUR €600–€1,000 (shared)",
            private_rent_monthly="EUR €1,600–€2,400 (1BR)",
            transit_index_note="Leap Card / Luas / Bus Éireann",
            grocery_index_note="Moderate-high",
            climate_snapshot="Mild, damp Atlantic climate",
            safety_snapshot="Generally safe; housing scarcity is the bigger issue",
        ),
    },
    "amsterdam": {
        "label": "Amsterdam / Randstad, Netherlands",
        "country_codes": {"NL"},
        "aliases": ["amsterdam", "delft", "leiden", "utrecht", "eindhoven", "university of amsterdam", "tu delft", "vu amsterdam"],
        "employers": [
            _employer("ASML", "https://www.asml.com/careers", "Veldhoven (Randstad commute)", ["semiconductors", "engineering"]),
            _employer("Booking.com", "https://careers.booking.com", "Amsterdam", ["tech"]),
            _employer("ING", "https://www.ing.jobs", "Amsterdam", ["finance"]),
            _employer("Philips", "https://www.careers.philips.com", "Amsterdam / Eindhoven", ["healthtech"]),
        ],
        "jobs": [
            _job("Graduate Software Engineer", "Booking.com", "Amsterdam, Netherlands", "https://careers.booking.com", ["CS", "SOFTWARE"]),
            _job("Graduate Engineer", "ASML", "Veldhoven, Netherlands", "https://www.asml.com/careers", ["ENGINEERING", "PHYSICS"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="EUR €500–€900 (shared — scarce)",
            private_rent_monthly="EUR €1,300–€2,000 (1BR Amsterdam)",
            transit_index_note="Trains/trams/bikes — cycling is default",
            grocery_index_note="Moderate",
            climate_snapshot="Cool, rainy maritime",
            safety_snapshot="Very safe; housing hunt is the stressor",
        ),
    },
    "warsaw": {
        "label": "Warsaw, Poland",
        "country_codes": {"PL"},
        "aliases": ["warsaw", "warszawa", "university of warsaw", "warsaw university of technology", "kozminski"],
        "employers": [
            _employer("CD Projekt", "https://www.cdprojekt.com/en/jobs/", "Warsaw", ["gaming", "tech"]),
            _employer("Allegro", "https://careers.allegro.eu", "Warsaw", ["tech", "commerce"]),
            _employer("PKO Bank Polski", "https://www.pkobp.pl/kariera/", "Warsaw", ["finance"]),
            _employer("Google", "https://careers.google.com", "Warsaw", ["tech"]),
        ],
        "jobs": [
            _job("Junior Software Engineer", "CD Projekt", "Warsaw, Poland", "https://www.cdprojekt.com/en/jobs/", ["CS", "SOFTWARE", "GAMING"]),
            _job("Graduate Technology Role", "Allegro", "Warsaw, Poland", "https://careers.allegro.eu", ["CS", "SOFTWARE"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="PLN 1,400–2,200 (shared)",
            private_rent_monthly="PLN 3,000–4,800 (1BR centre)",
            transit_index_note="Metro + trams; affordable monthly passes",
            grocery_index_note="Moderate — strong value vs Western EU",
            climate_snapshot="Cold winters; warm summers",
            safety_snapshot="Generally safe student districts",
        ),
    },
    "singapore-city": {
        "label": "Singapore",
        "country_codes": {"SG"},
        "aliases": ["singapore", "nus", "ntu", "smu", "national university of singapore", "nanyang"],
        "employers": [
            _employer("DBS Bank", "https://www.dbs.com/careers", "Singapore", ["finance"]),
            _employer("Grab", "https://grab.careers", "Singapore", ["tech"]),
            _employer("Sea Limited", "https://www.sea.com/careers", "Singapore", ["tech"]),
            _employer("Google", "https://careers.google.com", "Singapore", ["tech"]),
        ],
        "jobs": [
            _job("Technology Graduate", "DBS Bank", "Singapore", "https://www.dbs.com/careers", ["CS", "FINANCE", "IT"]),
            _job("Software Engineer (Early Career)", "Grab", "Singapore", "https://grab.careers", ["CS", "SOFTWARE"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="SGD $800–$1,400 (HDB room / shared)",
            private_rent_monthly="SGD $2,500–$4,500 (condo 1BR)",
            transit_index_note="MRT/bus island-wide; EZ-Link / SimplyGo",
            grocery_index_note="Hawker centres offset supermarket prices",
            climate_snapshot="Tropical hot/humid year-round",
            safety_snapshot="Extremely safe",
        ),
    },
    "dubai": {
        "label": "Dubai / Abu Dhabi, UAE",
        "country_codes": {"AE"},
        "aliases": ["dubai", "abu dhabi", "sharjah", "american university of sharjah", "khalifa university", "heriot-watt dubai"],
        "employers": [
            _employer("Emirates", "https://www.emirates.com/careers", "Dubai", ["aviation", "business"]),
            _employer("Etisalat (e&)", "https://www.etisalat.ae", "Dubai / Abu Dhabi", ["telecom"]),
            _employer("ADNOC", "https://www.adnoc.ae/careers", "Abu Dhabi", ["energy", "engineering"]),
            _employer("Emirates NBD", "https://www.emiratesnbd.com/careers", "Dubai", ["finance"]),
        ],
        "jobs": [
            _job("Graduate Programme", "Emirates", "Dubai, UAE", "https://www.emirates.com/careers", ["BUSINESS", "AVIATION"]),
            _job("Early Career Engineer", "ADNOC", "Abu Dhabi, UAE", "https://www.adnoc.ae/careers", ["ENGINEERING", "ENERGY"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="AED 2,000–3,500 (shared)",
            private_rent_monthly="AED 4,500–8,000+ (1BR)",
            transit_index_note="Dubai Metro + ride-hail; car useful off-metro",
            grocery_index_note="Moderate-high imports",
            climate_snapshot="Extremely hot summers; mild winters",
            safety_snapshot="Very safe; respect local laws",
        ),
    },
    "hong-kong-island": {
        "label": "Hong Kong",
        "country_codes": {"HK"},
        "aliases": ["hong kong", "hku", "cuhk", "hkust", "city university of hong kong", "polyu"],
        "employers": [
            _employer("HSBC", "https://www.hsbc.com.hk/careers/", "Hong Kong", ["finance"]),
            _employer("Cathay Pacific", "https://careers.cathaypacific.com", "Hong Kong", ["aviation"]),
            _employer("AIA", "https://www.aia.com/en/careers", "Hong Kong", ["insurance", "finance"]),
            _employer("Google", "https://careers.google.com", "Hong Kong", ["tech"]),
        ],
        "jobs": [
            _job("Graduate Analyst", "HSBC", "Hong Kong", "https://www.hsbc.com.hk/careers/", ["FINANCE", "BUSINESS"]),
            _job("Graduate Programme", "Cathay Pacific", "Hong Kong", "https://careers.cathaypacific.com", ["BUSINESS", "AVIATION"]),
        ],
        "city_living": FutureInsightsCityLiving(
            shared_housing_monthly="HKD 6,000–10,000 (shared — scarce)",
            private_rent_monthly="HKD 15,000–25,000+ (compact 1BR)",
            transit_index_note="MTR + Octopus — among the best urban transit systems",
            grocery_index_note="High; wet markets help",
            climate_snapshot="Hot humid summers; typhoon season",
            safety_snapshot="Very safe; space/cost is the constraint",
        ),
    },
}


def match_metro_key(
    *,
    country_code: str,
    institution_name: str | None,
    city_name: str | None,
    state_name: str | None,
) -> str | None:
    country = (country_code or "").strip().upper()
    if country == "GB":
        country = "UK"
    blob = " ".join(
        part for part in [institution_name or "", city_name or "", state_name or ""] if part
    ).lower()
    if not blob.strip():
        return None

    best_key: str | None = None
    best_len = 0
    for key, pack in METRO_PACKS.items():
        if country not in pack["country_codes"]:
            continue
        for alias in pack["aliases"]:
            alias_l = alias.lower()
            if alias_l in blob and len(alias_l) > best_len:
                best_key = key
                best_len = len(alias_l)
    return best_key


def metro_location_label(metro_key: str | None, fallback: str) -> str:
    if not metro_key:
        return fallback
    pack = METRO_PACKS.get(metro_key)
    return str(pack["label"]) if pack else fallback
