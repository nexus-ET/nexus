"""Send test WhatsApp outreach to verify delivery."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.services.messaging import (
    open_whatsapp_conversation_window,
    send_message,
    WhatsAppDeliveryError,
)
from app.services.phone_utils import clean_phone_number
from app.services.whatsapp_config import (
    resolve_whatsapp_display_phone,
    resolve_whatsapp_phone_number_id,
)


async def main() -> None:
    phone = "+918754545407"
    line = resolve_whatsapp_display_phone()
    print("Active phone_number_id:", resolve_whatsapp_phone_number_id())
    print("Active display phone:", line)
    print("Sending template to", clean_phone_number(phone))
    try:
        await open_whatsapp_conversation_window(phone)
        print("Template step done (check logs for warnings)")
    except WhatsAppDeliveryError as exc:
        print("Template FAILED:", exc)
        return

    body = (
        f"Hi Ish! This is a NEXUS delivery test from {line}. "
        "If you see this, WhatsApp outreach is working."
    )
    try:
        await send_message(to_number=phone, body=body)
        print("Text message sent successfully")
    except WhatsAppDeliveryError as exc:
        print("Text FAILED:", exc)


if __name__ == "__main__":
    asyncio.run(main())
