"""Session-scoped Destination / Future Insights packs (API-driven, not FE-hardcoded)."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.schemas.nexus_intel import (
    CountryComparisonItem,
    FutureInsightsCityLiving,
    FutureInsightsDestinationPack,
    FutureInsightsEmployer,
    FutureInsightsImmigration,
    FutureInsightsInstitutionContext,
    FutureInsightsJob,
    FutureInsightsResponse,
    FutureInsightsRoi,
)
from app.services.future_insights_habitat import build_habitat
from app.services.nexus_intel import COMPARISON_MATRIX

# Aspirations use ISO2 (GB); Intel comparison matrix historically uses UK.
_ISO2_TO_INTEL = {"GB": "UK"}
_INTEL_TO_ISO2 = {"UK": "GB"}

_AS_OF = date.today().isoformat()
_DISCLAIMER = (
    "Counsellor reference only — salary, cost, visa, and job figures are indicative "
    "snapshots and may change. Verify official sources before advising students."
)


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


def _normalize_intel_code(code: str) -> str:
    upper = (code or "").strip().upper()
    return _ISO2_TO_INTEL.get(upper, upper)


def _to_iso2(intel_code: str) -> str:
    return _INTEL_TO_ISO2.get(intel_code, intel_code)


# ROI / city / employers / jobs overlays keyed by Intel country code.
_ROI: dict[str, FutureInsightsRoi] = {
    "CA": FutureInsightsRoi(
        tuition_baseline="CAD $15k–$40k / year (program & province dependent)",
        health_fees_note="Provincial health / UHIP-style coverage often required for internationals",
        median_starting_salary="CAD $48k–$65k (metro + discipline dependent)",
        break_even_horizon="Typically 3–6 years post-grad vs mid-range tuition + living",
        ten_year_yield_note="Strong mid-career lift in tech, health, and skilled trades corridors",
        currency="CAD",
    ),
    "US": FutureInsightsRoi(
        tuition_baseline="USD $20k–$60k+ / year (public in-state vs private)",
        health_fees_note="University health insurance usually mandatory for F-1 students",
        median_starting_salary="USD $55k–$85k+ (STEM / business metros higher)",
        break_even_horizon="Often 4–8 years depending on debt load and OPT outcomes",
        ten_year_yield_note="Highest upside in tech/finance hubs; visa sponsorship is a gating factor",
        currency="USD",
    ),
    "UK": FutureInsightsRoi(
        tuition_baseline="£12k–£38k / year (varies widely by school & subject)",
        health_fees_note="Immigration Health Surcharge (IHS) payable with Student visa",
        median_starting_salary="£28k–£38k typical graduate band (London premium)",
        break_even_horizon="Often 4–7 years outside high-ROI STEM/finance tracks",
        ten_year_yield_note="Graduate Route window supports early career; long-term yield depends on Skilled Worker path",
        currency="GBP",
    ),
    "AU": FutureInsightsRoi(
        tuition_baseline="AUD $20k–$45k / year",
        health_fees_note="OSHC (Overseas Student Health Cover) required for Student visa",
        median_starting_salary="AUD $55k–$75k typical graduate band",
        break_even_horizon="Often 3–6 years with Temporary Graduate work rights",
        ten_year_yield_note="State nomination & skills lists shape long-term ROI beyond salary alone",
        currency="AUD",
    ),
    "DE": FutureInsightsRoi(
        tuition_baseline="Often low/no tuition at public universities (+ semester fees)",
        health_fees_note="Statutory/private health insurance mandatory for residence",
        median_starting_salary="€42k–€55k typical graduate band",
        break_even_horizon="Often 2–4 years given low tuition; living costs dominate",
        ten_year_yield_note="Strong engineering/manufacturing corridors; German language lifts yield",
        currency="EUR",
    ),
    "JP": FutureInsightsRoi(
        tuition_baseline="¥500k–¥1.5M+ / year (national vs private)",
        health_fees_note="National Health Insurance enrollment expected after arrival",
        median_starting_salary="¥3.5M–¥5.0M typical new-grad band (Tokyo premium)",
        break_even_horizon="Often 4–7 years; language proficiency strongly affects outcomes",
        ten_year_yield_note="Global firms + HSP points pathway can improve long-term mobility",
        currency="JPY",
    ),
    "FR": FutureInsightsRoi(
        tuition_baseline="Public regulated fees low; Grandes écoles / private higher",
        health_fees_note="Student social security / complementary cover typical",
        median_starting_salary="€32k–€42k typical graduate band",
        break_even_horizon="Often 3–5 years on public tracks; longer on private tuition",
        ten_year_yield_note="APS job-search residence supports early career; EU mobility is a plus",
        currency="EUR",
    ),
    "NZ": FutureInsightsRoi(
        tuition_baseline="NZD $22k–$45k+ / year",
        health_fees_note="Medical insurance usually required for Student visa conditions",
        median_starting_salary="NZD $50k–$65k typical graduate band",
        break_even_horizon="Often 3–6 years with Post Study Work rights",
        ten_year_yield_note="Skilled Migrant / green list pathways shape settlement ROI",
        currency="NZD",
    ),
    "SG": FutureInsightsRoi(
        tuition_baseline="SGD high for internationals; Tuition Grant lowers fees with bond",
        health_fees_note="School / IPA-linked medical insurance common",
        median_starting_salary="SGD $40k–$55k+ typical graduate band",
        break_even_horizon="Often 3–5 years if EP sponsorship follows; TG bond affects calculus",
        ten_year_yield_note="Regional HQ density supports finance/tech careers; no automatic PSW",
        currency="SGD",
    ),
    "AE": FutureInsightsRoi(
        tuition_baseline="AED high private / international campus fees",
        health_fees_note="Employer or university medical cover varies by emirate / free zone",
        median_starting_salary="AED competitive tax-free packages in finance/tech hubs",
        break_even_horizon="Highly variable — tuition high; tax-free salaries can compress payback",
        ten_year_yield_note="Sponsorship-led market; long-term stay depends on employer visa pathways",
        currency="AED",
    ),
    "SE": FutureInsightsRoi(
        tuition_baseline="EU/EEA often fee-free at public unis; non-EU tuition applies",
        health_fees_note="Residence-linked health coverage after registration",
        median_starting_salary="SEK 320k–420k typical graduate band",
        break_even_horizon="Often 3–5 years for fee-paying internationals",
        ten_year_yield_note="Strong engineering/climate-tech corridors; Swedish language helps",
        currency="SEK",
    ),
    "CH": FutureInsightsRoi(
        tuition_baseline="Public cantonal fees moderate; private/specialty higher",
        health_fees_note="Mandatory health insurance shortly after arrival",
        median_starting_salary="CHF 70k–90k+ typical graduate band (city dependent)",
        break_even_horizon="Often 2–4 years given strong salary bands; quotas constrain outcomes",
        ten_year_yield_note="High salaries offset living costs; work permit quotas are the risk factor",
        currency="CHF",
    ),
    "IE": FutureInsightsRoi(
        tuition_baseline="EUR €10k–€25k+ / year (programme dependent)",
        health_fees_note="Private medical insurance commonly required for immigration registration",
        median_starting_salary="EUR €32k–€45k typical graduate band (Dublin premium)",
        break_even_horizon="Often 3–5 years with Graduate Scheme stay-back",
        ten_year_yield_note="Strong tech/pharma corridors; Critical Skills Employment Permit supports longer stay",
        currency="EUR",
    ),
    "NL": FutureInsightsRoi(
        tuition_baseline="Non-EU institutional fees commonly ~€8k–€20k+ / year",
        health_fees_note="Dutch health insurance required after registration / residence",
        median_starting_salary="EUR €35k–€48k typical graduate band",
        break_even_horizon="Often 3–5 years; orientation year helps early earnings",
        ten_year_yield_note="High English-speaking labour market; highly skilled migrant scheme is key",
        currency="EUR",
    ),
    "NO": FutureInsightsRoi(
        tuition_baseline="Public fees historically low/none; confirm current non-EU tuition policy by university",
        health_fees_note="Membership in National Insurance scheme after eligible residence",
        median_starting_salary="NOK 480k–580k typical graduate band",
        break_even_horizon="Often 2–4 years when tuition is low; living costs dominate",
        ten_year_yield_note="Strong energy/maritime/tech salaries; language helps long-term mobility",
        currency="NOK",
    ),
    "PL": FutureInsightsRoi(
        tuition_baseline="EUR/PLN moderate public international fees; private higher",
        health_fees_note="Health insurance required for visa / temporary residence",
        median_starting_salary="PLN 5.5k–8k monthly typical early-career band (city dependent)",
        break_even_horizon="Often 2–4 years given lower tuition vs Western Europe",
        ten_year_yield_note="Growing SSC/IT hubs (Warsaw, Kraków, Wrocław); EU mobility after eligible status",
        currency="PLN",
    ),
    "HK": FutureInsightsRoi(
        tuition_baseline="HKD high for non-local UG; taught PG bands vary widely",
        health_fees_note="University / private medical cover typically arranged for visa",
        median_starting_salary="HKD 18k–28k monthly typical graduate band",
        break_even_horizon="Often 3–6 years; IANG open stay supports early career",
        ten_year_yield_note="Finance/professional services density; competition and living costs are high",
        currency="HKD",
    ),
    "MY": FutureInsightsRoi(
        tuition_baseline="MYR competitive vs AU/UK/US; branch campuses priced higher",
        health_fees_note="Medical insurance usually required under Student Pass / EMGS",
        median_starting_salary="MYR 3k–5k monthly typical graduate band (KL premium)",
        break_even_horizon="Often 2–4 years on local fee levels; sponsorship needed for longer stay",
        ten_year_yield_note="Regional hub for shared services/tech; Employment Pass is the bridge",
        currency="MYR",
    ),
    "QA": FutureInsightsRoi(
        tuition_baseline="QAR — Education City / private fees; scholarships materially change ROI",
        health_fees_note="Hamad / university medical cover typically tied to residence",
        median_starting_salary="QAR competitive tax-free packages in energy/finance/education hubs",
        break_even_horizon="Highly scholarship-sensitive; employer sponsorship drives payback",
        ten_year_yield_note="Residence is sponsorship-led; Education City networks help placements",
        currency="QAR",
    ),
    "IN": FutureInsightsRoi(
        tuition_baseline="INR wide range — NITs/IITs/public vs private / international campuses",
        health_fees_note="Campus or private medical insurance commonly required for foreign students",
        median_starting_salary="INR campus-dependent — tech/consulting metros pay a large premium",
        break_even_horizon="Often 1–3 years on public fees; longer on premium private tuition",
        ten_year_yield_note="Domestic market depth is the yield story; foreign-student work rights are limited",
        currency="INR",
    ),
    "RU": FutureInsightsRoi(
        tuition_baseline="RUB moderate at many public universities; English tracks higher",
        health_fees_note="Medical insurance typically required for student visa / enrolment",
        median_starting_salary="RUB early-career bands vary sharply by city and sector",
        break_even_horizon="Often 2–4 years on moderate tuition; currency and policy risk matter",
        ten_year_yield_note="Outcomes depend on sector, language, and migration policy — verify case-by-case",
        currency="RUB",
    ),
}

_CITY: dict[str, FutureInsightsCityLiving] = {
    "CA": FutureInsightsCityLiving(
        shared_housing_monthly="CAD $700–$1,200 (shared)",
        private_rent_monthly="CAD $1,600–$2,800 (1BR metro)",
        transit_index_note="Strong transit in Toronto/Vancouver/Montreal; winter commute planning matters",
        grocery_index_note="Grocery costs moderate-high in major metros",
        climate_snapshot="Cold winters (except coastal BC); warm summers inland",
        safety_snapshot="Generally safe student cities; neighbourhood variation as in any metro",
    ),
    "US": FutureInsightsCityLiving(
        shared_housing_monthly="USD $800–$1,400 (shared)",
        private_rent_monthly="USD $1,500–$3,500+ (coastal metros)",
        transit_index_note="Transit-rich in NYC/Boston/Chicago; car-dependent in many metros",
        grocery_index_note="Wide range; coastal cities materially higher",
        climate_snapshot="Extremely varied by state — confirm campus microclimate",
        safety_snapshot="Campus security strong; off-campus safety is neighbourhood-specific",
    ),
    "UK": FutureInsightsCityLiving(
        shared_housing_monthly="£500–£900 (shared outside central London)",
        private_rent_monthly="£1,200–£2,500+ (London premium)",
        transit_index_note="Excellent rail/tube in London; solid city buses/trams elsewhere",
        grocery_index_note="Moderate; London groceries and council tax add pressure",
        climate_snapshot="Mild, damp winters; cool summers",
        safety_snapshot="Student cities generally manageable; standard urban awareness",
    ),
    "AU": FutureInsightsCityLiving(
        shared_housing_monthly="AUD $800–$1,300 (shared)",
        private_rent_monthly="AUD $1,800–$3,000 (Sydney/Melbourne)",
        transit_index_note="Good metro transit; some suburban campuses need longer commutes",
        grocery_index_note="Moderate-high in capital cities",
        climate_snapshot="Warm summers; city microclimates from tropical QLD to cooler VIC",
        safety_snapshot="High livability rankings; bushfire/flood awareness by region",
    ),
    "DE": FutureInsightsCityLiving(
        shared_housing_monthly="€350–€650 (WG shared)",
        private_rent_monthly="€800–€1,600 (city dependent)",
        transit_index_note="Excellent local transit; semester ticket often included",
        grocery_index_note="Moderate; discount grocers keep costs manageable",
        climate_snapshot="Temperate; cold winters inland",
        safety_snapshot="Very safe student cities overall",
    ),
    "JP": FutureInsightsCityLiving(
        shared_housing_monthly="¥40k–¥70k (shared / share-house)",
        private_rent_monthly="¥70k–¥120k+ (Tokyo 1R/1K)",
        transit_index_note="World-class urban rail; IC cards simplify daily travel",
        grocery_index_note="Moderate; eating out can be affordable near campuses",
        climate_snapshot="Humid summers; cold winters inland / Hokkaido",
        safety_snapshot="Among the safest large-city environments globally",
    ),
    "FR": FutureInsightsCityLiving(
        shared_housing_monthly="€400–€700 (shared / CROUS waitlists)",
        private_rent_monthly="€800–€1,500 (Paris premium)",
        transit_index_note="Strong metro/RER in Paris; solid regional TER elsewhere",
        grocery_index_note="Moderate; marchés help stretch budgets",
        climate_snapshot="Mild in west; colder winters inland/east",
        safety_snapshot="Standard European urban awareness; campus areas generally fine",
    ),
    "NZ": FutureInsightsCityLiving(
        shared_housing_monthly="NZD $700–$1,100 (shared)",
        private_rent_monthly="NZD $1,500–$2,400 (Auckland premium)",
        transit_index_note="Improving urban transit; smaller cities often need bikes/cars",
        grocery_index_note="Moderate-high for imports; local produce helps",
        climate_snapshot="Temperate maritime; regional weather swings",
        safety_snapshot="High livability; earthquake preparedness is normal",
    ),
    "SG": FutureInsightsCityLiving(
        shared_housing_monthly="SGD $800–$1,400 (shared / HDB room)",
        private_rent_monthly="SGD $2,500–$4,500 (condo 1BR)",
        transit_index_note="Excellent MRT/bus network island-wide",
        grocery_index_note="Hawker centres offset higher supermarket prices",
        climate_snapshot="Tropical — hot/humid year-round; heavy rain seasons",
        safety_snapshot="Very safe; strict local regulations apply",
    ),
    "AE": FutureInsightsCityLiving(
        shared_housing_monthly="AED 2,000–3,500 (shared)",
        private_rent_monthly="AED 4,500–8,000+ (Dubai/Abu Dhabi)",
        transit_index_note="Dubai Metro + ride-hail; car useful for many campuses",
        grocery_index_note="Moderate-high; malls and hypermarkets dominate",
        climate_snapshot="Extremely hot summers; mild winters",
        safety_snapshot="Very safe cities; respect local laws and customs",
    ),
    "SE": FutureInsightsCityLiving(
        shared_housing_monthly="SEK 4,000–7,000 (student corridor / shared)",
        private_rent_monthly="SEK 9,000–15,000 (Stockholm premium)",
        transit_index_note="Strong local transit; student cards common",
        grocery_index_note="Moderate-high; Systembolaget / grocery chains",
        climate_snapshot="Long dark winters; bright summers",
        safety_snapshot="Generally very safe student cities",
    ),
    "CH": FutureInsightsCityLiving(
        shared_housing_monthly="CHF 600–1,000 (shared)",
        private_rent_monthly="CHF 1,500–2,800 (Zurich/Geneva)",
        transit_index_note="Excellent national rail + local transit; half-fare cards help",
        grocery_index_note="High grocery costs; cross-border shopping sometimes used",
        climate_snapshot="Alpine winters; pleasant summers",
        safety_snapshot="Extremely safe; high living costs are the main pressure",
    ),
    "IE": FutureInsightsCityLiving(
        shared_housing_monthly="EUR €500–€900 (shared)",
        private_rent_monthly="EUR €1,400–€2,400 (Dublin premium)",
        transit_index_note="Dublin Leap / Luas / Bus; regional cities more compact",
        grocery_index_note="Moderate-high in Dublin; similar to other NW Europe capitals",
        climate_snapshot="Mild, damp Atlantic climate year-round",
        safety_snapshot="Generally safe student cities; standard urban awareness in Dublin centre",
    ),
    "NL": FutureInsightsCityLiving(
        shared_housing_monthly="EUR €450–€800 (shared / student housing)",
        private_rent_monthly="EUR €1,100–€2,000 (Amsterdam premium)",
        transit_index_note="Excellent trains/trams/bikes — cycling is core lifestyle",
        grocery_index_note="Moderate; Albert Heijn / discounters keep baskets predictable",
        climate_snapshot="Cool, rainy maritime climate",
        safety_snapshot="Very safe; housing scarcity is the bigger stressor than safety",
    ),
    "NO": FutureInsightsCityLiving(
        shared_housing_monthly="NOK 5,000–8,000 (shared / student housing)",
        private_rent_monthly="NOK 12,000–18,000 (Oslo premium)",
        transit_index_note="Strong urban transit; student discounts common",
        grocery_index_note="High grocery costs; cooking at home is essential for budgets",
        climate_snapshot="Cold, dark winters; bright summers; regional extremes in the north",
        safety_snapshot="Extremely safe student cities",
    ),
    "PL": FutureInsightsCityLiving(
        shared_housing_monthly="PLN 1,200–2,000 (shared)",
        private_rent_monthly="PLN 2,500–4,500 (Warsaw/Kraków premium)",
        transit_index_note="Solid trams/buses/metros in major cities; affordable monthly passes",
        grocery_index_note="Moderate — among the more affordable EU study options",
        climate_snapshot="Cold winters; warm summers",
        safety_snapshot="Generally safe student cities; normal urban awareness",
    ),
    "HK": FutureInsightsCityLiving(
        shared_housing_monthly="HKD 6,000–10,000 (shared / subdivided — scarce)",
        private_rent_monthly="HKD 15,000–25,000+ (tiny flats common)",
        transit_index_note="World-class MTR; Octopus card simplifies everything",
        grocery_index_note="High; wet markets help vs supermarket imports",
        climate_snapshot="Hot humid summers; mild winters; typhoon season",
        safety_snapshot="Very safe; housing cost/space is the main lifestyle constraint",
    ),
    "MY": FutureInsightsCityLiving(
        shared_housing_monthly="MYR 600–1,200 (shared)",
        private_rent_monthly="MYR 1,500–3,000 (KL / Penang)",
        transit_index_note="KL has MRT/LRT; many campuses still benefit from Grab",
        grocery_index_note="Affordable food culture; hawker / mamak meals stretch budgets",
        climate_snapshot="Tropical — hot/humid with monsoon seasons",
        safety_snapshot="Generally manageable; neighbourhood variation in larger cities",
    ),
    "QA": FutureInsightsCityLiving(
        shared_housing_monthly="QAR 2,000–3,500 (shared / student housing)",
        private_rent_monthly="QAR 4,500–8,000 (Doha)",
        transit_index_note="Doha Metro expanding; Education City shuttles common",
        grocery_index_note="Moderate-high imports; mall hypermarkets dominate",
        climate_snapshot="Extremely hot summers; mild winters",
        safety_snapshot="Very safe; respect local laws and customs",
    ),
    "IN": FutureInsightsCityLiving(
        shared_housing_monthly="INR 8k–20k (shared / PG)",
        private_rent_monthly="INR 20k–60k+ (metro dependent)",
        transit_index_note="Metro networks in major cities; campus shuttles common",
        grocery_index_note="Wide range — local markets keep costs flexible",
        climate_snapshot="Extremely varied by region — confirm campus climate",
        safety_snapshot="Campus security varies; choose housing with verified student reviews",
    ),
    "RU": FutureInsightsCityLiving(
        shared_housing_monthly="RUB 15k–30k (dorm / shared)",
        private_rent_monthly="RUB 40k–80k+ (Moscow/St. Petersburg premium)",
        transit_index_note="Excellent metros in major cities; student passes common",
        grocery_index_note="Moderate; local chains keep staples accessible",
        climate_snapshot="Cold winters; short summers — city dependent",
        safety_snapshot="Follow university international-office guidance; register as required",
    ),
}

_PATHWAYS: dict[str, list[str]] = {
    "CA": [
        "PGWP duration tied to program length — confirm IRCC rules for the specific credential",
        "Express Entry / Provincial Nominee streams are common long-term pathways after Canadian work experience",
    ],
    "US": [
        "OPT (12 months) + STEM OPT extension (24 months) for eligible degrees",
        "H-1B / other work visas typically required beyond OPT — employer sponsorship critical",
    ],
    "UK": [
        "Graduate Route (usually 2 years; 3 for PhD) after eligible UK degree",
        "Skilled Worker visa is the common bridge from Graduate Route to longer stay",
    ],
    "AU": [
        "Temporary Graduate (485) pathways vary by qualification and location",
        "State nomination and skills lists shape PR strategy beyond the study visa",
    ],
    "DE": [
        "18-month job-seeker residence after eligible graduation",
        "EU Blue Card / employment residence once a qualifying job offer is secured",
    ],
    "JP": [
        "Designated Activities (job hunting) or direct change to Work / Highly Skilled Professional",
        "HSP points system can accelerate longer-term residence for high scorers",
    ],
    "FR": [
        "APS / job-search or entrepreneurship residence after eligible Master's-level study",
        "Talent Passport / salaried residence once employed",
    ],
    "NZ": [
        "Post Study Work Visa open work rights typically 1–3 years by qualification tier",
        "Skilled Migrant / green list roles influence settlement planning",
    ],
    "SG": [
        "No automatic open PSW — plan for Employment Pass / related work passes",
        "Tuition Grant bond (if accepted) creates a post-grad work obligation in Singapore",
    ],
    "AE": [
        "Residence is primarily study- or employer-tied",
        "Long-term stay usually requires sponsorship after graduation",
    ],
    "SE": [
        "Up to 12 months residence to seek work after eligible Bachelor's/Master's",
        "Work permit follows a qualifying job offer",
    ],
    "CH": [
        "~6-month post-grad window to find work of high economic/scientific interest",
        "Cantonal quotas and permit categories are decisive — early employer outreach matters",
    ],
    "IE": [
        "Third Level Graduate Scheme typically grants 12–24 months stay-back by award level",
        "Critical Skills / General Employment Permits are common bridges to longer residence",
    ],
    "NL": [
        "Orientation year (zoekjaar) — typically up to 1 year after eligible graduation",
        "Highly skilled migrant / EU Blue Card routes after a qualifying job offer",
    ],
    "NO": [
        "Job-seeker residence may be available after eligible graduation — confirm UDI rules",
        "Skilled worker residence follows a qualifying job offer and salary thresholds",
    ],
    "PL": [
        "Temporary residence to seek work after graduation is available under national rules",
        "EU long-term / work residence depends on continuous legal stay and employment",
    ],
    "HK": [
        "IANG typically allows 24 months open stay for eligible non-local graduates",
        "Longer stay usually transitions via employment / investment visa categories",
    ],
    "MY": [
        "No broad automatic multi-year PSW — plan Employment Pass / related categories early",
        "EMGS Student Pass compliance (attendance, insurance) is closely monitored",
    ],
    "QA": [
        "Residence is primarily study- or employer-tied after graduation",
        "Education City / employer sponsorship is the practical long-term pathway",
    ],
    "IN": [
        "Foreign graduates generally need a separate work authorisation — not an open PSW model",
        "Focus counsellor talk-track on academic fit and domestic placement outcomes",
    ],
    "RU": [
        "Post-study work requires separate migration authorisation — not a broad open PSW",
        "Always verify current consular / university international-office guidance before advising",
    ],
}

_EMPLOYERS: dict[str, list[FutureInsightsEmployer]] = {
    "CA": [
        _employer("Shopify", "https://www.shopify.com", "Ottawa / remote-friendly", ["tech", "commerce"]),
        _employer("RBC", "https://www.rbc.com", "Toronto", ["finance", "banking"]),
        _employer("TD Bank", "https://www.td.com", "Toronto", ["finance"]),
        _employer("CGI", "https://www.cgi.com", "Montreal / national", ["tech", "consulting"]),
        _employer("Bombardier", "https://bombardier.com", "Montreal", ["engineering", "aerospace"]),
    ],
    "US": [
        _employer("Google", "https://about.google", "Multi-metro", ["tech"]),
        _employer("Microsoft", "https://www.microsoft.com", "Redmond / national", ["tech"]),
        _employer("Amazon", "https://www.amazon.jobs", "Multi-metro", ["tech", "operations"]),
        _employer("JPMorgan Chase", "https://www.jpmorganchase.com", "NYC / national", ["finance"]),
        _employer("Deloitte", "https://www2.deloitte.com", "Multi-metro", ["consulting"]),
    ],
    "UK": [
        _employer("HSBC", "https://www.hsbc.com", "London", ["finance"]),
        _employer("Barclays", "https://www.barclays.co.uk", "London", ["finance"]),
        _employer("BBC", "https://www.bbc.co.uk", "London / national", ["media"]),
        _employer("ARM", "https://www.arm.com", "Cambridge", ["tech", "semiconductors"]),
        _employer("Rolls-Royce", "https://www.rolls-royce.com", "Derby / national", ["engineering"]),
    ],
    "AU": [
        _employer("Atlassian", "https://www.atlassian.com", "Sydney", ["tech"]),
        _employer("Commonwealth Bank", "https://www.commbank.com.au", "Sydney", ["finance"]),
        _employer("BHP", "https://www.bhp.com", "Melbourne / national", ["resources", "engineering"]),
        _employer("Telstra", "https://www.telstra.com.au", "Melbourne", ["telecom", "tech"]),
    ],
    "DE": [
        _employer("SAP", "https://www.sap.com", "Walldorf / national", ["tech"]),
        _employer("Siemens", "https://www.siemens.com", "Munich / national", ["engineering"]),
        _employer("BMW", "https://www.bmwgroup.com", "Munich", ["automotive", "engineering"]),
        _employer("Deutsche Bank", "https://www.db.com", "Frankfurt", ["finance"]),
    ],
    "JP": [
        _employer("Sony", "https://www.sony.com", "Tokyo", ["tech", "electronics"]),
        _employer("Toyota", "https://global.toyota", "Aichi / national", ["automotive"]),
        _employer("SoftBank", "https://group.softbank", "Tokyo", ["tech", "telecom"]),
        _employer("Rakuten", "https://global.rakuten.com", "Tokyo", ["tech", "commerce"]),
    ],
    "FR": [
        _employer("Capgemini", "https://www.capgemini.com", "Paris / national", ["tech", "consulting"]),
        _employer("Airbus", "https://www.airbus.com", "Toulouse", ["aerospace", "engineering"]),
        _employer("BNP Paribas", "https://group.bnpparibas", "Paris", ["finance"]),
        _employer("L'Oréal", "https://www.loreal.com", "Paris / national", ["consumer", "business"]),
    ],
    "NZ": [
        _employer("Xero", "https://www.xero.com", "Wellington / Auckland", ["tech", "saas"]),
        _employer("Fonterra", "https://www.fonterra.com", "Auckland", ["agribusiness"]),
        _employer("Spark NZ", "https://www.sparknz.co.nz", "Auckland", ["telecom"]),
    ],
    "SG": [
        _employer("DBS Bank", "https://www.dbs.com", "Singapore", ["finance"]),
        _employer("Grab", "https://www.grab.com", "Singapore", ["tech", "mobility"]),
        _employer("Sea Limited", "https://www.sea.com", "Singapore", ["tech", "gaming"]),
        _employer("Singtel", "https://www.singtel.com", "Singapore", ["telecom"]),
    ],
    "AE": [
        _employer("Emirates", "https://www.emirates.com", "Dubai", ["aviation", "business"]),
        _employer("Etisalat (e&)", "https://www.etisalat.ae", "Abu Dhabi / Dubai", ["telecom"]),
        _employer("ADNOC", "https://www.adnoc.ae", "Abu Dhabi", ["energy", "engineering"]),
    ],
    "SE": [
        _employer("Spotify", "https://www.spotify.com", "Stockholm", ["tech"]),
        _employer("Ericsson", "https://www.ericsson.com", "Stockholm", ["telecom", "tech"]),
        _employer("IKEA", "https://www.ikea.com", "Älmhult / national", ["retail", "business"]),
    ],
    "CH": [
        _employer("Nestlé", "https://www.nestle.com", "Vevey / national", ["consumer", "business"]),
        _employer("Roche", "https://www.roche.com", "Basel", ["pharma", "life-sciences"]),
        _employer("UBS", "https://www.ubs.com", "Zurich", ["finance"]),
    ],
    "IE": [
        _employer("Accenture", "https://www.accenture.com", "Dublin", ["consulting", "tech"]),
        _employer("Google", "https://about.google", "Dublin", ["tech"]),
        _employer("Pfizer", "https://www.pfizer.com", "Cork / Dublin", ["pharma"]),
        _employer("Ryanair", "https://www.ryanair.com", "Dublin", ["aviation", "business"]),
    ],
    "NL": [
        _employer("ASML", "https://www.asml.com", "Veldhoven", ["semiconductors", "engineering"]),
        _employer("ING", "https://www.ing.com", "Amsterdam", ["finance"]),
        _employer("Philips", "https://www.philips.com", "Eindhoven / Amsterdam", ["healthtech", "engineering"]),
        _employer("Booking.com", "https://www.booking.com", "Amsterdam", ["tech", "travel"]),
    ],
    "NO": [
        _employer("Equinor", "https://www.equinor.com", "Stavanger / Oslo", ["energy", "engineering"]),
        _employer("DNB", "https://www.dnb.no", "Oslo", ["finance"]),
        _employer("Telenor", "https://www.telenor.com", "Oslo", ["telecom", "tech"]),
        _employer("Schibsted", "https://schibsted.com", "Oslo", ["media", "tech"]),
    ],
    "PL": [
        _employer("CD Projekt", "https://www.cdprojekt.com", "Warsaw", ["gaming", "tech"]),
        _employer("Allegro", "https://allegro.eu", "Poznań / Warsaw", ["commerce", "tech"]),
        _employer("PKO Bank Polski", "https://www.pkobp.pl", "Warsaw", ["finance"]),
        _employer("Asseco", "https://pl.asseco.com", "Rzeszów / national", ["tech", "software"]),
    ],
    "HK": [
        _employer("HSBC", "https://www.hsbc.com.hk", "Hong Kong", ["finance"]),
        _employer("Cathay Pacific", "https://www.cathaypacific.com", "Hong Kong", ["aviation"]),
        _employer("AIA", "https://www.aia.com", "Hong Kong", ["insurance", "finance"]),
        _employer("Lenovo", "https://www.lenovo.com", "Hong Kong / regional", ["tech"]),
    ],
    "MY": [
        _employer("Petronas", "https://www.petronas.com", "Kuala Lumpur", ["energy", "engineering"]),
        _employer("Maybank", "https://www.maybank.com", "Kuala Lumpur", ["finance"]),
        _employer("AirAsia", "https://www.airasia.com", "Kuala Lumpur", ["aviation", "business"]),
        _employer("Grab", "https://www.grab.com", "Kuala Lumpur / regional", ["tech", "mobility"]),
    ],
    "QA": [
        _employer("Qatar Airways", "https://www.qatarairways.com", "Doha", ["aviation", "business"]),
        _employer("QatarEnergy", "https://www.qatarenergy.qa", "Doha", ["energy", "engineering"]),
        _employer("Ooredoo", "https://www.ooredoo.qa", "Doha", ["telecom"]),
        _employer("QNB", "https://www.qnb.com", "Doha", ["finance"]),
    ],
    "IN": [
        _employer("Tata Consultancy Services", "https://www.tcs.com", "Multi-city", ["tech", "consulting"]),
        _employer("Infosys", "https://www.infosys.com", "Bengaluru / national", ["tech"]),
        _employer("Reliance Industries", "https://www.ril.com", "Mumbai / national", ["energy", "business"]),
        _employer("HDFC Bank", "https://www.hdfcbank.com", "Mumbai / national", ["finance"]),
    ],
    "RU": [
        _employer("Yandex", "https://yandex.com", "Moscow", ["tech"]),
        _employer("Sber", "https://www.sberbank.com", "Moscow", ["finance", "tech"]),
        _employer("Kaspersky", "https://www.kaspersky.com", "Moscow", ["cybersecurity", "tech"]),
        _employer("VK", "https://vk.com", "Moscow / St. Petersburg", ["tech", "media"]),
    ],
}

_JOBS: dict[str, list[FutureInsightsJob]] = {
    "CA": [
        _job("Software Engineer (New Grad)", "Shopify", "Toronto / remote-friendly", "https://www.shopify.com/careers", ["CS", "SOFTWARE", "COMPUTER", "IT"]),
        _job("Business Analyst Graduate", "RBC", "Toronto", "https://jobs.rbc.com", ["BUSINESS", "FINANCE", "ANALYTICS", "COMMERCE"]),
        _job("Mechanical Engineering Intern/Grad", "Bombardier", "Montreal", "https://bombardier.com/en/careers", ["MECHANICAL", "ENGINEERING", "AEROSPACE"]),
    ],
    "US": [
        _job("Software Engineering New Grad", "Google", "Multiple US locations", "https://careers.google.com", ["CS", "SOFTWARE", "COMPUTER"]),
        _job("Investment Banking Analyst", "JPMorgan Chase", "New York", "https://careers.jpmorgan.com", ["FINANCE", "BUSINESS", "ECONOMICS"]),
        _job("Technology Consultant Analyst", "Deloitte", "Multiple US locations", "https://www2.deloitte.com/careers", ["BUSINESS", "IT", "CONSULTING"]),
    ],
    "UK": [
        _job("Graduate Software Engineer", "ARM", "Cambridge", "https://careers.arm.com", ["CS", "ELECTRONICS", "ENGINEERING"]),
        _job("Graduate Analyst", "HSBC", "London", "https://www.hsbc.com/careers", ["FINANCE", "BUSINESS", "ECONOMICS"]),
        _job("Engineering Graduate Scheme", "Rolls-Royce", "Derby", "https://careers.rolls-royce.com", ["ENGINEERING", "MECHANICAL", "AEROSPACE"]),
    ],
    "AU": [
        _job("Graduate Software Engineer", "Atlassian", "Sydney", "https://www.atlassian.com/company/careers", ["CS", "SOFTWARE"]),
        _job("Graduate Program", "Commonwealth Bank", "Sydney", "https://www.commbank.com.au/about-us/careers.html", ["FINANCE", "BUSINESS"]),
    ],
    "DE": [
        _job("Developer Associate", "SAP", "Walldorf / hubs", "https://jobs.sap.com", ["CS", "SOFTWARE", "IT"]),
        _job("Graduate Engineer", "Siemens", "Munich / national", "https://jobs.siemens.com", ["ENGINEERING", "ELECTRICAL", "MECHANICAL"]),
    ],
    "JP": [
        _job("Global New Grad (Engineering)", "Sony", "Tokyo", "https://www.sony.com/en/jobs", ["ENGINEERING", "CS", "ELECTRONICS"]),
        _job("New Graduate (Product/Tech)", "Rakuten", "Tokyo", "https://corp.rakuten.co.jp/careers", ["CS", "BUSINESS", "PRODUCT"]),
    ],
    "FR": [
        _job("Graduate Consultant", "Capgemini", "Paris / national", "https://www.capgemini.com/careers", ["BUSINESS", "IT", "CONSULTING"]),
        _job("Engineering Graduate", "Airbus", "Toulouse", "https://www.airbus.com/en/careers", ["ENGINEERING", "AEROSPACE"]),
    ],
    "NZ": [
        _job("Graduate Software Engineer", "Xero", "Wellington / Auckland", "https://www.xero.com/about/careers", ["CS", "SOFTWARE"]),
    ],
    "SG": [
        _job("Technology Graduate", "DBS Bank", "Singapore", "https://www.dbs.com/careers", ["CS", "FINANCE", "IT"]),
        _job("Software Engineer (Early Career)", "Grab", "Singapore", "https://grab.careers", ["CS", "SOFTWARE"]),
    ],
    "AE": [
        _job("Graduate Programme", "Emirates", "Dubai", "https://www.emirates.com/careers", ["BUSINESS", "AVIATION", "HOSPITALITY"]),
    ],
    "SE": [
        _job("Graduate Software Engineer", "Spotify", "Stockholm", "https://www.lifeatspotify.com", ["CS", "SOFTWARE"]),
    ],
    "CH": [
        _job("Graduate Talent Program", "Nestlé", "Vevey / hubs", "https://www.nestle.com/jobs", ["BUSINESS", "FOOD", "SCIENCE"]),
        _job("Early Talent (Science/Tech)", "Roche", "Basel", "https://careers.roche.com", ["LIFE SCIENCES", "BIOTECH", "PHARMA"]),
    ],
    "IE": [
        _job("Technology Consulting Analyst", "Accenture", "Dublin", "https://www.accenture.com/careers", ["BUSINESS", "IT", "CONSULTING"]),
        _job("Software Engineering New Grad", "Google", "Dublin", "https://careers.google.com", ["CS", "SOFTWARE"]),
    ],
    "NL": [
        _job("Graduate Engineer", "ASML", "Veldhoven", "https://www.asml.com/careers", ["ENGINEERING", "ELECTRICAL", "PHYSICS"]),
        _job("Graduate Software Engineer", "Booking.com", "Amsterdam", "https://careers.booking.com", ["CS", "SOFTWARE"]),
    ],
    "NO": [
        _job("Graduate Programme", "Equinor", "Stavanger / Oslo", "https://www.equinor.com/careers", ["ENGINEERING", "ENERGY", "BUSINESS"]),
        _job("Graduate Analyst", "DNB", "Oslo", "https://www.dnb.no/en/about-us/careers", ["FINANCE", "BUSINESS"]),
    ],
    "PL": [
        _job("Junior / Graduate Software Engineer", "CD Projekt", "Warsaw", "https://www.cdprojekt.com/en/jobs", ["CS", "SOFTWARE", "GAMING"]),
        _job("Graduate Technology Role", "Allegro", "Warsaw / Poznań", "https://careers.allegro.eu", ["CS", "SOFTWARE", "PRODUCT"]),
    ],
    "HK": [
        _job("Graduate Analyst", "HSBC", "Hong Kong", "https://www.hsbc.com.hk/careers", ["FINANCE", "BUSINESS"]),
        _job("Graduate Programme", "Cathay Pacific", "Hong Kong", "https://careers.cathaypacific.com", ["BUSINESS", "AVIATION"]),
    ],
    "MY": [
        _job("Graduate Programme", "Petronas", "Kuala Lumpur", "https://www.petronas.com/careers", ["ENGINEERING", "BUSINESS", "ENERGY"]),
        _job("Technology Graduate", "Maybank", "Kuala Lumpur", "https://www.maybank.com/en/careers", ["CS", "FINANCE", "IT"]),
    ],
    "QA": [
        _job("Graduate Programme", "Qatar Airways", "Doha", "https://www.qatarairways.com/careers", ["BUSINESS", "AVIATION", "HOSPITALITY"]),
        _job("Early Career / Graduate", "QatarEnergy", "Doha", "https://www.qatarenergy.qa/careers", ["ENGINEERING", "ENERGY"]),
    ],
    "IN": [
        _job("Assistant System Engineer / Graduate", "Tata Consultancy Services", "Multi-city", "https://www.tcs.com/careers", ["CS", "IT", "SOFTWARE"]),
        _job("Systems Engineer Trainee", "Infosys", "Bengaluru / hubs", "https://www.infosys.com/careers", ["CS", "SOFTWARE"]),
    ],
    "RU": [
        _job("Junior Software Engineer", "Yandex", "Moscow", "https://yandex.com/jobs", ["CS", "SOFTWARE"]),
        _job("Graduate / Early Career", "Sber", "Moscow", "https://www.sberbank.com/careers", ["FINANCE", "TECH", "BUSINESS"]),
    ],
}

_DEFAULT_ROI = FutureInsightsRoi(
    tuition_baseline="Confirm with target institutions — band not yet seeded for this destination",
    health_fees_note="Verify mandatory health / insurance requirements for the study visa",
    median_starting_salary="Request local graduate outcome data for the program discipline",
    break_even_horizon="Model against the student’s budget band once tuition quotes are known",
    ten_year_yield_note="Combine salary, PR pathways, and sponsorship likelihood in counsellor notes",
    currency="—",
)

_DEFAULT_CITY = FutureInsightsCityLiving(
    shared_housing_monthly="Confirm campus housing office / local listings",
    private_rent_monthly="Confirm city-level rent indices near campus",
    transit_index_note="Map campus ↔ housing commute before commit",
    grocery_index_note="Use local CPI / Numbeo-style indices as a starting point",
    climate_snapshot="Review seasonal climate for the specific city",
    safety_snapshot="Use official campus and city safety briefings",
)


def _filter_jobs(
    jobs: list[FutureInsightsJob], program_codes: list[str]
) -> list[FutureInsightsJob]:
    if not program_codes:
        return jobs
    needles = [code.strip().upper() for code in program_codes if code and code.strip()]
    if not needles:
        return jobs
    matched: list[FutureInsightsJob] = []
    for job in jobs:
        blob = " ".join([job.title, *job.program_disciplines]).upper()
        if any(needle in blob or any(needle in d.upper() for d in job.program_disciplines) for needle in needles):
            matched.append(job)
            continue
        # Soft match: any discipline token overlaps program code fragments.
        if any(
            any(token and token in needle or needle in token for token in d.upper().replace("_", " ").split())
            for d in job.program_disciplines
            for needle in needles
        ):
            matched.append(job)
    return matched or jobs


def _pack_for(intel_code: str, comparison: CountryComparisonItem, program_codes: list[str]) -> FutureInsightsDestinationPack:
    roi = _ROI.get(intel_code, _DEFAULT_ROI.model_copy(update={"tuition_baseline": comparison.tuition_band}))
    if intel_code not in _ROI:
        roi = roi.model_copy(update={"tuition_baseline": comparison.tuition_band})

    immigration = FutureInsightsImmigration(
        psw_rights=comparison.psw_rights,
        work_limits=comparison.work_limits,
        dependent_rules=comparison.dependent_rules,
        pathway_notes=_PATHWAYS.get(intel_code, []),
        language_requirements=comparison.language_requirements or "",
        proof_of_funds_summary=comparison.proof_of_funds_summary,
    )

    city_living = _CITY.get(intel_code, _DEFAULT_CITY)
    location_label = _to_iso2(intel_code)
    return FutureInsightsDestinationPack(
        country_code=intel_code,
        country_iso2=_to_iso2(intel_code),
        as_of=_AS_OF,
        disclaimer=_DISCLAIMER,
        roi=roi,
        employers=list(_EMPLOYERS.get(intel_code, [])),
        jobs=_filter_jobs(list(_JOBS.get(intel_code, [])), program_codes),
        immigration=immigration,
        city_living=city_living,
        habitat=build_habitat(
            location_label=location_label,
            country_code=intel_code,
            city_living=city_living,
        ),
        institutions=[],
    )


def _soft_filter_by_location(
    employers: list[FutureInsightsEmployer],
    jobs: list[FutureInsightsJob],
    city_name: str | None,
    state_name: str | None,
) -> tuple[list[FutureInsightsEmployer], list[FutureInsightsJob]]:
    needles = [n.lower() for n in [city_name or "", state_name or ""] if n and len(n) >= 3]
    if not needles:
        return employers, jobs

    def hits(text: str | None) -> bool:
        blob = (text or "").lower()
        return any(needle in blob for needle in needles)

    local_employers = [e for e in employers if hits(e.city_or_region) or hits(e.name)]
    local_jobs = [j for j in jobs if hits(j.location) or hits(j.employer_name)]
    return (local_employers or employers, local_jobs or jobs)


def _build_institution_contexts(
    db: Session,
    institution_ids: list[int],
    program_codes: list[str],
    destination_by_iso: dict[str, FutureInsightsDestinationPack],
) -> None:
    """Attach metro-local employers/jobs onto each destination pack in-place."""
    if not institution_ids:
        return

    from app.models.academia_geography import GeographyCity, GeographyState
    from app.models.academia_institution import Institution
    from app.models.country import Country
    from app.services.future_insights_metros import (
        METRO_PACKS,
        match_metro_key,
        metro_location_label,
    )

    rows = (
        db.query(Institution)
        .filter(Institution.id.in_(institution_ids))
        .all()
    )
    if not rows:
        return

    city_ids = {row.city_id for row in rows if row.city_id}
    state_ids = {row.state_id for row in rows if row.state_id}
    country_ids = {row.country_id for row in rows if row.country_id}

    cities = {
        c.id: c
        for c in db.query(GeographyCity).filter(GeographyCity.id.in_(city_ids)).all()
    } if city_ids else {}
    states = {
        s.id: s
        for s in db.query(GeographyState).filter(GeographyState.id.in_(state_ids)).all()
    } if state_ids else {}
    countries = {
        c.id: c
        for c in db.query(Country).filter(Country.id.in_(country_ids)).all()
    } if country_ids else {}

    for row in rows:
        city = cities.get(row.city_id) if row.city_id else None
        state = states.get(row.state_id) if row.state_id else None
        country = countries.get(row.country_id) if row.country_id else None
        iso2 = (country.iso2 if country and country.iso2 else "").upper()
        intel = _normalize_intel_code(iso2)
        pack = destination_by_iso.get(iso2) or destination_by_iso.get(_to_iso2(intel))
        if pack is None:
            continue

        city_name = city.name if city else None
        state_name = state.name if state else None
        metro_key = match_metro_key(
            country_code=intel or iso2,
            institution_name=row.name,
            city_name=city_name,
            state_name=state_name,
        )
        fallback_label = ", ".join(
            part for part in [city_name, state_name, iso2 or intel] if part
        ) or (row.name or "Campus area")

        if metro_key and metro_key in METRO_PACKS:
            metro = METRO_PACKS[metro_key]
            employers = list(metro.get("employers") or [])
            jobs = _filter_jobs(list(metro.get("jobs") or []), program_codes)
            city_living = metro.get("city_living")
            location_label = metro_location_label(metro_key, fallback_label)
            metro_matched = True
        else:
            # Soft-filter national pack by city/state text when no metro seed exists.
            if pack is not None:
                base = pack
            elif intel in COMPARISON_MATRIX:
                base = _pack_for(intel, COMPARISON_MATRIX[intel], program_codes)
            else:
                continue
            employers, jobs = _soft_filter_by_location(
                list(base.employers), list(base.jobs), city_name, state_name
            )
            jobs = _filter_jobs(jobs, program_codes)
            city_living = None
            location_label = fallback_label
            metro_matched = False
            pack = pack or base

        assert pack is not None
        habitat = build_habitat(
            location_label=location_label,
            country_code=intel or iso2,
            metro_key=metro_key,
            city_living=city_living or pack.city_living,
        )
        pack.institutions.append(
            FutureInsightsInstitutionContext(
                institution_id=row.id,
                institution_name=row.name,
                city_name=city_name,
                state_name=state_name,
                country_iso2=iso2 or pack.country_iso2,
                metro_key=metro_key,
                location_label=location_label,
                metro_matched=metro_matched,
                employers=employers,
                jobs=jobs,
                city_living=city_living,
                habitat=habitat,
            )
        )


def get_future_insights(
    country_codes: list[str],
    program_codes: list[str] | None = None,
    institution_ids: list[int] | None = None,
    db: Session | None = None,
) -> FutureInsightsResponse:
    programs = program_codes or []
    destinations: list[FutureInsightsDestinationPack] = []
    unsupported: list[str] = []
    seen: set[str] = set()

    for raw in country_codes:
        intel = _normalize_intel_code(raw)
        if not intel or intel in seen:
            continue
        seen.add(intel)
        comparison = COMPARISON_MATRIX.get(intel)
        if comparison is None:
            unsupported.append(raw.strip().upper() or intel)
            continue
        destinations.append(_pack_for(intel, comparison, programs))

    if institution_ids and db is not None:
        by_iso: dict[str, FutureInsightsDestinationPack] = {}
        for dest in destinations:
            by_iso[dest.country_iso2.upper()] = dest
            by_iso[dest.country_code.upper()] = dest
        # Also ensure packs exist for institution countries not in the aspiration list.
        from app.models.academia_institution import Institution
        from app.models.country import Country

        extra_ids = [i for i in institution_ids if i]
        if extra_ids:
            inst_rows = db.query(Institution).filter(Institution.id.in_(extra_ids)).all()
            for inst in inst_rows:
                if not inst.country_id:
                    continue
                country = db.query(Country).filter(Country.id == inst.country_id).first()
                if not country or not country.iso2:
                    continue
                intel = _normalize_intel_code(country.iso2)
                if intel in seen:
                    continue
                comparison = COMPARISON_MATRIX.get(intel)
                if comparison is None:
                    continue
                seen.add(intel)
                pack = _pack_for(intel, comparison, programs)
                destinations.append(pack)
                by_iso[pack.country_iso2.upper()] = pack
                by_iso[pack.country_code.upper()] = pack

        _build_institution_contexts(db, extra_ids, programs, by_iso)

    return FutureInsightsResponse(
        destinations=destinations,
        unsupported_countries=unsupported,
    )
