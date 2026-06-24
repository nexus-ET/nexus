import sys
import os
import asyncio
from datetime import datetime, timedelta

# 1. Force path registration so Python can locate your app folder structure
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import MetaData, Table, insert

# Pull your configurations and models natively
from app.config import settings
from app.models.lead import Lead, LeadStage, LeadChannel 

async def seed_database():
    print("--- Starting Pure Standalone NEXUS CRM Database Seeding ---")
    
    # 2. Read your connection string directly from your .env file via app settings
    # We add '+asyncpg' to the protocol so the async engine knows which driver to fire up
    db_url = str(settings.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://")

    # 3. Initialize Async Engine
    engine = create_async_engine(db_url, echo=False)
    
    # 4. FORCE table creation via the async connection on the fly
    print("--- Synchronizing database schema tables via asyncpg... ---")
    try:
        async with engine.begin() as conn:
            # This extracts the metadata tied to your Lead class and builds it immediately if missing
            await conn.run_sync(Lead.metadata.create_all)
        print("--- 'leads' table successfully verified/created! ---")
    except Exception as e:
        print(f"❌ Migration Engine Error: {e}")
        await engine.dispose()
        return

    # 5. Reflect the table metadata from the active database
    metadata = MetaData()
    async with engine.begin() as conn:
        leads_table = await conn.run_sync(
            lambda sync_conn: Table("leads", metadata, autoload_with=sync_conn)
        )

    # 6. Define raw dictionary records to map into your columns
    mock_leads_data = [
        {
            "full_name": "Aarav Sharma",
            "email": "aarav.sharma@example.com",
            "phone_number": "+91 98765 43210",
            "channel": LeadChannel.WHATSAPP.value,
            "stage": LeadStage.AI_ACTIVE.value,
            "is_human_locked": False,
            "preferred_country": "Canada",
            "budget_tier": "$15k-$30k",
            "test_scores": "IELTS: 7.0 (Aiming for 7.5)",
            "academic_summary": "Completed B.Tech in CS. GPA: 8.4/10.",
            "ml_conversion_score": 78.5,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "full_name": "Chloe Dubois",
            "email": "chloe.dubois@example.com",
            "phone_number": "+33 6 1234 5678",
            "channel": LeadChannel.EMAIL.value,
            "stage": LeadStage.AI_ACTIVE.value,
            "is_human_locked": False,
            "preferred_country": "United Kingdom",
            "budget_tier": "$30k-$50k",
            "test_scores": "None (Waiver requested)",
            "academic_summary": "BBA graduate from Paris. 2 years marketing exp.",
            "ml_conversion_score": 62.0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "full_name": "Amara Okafor",
            "email": "amara.okafor@example.com",
            "phone_number": "+234 803 111 2222",
            "channel": LeadChannel.WHATSAPP.value,
            "stage": LeadStage.HANDOFF.value,
            "is_human_locked": False,
            "preferred_country": "United States",
            "budget_tier": "$50k+",
            "test_scores": "TOEFL: 108 | GRE: 322",
            "academic_summary": "B.Sc in Biochemistry. First Class Honors.",
            "ml_conversion_score": 94.2,
            "calendar_booking_id": "https://cal.com/nexus/consultation-amara",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "full_name": "Juan Rodriguez",
            "email": "juan.rod@example.com",
            "phone_number": "+54 11 4455 6677",
            "channel": LeadChannel.INSTAGRAM.value,
            "stage": LeadStage.ARCHIVE.value,
            "is_human_locked": False,
            "preferred_country": "Germany",
            "budget_tier": "<$15k",
            "test_scores": "IELTS: 7.0",
            "academic_summary": "Mechanical Engineer tracking tuition-free programs.",
            "ml_conversion_score": 99.0,
            "resolution_reason": "Enrolled - Fall 2026",
            "audit_report_url": "https://cloudflare-r2.nexus.storage/reports/audit_juan_rodriguez.pdf",
            "archived_at": datetime.utcnow() - timedelta(days=5),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]

    # 7. Push data directly out via transactional insertion
    async with engine.begin() as conn:
        await conn.execute(insert(leads_table), mock_leads_data)
        print("--- Database mock records injected successfully! ---")
        
    await engine.dispose()
    print("--- Engine disconnected. Seeding routine finished. ---")

if __name__ == "__main__":
    # 🎯 Modern Python 3.14+ approach: Use SelectorEventLoop explicitly on Windows
    if sys.platform == "win32":
        import selectors
        asyncio.run(
            seed_database(), 
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
        )
    else:
        # Linux / macOS continue to run perfectly on default configurations
        asyncio.run(seed_database())