# test_pin_upgrade.py
import asyncio
import hashlib
import os
from dotenv import load_dotenv
load_dotenv()

from app.modules.merchant.service import merchant_service

async def test():
    # 1. Get a real merchant ID from your DB
    result = merchant_service.supabase.table("merchants").select("id, pin_hash").limit(1).execute()
    if not result.data:
        print("❌ No merchants found")
        return
    
    merchant = result.data[0]
    merchant_id = merchant["id"]
    print(f"Testing merchant: {merchant_id}")
    print(f"Current hash: {merchant['pin_hash'][:20]}...")

    # 2. Set a known SHA-256 hash for PIN "1234"
    sha256_hash = hashlib.sha256("1234".encode()).hexdigest()
    merchant_service.supabase.table("merchants").update({
        "pin_hash": sha256_hash
    }).eq("id", merchant_id).execute()
    print(f"✅ Set SHA-256 hash: {sha256_hash[:20]}...")

    # 3. Verify the PIN — should succeed AND upgrade
    result = await merchant_service._verify_merchant_pin(merchant_id, "1234")
    print(f"PIN verify result: {result}")

    # 4. Check the hash was upgraded
    updated = merchant_service.supabase.table("merchants").select("pin_hash").eq("id", merchant_id).execute()
    new_hash = updated.data[0]["pin_hash"]
    if new_hash.startswith("$2b$"):
        print(f"✅ Hash upgraded to bcrypt: {new_hash[:20]}...")
    else:
        print(f"❌ Hash NOT upgraded: {new_hash[:20]}...")

    # 5. Verify wrong PIN returns False
    wrong = await merchant_service._verify_merchant_pin(merchant_id, "9999")
    print(f"Wrong PIN returns False: {wrong == False} {'✅' if wrong == False else '❌'}")

asyncio.run(test())

