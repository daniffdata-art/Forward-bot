import asyncio
import re
import hashlib
import os
import sys
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, RPCError

# ===== 🔐 ENVIRONMENT VARIABLES (Railway) =====
API_ID = int(os.environ.get("API_ID", 34783446))
API_HASH = os.environ.get("API_HASH", "c1da051b38797498a32805f762c36bd3")
STRING_SESSION = os.environ.get("STRING_SESSION", "")

SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", -1003728422300))
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL", -1003783045906))

DELETE_DELAY = int(os.environ.get("DELETE_DELAY", 10))
GAP_DELAY = int(os.environ.get("GAP_DELAY", 10))

BLOCK_BINS = {
    "440066","453201","497171","431195","411146","525849","453924",
    "492913","454638","465865","461785","437401","404924","455600",
    "483583","445444","450065","428550","402911","421494","486483",
    "511796","520976","516921","554042","400843","522401","417363",
    "530436","441014","545147","540132","535081","5392047","543484",
    "559728","457226","466582","485358","592333","528181","431322",
    "550568","465487","462436","417878","404247","516815","468040",
    "532541","457224","539305","430451","521152","489364","554702",
    "549041","483074","457227","543891","444111","466582","489358",
    "408383","419327","412998","554027","412329","440768","401711"
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
simple_cc_regex = re.compile(
    r'(\d{15,16})\s*[|/]\s*(\d{1,2})\s*[|/]\s*(\d{2,4})\s*[|/]\s*(\d{3,4})',
    re.IGNORECASE
)

msg_counter = 0
lock = asyncio.Lock()

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    global msg_counter
    
    if not event.text:
        return
    
    print(f"\n📥 New message received!")
    print(f"Message preview: {event.text[:100]}...")
    
    matches = cc_regex.findall(event.text)
    if not matches:
        matches = simple_cc_regex.findall(event.text)
    
    if not matches:
        print("⚠️ No CC found in message")
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
                
                print(f"🔍 Found CC: {card_number[:6]}*** | Exp: {month}/{year}")
                
                # Block non‑Visa cards
                if not card_number.startswith('4'):
                    print(f"⛔ Skipped non‑Visa card: {card_number[:6]}***")
                    continue
                
                # Check BIN block
                if prefix6 in BLOCK_BINS:
                    print(f"⛔ Skipped blocked BIN: {prefix6}")
                    continue
                
                card_hash = hashlib.md5(card_number.encode()).hexdigest()
                if card_hash in posted:
                    print(f"♻️ Duplicate CC, skipping...")
                    continue
                
                async with lock:
                    posted.add(card_hash)
                    with open(dup_file, "a") as f:
                        f.write(card_hash + "\n")
                    
                    for attempt in range(3):
                        try:
                            msg = await client.send_message(TARGET_CHANNEL, f"/br {full_cc}")
                            msg_counter += 1
                            print(f"✅ SENT: {full_cc[:10]}*** | Total: {msg_counter}")
                            
                            await asyncio.sleep(DELETE_DELAY)
                            try:
                                await msg.delete()
                                print(f"🗑️ Deleted message")
                            except Exception as e:
                                print(f"⚠️ Could not delete: {e}")
                            
                            await asyncio.sleep(GAP_DELAY)
                            break
                            
                        except FloodWaitError as e:
                            print(f"⏳ Flood wait: {e.seconds} seconds")
                            await asyncio.sleep(e.seconds + 5)
                        except RPCError as e:
                            print(f"⚠️ RPC Error (attempt {attempt+1}/3): {e}")
                            if attempt < 2:
                                await asyncio.sleep(5 * (attempt + 1))
                        except Exception as e:
                            print(f"❌ Error sending: {e}")
                            if attempt < 2:
                                await asyncio.sleep(3)
            else:
                print(f"⚠️ Invalid match format: {match}")
                
        except Exception as e:
            print(f"❌ Error processing CC: {e}")
            continue

async def main():
    try:
        print("🚀 Starting bot...")
        await client.start()
        
        me = await client.get_me()
        print(f"🤖 Bot Started as: {me.first_name} (@{me.username})")
        print(f"📡 Monitoring source channel: {SOURCE_CHANNEL}")
        print(f"🎯 Forwarding to target channel: {TARGET_CHANNEL}")
        print("🚀 Bot is running... Press Ctrl+C to stop\n")
        
        try:
            await client.get_entity(SOURCE_CHANNEL)
            print("✅ Source channel accessible")
        except Exception as e:
            print(f"⚠️ Warning: Source channel might not be accessible: {e}")
        
        try:
            await client.get_entity(TARGET_CHANNEL)
            print("✅ Target channel accessible")
        except Exception as e:
            print(f"⚠️ Warning: Target channel might not be accessible: {e}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Fatal error in main: {e}")
        raise

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
