"""Canonical Inquiry Hub taxonomy and initial frequently asked questions."""

from __future__ import annotations

INQUIRY_TAXONOMY = [
    {"code": "1", "name": "Counselling", "children": [
        {"code": "1.1", "name": "Intake Session"},
        {"code": "1.2", "name": "Candidate Registration"},
        {"code": "1.3", "name": "Profile Creation"},
    ]},
    {"code": "2", "name": "College Finding", "children": [
        {"code": "2.1", "name": "Shortlist Target Colleges"},
        {"code": "2.2", "name": "Confirm Program Fit"},
        {"code": "2.3", "name": "University Outreach"},
        {"code": "2.4", "name": "Finalize Target Colleges"},
    ]},
    {"code": "3", "name": "Document Readiness", "children": [
        {"code": "3.1", "name": "Academic Transcripts"},
        {"code": "3.2", "name": "Standardized Test Scores", "children": [
            {"code": "3.2.1", "name": "Confirm Required Tests"},
            {"code": "3.2.2", "name": "Book Exam Slot"},
            {"code": "3.2.3", "name": "Upload Score Report"},
        ]},
        {"code": "3.3", "name": "Financial Proofs"},
        {"code": "3.4", "name": "Statement of Purpose (SOP)"},
        {"code": "3.5", "name": "Recommendation Letters (LORs)"},
        {"code": "3.6", "name": "Identity & Passport"},
    ]},
    {"code": "4", "name": "Admission Processing", "children": [
        {"code": "4.1", "name": "Application Submission"},
        {"code": "4.2", "name": "Tuition & Fee Payment"},
        {"code": "4.3", "name": "Final Offer & Visa Documentation"},
    ]},
    {"code": "5", "name": "Visa Processing", "children": [
        {"code": "5.1", "name": "Document & Financials"},
        {"code": "5.2", "name": "Visa Application"},
        {"code": "5.3", "name": "Biometrics & Medical Examination"},
        {"code": "5.4", "name": "Visa Interview Preparation"},
        {"code": "5.5", "name": "Visa Decision & Issuance"},
    ]},
    {"code": "6", "name": "Pre-Departure & Travel", "children": [
        {"code": "6.1", "name": "Travel Booking"},
        {"code": "6.2", "name": "Accommodation"},
        {"code": "6.3", "name": "Orientation"},
        {"code": "6.4", "name": "Compliance & FX"},
        {"code": "6.5", "name": "Arrival Tracking"},
    ]},
    {"code": "7", "name": "Landing", "children": [
        {"code": "7.1", "name": "Airport Arrival"},
        {"code": "7.2", "name": "Campus Check-In"},
        {"code": "7.3", "name": "Settling In"},
        {"code": "7.4", "name": "Bank & Telecom"},
        {"code": "7.5", "name": "Academic Registration"},
    ]},
    {"code": "OTHER", "name": "Others", "children": []},
]


def _faq(path: str, question: str, answer: str) -> dict[str, str]:
    return {"path": path, "question": question, "answer": answer}


