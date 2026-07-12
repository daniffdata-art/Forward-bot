import os
import asyncio
import hashlib
import re
import sys
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, RPCError

# ===== CONFIGURATION (Railway Variables Se) =====
API_ID = int(os.environ.get("API_ID", 34783446))
API_HASH = os.environ.get("API_HASH", "c1da051b38797498a32805f762c36bd3")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", -1004438106656))
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL", -1003783045906))
DELETE_DELAY = int(os.environ.get("DELETE_DELAY", 10))
GAP_DELAY = int(os.environ.get("GAP_DELAY", 10))

# ===== BLOCK BINS =====
BLOCK_BINS = {
    "440066", "453201", "497171", "431195", "411146", "525849", "453924",
    "492913", "454638", "465865", "461785", "437401", "404924", "455600",
    "483583", "445444", "450065", "428550", "402911", "421494", "486483",
    "511796", "520976", "516921", "554042", "400843", "522401", "417363",
    "530436", "441014", "545147", "540132", "535081", "5392047", "543484",
    "559728", "457226", "466582", "485358", "592333", "528181", "431322",
    "550568", "465487", "462436", "417878", "404247", "516815", "468040",
    "532541", "457224", "539305", "430451", "521152", "489364", "554702",
    "549041", "483074", "457227", "543891", "444111", "466582", "489358",
    "408383", "419327", "412998", "554027", "412329", "440768", "401711"
}

# ===== SETUP =====
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

posted = set()
dup_file = "posted_cc.txt"
if os.path.exists(dup_file):
    with open(dup_file, "r") as f:
        posted = set(line.strip() for line in f)

cc_regex = re.compile(
    r'(\d{16})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
    re.IGNORECASE
)

msg_counter = 0
lock = asyncio.Lock()

# ===== BOT STARTED MESSAGE =====
async def send_startup_message():
    try:
        await client.send_message(
            TARGET_CHANNEL,
            "🤖 Bot is working! 🚀\n\n✅ Successfully deployed on Railway\n✅ Monitoring source channel\n✅ Ready to forward CCs"
        )
        print("✅ Startup message sent to target channel!")
    except Exception as e:
        print(f"⚠️ Could not send startup message: {e}")

# ===== MESSAGE HANDLER =====
@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    global msg_counter
    if not event.text:
        return

    print(f"\n📥 New message received!")
    matches = cc_regex.findall(event.text)
    if not matches:
        print("⚠️ No CC found")
        return

    for match in matches:
        try:
            if len(match) >= 4:
                card_number = match[0].strip()
                month = match[1].strip()
                year = match[2].strip()
                cvv = match[3].strip()
                full_cc = f"{card_number}|{month}|{year}|{cvv}"
                prefix6 = card_number[:6]

                print(f"🔍 Found CC: {card_number[:6]}***")

                if not card_number.startswith('4'):
                    print(f"⛔ Skipped non-Visa: {prefix6}")
                    continue

                if prefix6 in BLOCK_BINS:
                    print(f"⛔ Skipped blocked BIN: {prefix6}")
                    continue

                card_hash = hashlib.md5(card_number.encode()).hexdigest()
                if card_hash in posted:
                    print(f"♻️ Duplicate skipped")
                    continue

                async with lock:
                    posted.add(card_hash)
                    with open(dup_file, "a") as f:
                        f.write(card_hash + "\n")

                    try:
                        msg = await client.send_message(TARGET_CHANNEL, f"/br {full_cc}")
                        msg_counter += 1
                        print(f"✅ SENT: {full_cc[:10]}*** | Total: {msg_counter}")
                        await asyncio.sleep(DELETE_DELAY)
                        await msg.delete()
                        print(f"🗑️ Deleted")
                        await asyncio.sleep(GAP_DELAY)
                    except FloodWaitError as e:
                        print(f"⏳ Flood wait: {e.seconds}s")
                        await asyncio.sleep(e.seconds + 5)
                    except Exception as e:
                        print(f"❌ Error: {e}")
        except Exception as e:
            print(f"❌ Processing error: {e}")
            continue

# ===== MAIN =====
async def main():
    print("=" * 50)
    print("🚀 BOT STARTING...")
    print("=" * 50)

    try:
        await client.start()
        print("✅ Client started successfully!")
    except Exception as e:
        print(f"❌ Failed to start client: {e}")
        sys.exit(1)

    try:
        me = await client.get_me()
        print(f"🤖 Connected as: {me.first_name} (@{me.username})")
    except Exception as e:
        print(f"❌ Failed to get user info: {e}")
        sys.exit(1)

    try:
        await client.get_entity(SOURCE_CHANNEL)
        print(f"✅ Source channel accessible: {SOURCE_CHANNEL}")
    except Exception as e:
        print(f"⚠️ Source channel error: {e}")

    try:
        await client.get_entity(TARGET_CHANNEL)
        print(f"✅ Target channel accessible: {TARGET_CHANNEL}")
    except Exception as e:
        print(f"⚠️ Target channel error: {e}")

    await send_startup_message()

    print("=" * 50)
    print("🤖 BOT IS RUNNING!")
    print("=" * 50)

    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