INQUIRY_FAQ_SEED = [
    _faq("1.1", "What should I expect during our very first intake meeting?", "The intake session is a diagnostic discussion where the counselor evaluates your academic history, career objectives, preferred study destinations, and financial boundaries to establish a preliminary roadmap."),
    _faq("1.1", "Do parents need to attend this initial session?", "Yes, parent participation is highly encouraged during the intake phase, especially to align on budget planning, financial proof requirements, and safety preferences."),
    _faq("1.2", "What triggers official registration with Nexus after counseling?", "Registration occurs once you agree to the counselling terms, select your service package tier, and are officially converted to a qualified prospect in our system."),
    _faq("1.2", "What immediate deliverables do I receive post-registration?", "You will receive your unique student identifier (`STU-[ID]`), login access to the Nexus portal, and a formal guidance document mapping out your upcoming processing phases."),
    _faq("1.3", "How is my profile finalized, and what data is prioritized?", "Your profile is compiled by aggregating your academic transcripts, standardized test status, extracurricular history, and financial constraints into a centralized digital dossier."),
    _faq("1.3", "Can my profile be updated later if my GPA or test scores change?", "Yes, your Account Manager can update your academic and test metrics in the system anytime before final institutional submissions occur."),
    _faq("2.1", "How many universities will be included in my initial shortlist?", "Typically, a balanced list of 6 to 8 universities is curated, categorized into ambitious, target, and safe options based on your academic profile."),
    _faq("2.1", "Can I suggest my own university choices to add to the shortlist?", "Absolutely. Your preferences, target locations, and dream schools are cross-referenced with our database to evaluate admission viability."),
    _faq("2.2", "How do you ensure the chosen degree program matches my long-term career goals?", "We review course modules, internship opportunities, faculty expertise, and post-graduation employment outcomes to verify that the curriculum aligns with your objectives."),
    _faq("2.2", "What happens if a specific program has unique prerequisite courses I haven't taken?", "Your counselor will flag missing prerequisites early and advise on bridge courses or alternative program options that match your background."),
    _faq("2.3", "What kind of communication is sent to universities during outreach?", "Inquiries regarding specific admissions criteria, credit transfers, portfolio expectations, or rolling deadline updates are submitted directly to admissions offices."),
    _faq("2.3", "How long does it typically take for universities to respond to outreach queries?", "Most universities respond within 3 to 7 business days, though peak application seasons can extend response windows to two weeks."),
    _faq("2.4", "How do we narrow down the shortlists to the final applications?", "We evaluate application fees, acceptance rates, upcoming deadlines, and your personal preferences to lock down a final set of 3 to 5 target institutions."),
    _faq("2.4", "Can I apply to more universities than what is included in my service package?", "Yes, additional university applications can be processed by upgrading your service tier or adding custom module add-ons through your Account Manager."),
    _faq("3.1", "Are digital copies of mark sheets sufficient, or do I need physical attested transcripts?", "While digital scans are used for initial portal reviews and preliminary uploads, most universities eventually require official physical transcripts sealed and attested by your prior institution."),
    _faq("3.1", "What naming format should I use when uploading my academic transcripts?", "Files must follow the standardized convention: `STU-[ID]_[Name]_bachelor_transcript_[Source]_[Date]_[Time].pdf`."),
    _faq("3.2.1", "How do I know which standardized tests (IELTS, TOEFL, GRE, GMAT) are mandatory for my chosen universities?", "Test requirements are determined based on your target country, university admission policy, and program guidelines mapped during college finding."),
    _faq("3.2.2", "Should I book my test date before or after starting university shortlisting?", "It is recommended to book your exam slot early in the timeline so that official scores are ready well before university application deadlines open."),
    _faq("3.2.3", "How are official score reports submitted to universities?", "You must request the official testing agency to send scores directly to the university code, while also uploading your score report PDF using the format `STU-[ID]_[Name]_ielts_scorecard_[Source]_[Date]_[Time].pdf`."),
    _faq("3.3", "What documents are accepted as proof of funds for visa and university applications?", "Bank statements covering a specific historical period (usually 3 to 6 months), fixed deposit certificates, sanctioned education loan letters, and official scholarship award letters are accepted."),
    _faq("3.4", "Will Nexus write my Statement of Purpose entirely, or do I need to provide inputs?", "We use a collaborative approach: you provide a detailed personal background questionnaire and core motivations, and our expert consultants help structure, draft, and refine the SOP."),
    _faq("3.5", "How many Letters of Recommendation do I need, and who should write them?", "Most Master's and Bachelor's programs require 2 to 3 LORs, ideally a mix of academic professors who know your work and professional supervisors if you have work experience."),
    _faq("3.6", "What passport validity is required before applying for universities and visas?", "Your passport must generally remain valid for at least 6 months beyond your intended program completion date, though a minimum of 2 years of remaining validity is safer."),
    _faq("4.1", "Who submits the actual application forms to the universities?", "Your assigned Account Manager handles portal data entry, document attachments, and final institutional submission to ensure error-free applications."),
    _faq("4.2", "How do I pay university application fees and initial tuition deposits securely?", "Nexus guides you through secure international wire transfers, forex card transactions, or approved online payment gateways directly to the university's bank account."),
    _faq("4.3", "What is the difference between a Conditional Offer and an Unconditional Offer?", "A Conditional Offer requires you to fulfill pending criteria (such as final exam results or language proofs), whereas an Unconditional Offer confirms full acceptance into the program."),
    _faq("5.1", "How meticulous does the visa file assembly need to be?", "Extremely meticulous; visa officers follow strict compliance guidelines, and minor discrepancies in financial aging or document naming can lead to immediate visa refusals."),
    _faq("5.2", "Who fills out the complex online visa application forms (e.g., DS-160 for the US)?", "Your Account Manager drafts the application forms based on your verified data, which you then review and approve prior to final electronic submission and fee payment."),
    _faq("5.3", "Where do I go to complete my biometric data collection and medical exams?", "Biometrics must be done at official government-approved Visa Application Centres (VAC), and medical examinations must be completed at embassy-certified panel physicians."),
    _faq("5.4", "Will Nexus conduct mock interviews for my embassy visa appointment?", "Yes, specialized mock interview sessions are conducted by senior counselors to prepare you for common visa officer questions regarding your study plan, finances, and ties to your home country."),
    _faq("5.5", "What happens immediately after my visa is approved?", "Your passport is stamped or a digital visa counterfoil is issued, and it is dispatched or collected from the visa application center."),
    _faq("6.1", "When is the best time to book my flight tickets to study abroad?", "Flights should be booked immediately after receiving your visa confirmation, typically 4 to 6 weeks before your university's official orientation date to secure better rates."),
    _faq("6.2", "Should I live on-campus in university dorms or off-campus private housing?", "Your counselor will present the pros and cons of both options based on availability, cost, proximity to campus, and your personal preference."),
    _faq("6.3", "Is attending the university's pre-arrival or international student orientation mandatory?", "While sometimes optional, attending online or in-person orientation is heavily advised as it covers course registration, campus tours, and legal compliance guidelines."),
    _faq("6.4", "What types of insurance coverage do I need before traveling?", "Mandatory health insurance (such as OSHC in Australia or IHS in the UK) alongside travel and medical evacuation insurance must be secured prior to departure."),
    _faq("6.5", "How does airport pickup work when I land?", "If opted into your arrival package, university representatives or trusted local partners coordinate airport pickup and direct transit to your accommodation."),
    _faq("7.1", "What documents should I keep easily accessible in my carry-on luggage during immigration?", "Keep your passport, valid visa, university acceptance letter, accommodation proof, financial proofs, and insurance documents in your hand luggage for easy presentation at immigration control."),
    _faq("7.2", "What is the first thing I need to do once I arrive at the university campus?", "You must visit the international student services desk to complete your physical check-in, verify your passport, and collect your student ID card."),
    _faq("7.3", "How do I handle setting up utilities, internet, and groceries in my new apartment?", "Your local Nexus support network or student guides assist you with local grocery stores, setting up utility connections, and understanding neighborhood safety."),
    _faq("7.4", "Which local mobile network operator should I choose when landing?", "We guide you on student-friendly telecom providers that offer affordable data plans and international calling bundles right at the airport or local stores."),
    _faq("7.5", "When do I select and register for my semester classes?", "Class registration typically occurs during orientation week or just prior, and your counselor can provide remote guidance on choosing the right credit modules."),
    _faq("OTHER", "What happens if my query does not fit into any predefined process or sub-process?", "You can file it under the **Others** category in the Inquiry Hub module, where custom administrative queries can be logged, answered, and later re-categorized if needed."),
]


def resolve_inquiry_path(path: str) -> dict[str, str | None]:
    """Resolve a leaf code to denormalized hierarchy fields."""
    for process in INQUIRY_TAXONOMY:
        if process["code"] == path:
            return {
                "process_code": process["code"],
                "process_name": process["name"],
                "subprocess_code": None,
                "subprocess_name": None,
                "nested_process_code": None,
                "nested_process_name": None,
            }
        for subprocess in process["children"]:
            if subprocess["code"] == path:
                return {
                    "process_code": process["code"],
                    "process_name": process["name"],
                    "subprocess_code": subprocess["code"],
                    "subprocess_name": subprocess["name"],
                    "nested_process_code": None,
                    "nested_process_name": None,
                }
            for nested in subprocess.get("children", []):
                if nested["code"] == path:
                    return {
                        "process_code": process["code"],
                        "process_name": process["name"],
                        "subprocess_code": subprocess["code"],
                        "subprocess_name": subprocess["name"],
                        "nested_process_code": nested["code"],
                        "nested_process_name": nested["name"],
                    }
    raise ValueError(f"Unknown Inquiry Hub path: {path}")
