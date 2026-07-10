import os
import asyncio
import json
import hashlib
import re
import sys
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, RPCError

# ===== TRY REDIS =====
try:
    import redis
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False
    print("⚠️ Redis not installed, using file backup")

class SmartSession:
    """Session with Redis + File + Auto-Renew"""
    
    def __init__(self):
        self.api_id = int(os.environ.get("API_ID", 34783446))
        self.api_hash = os.environ.get("API_HASH", "c1da051b38797498a32805f762c36bd3")
        self.session_key = "telegram_session_v1"
        
        # Setup Redis
        self.redis = None
        if REDIS_AVAILABLE:
            redis_url = os.environ.get("REDIS_URL")
            if redis_url:
                try:
                    self.redis = redis.from_url(redis_url)
                    # Test connection
                    self.redis.ping()
                    print("✅ Redis connected successfully!")
                except Exception as e:
                    print(f"⚠️ Redis connection failed: {e}")
        
        self.client = None
        self.session_file = "session_backup.json"
    
    def _load_session(self):
        """Load session from Redis or file"""
        # Try Redis first
        if self.redis:
            try:
                session = self.redis.get(self.session_key)
                if session:
                    print("✅ Session loaded from Redis")
                    return session.decode()
            except Exception as e:
                print(f"⚠️ Redis read failed: {e}")
        
        # Try file backup
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    session = data.get('session_string')
                    if session:
                        print("✅ Session loaded from file backup")
                        return session
        except Exception as e:
            print(f"⚠️ File read failed: {e}")
        
        # Try environment variable
        session = os.environ.get("STRING_SESSION")
        if session:
            print("✅ Session loaded from environment")
            return session
        
        return None
    
    def _save_session(self, session_str):
        """Save session to Redis and file"""
        # Save to Redis
        if self.redis:
            try:
                self.redis.set(self.session_key, session_str)
                self.redis.expire(self.session_key, 30*24*60*60)  # 30 days
                print("💾 Session saved to Redis")
            except Exception as e:
                print(f"⚠️ Redis save failed: {e}")
        
        # Save to file
        try:
            with open(self.session_file, 'w') as f:
                json.dump({
                    'session_string': session_str,
                    'timestamp': str(asyncio.get_event_loop().time())
                }, f)
            print("💾 Session saved to file backup")
        except Exception as e:
            print(f"⚠️ File save failed: {e}")
    
    async def get_client(self):
        """Get client with auto-renewal"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                session_str = self._load_session()
                
                if session_str:
                    print(f"🔄 Using saved session (attempt {attempt+1})")
                    self.client = TelegramClient(
                        StringSession(session_str),
                        self.api_id,
                        self.api_hash
                    )
                    await self.client.start()
                    
                    # Verify it works
                    me = await self.client.get_me()
                    print(f"✅ Connected as: {me.first_name} (@{me.username})")
                    
                    # Save refreshed session
                    new_session = self.client.session.save()
                    if new_session != session_str:
                        self._save_session(new_session)
                    
                    return self.client
                
                else:
                    # No session found, create new
                    print("🔄 Creating brand new session...")
                    self.client = TelegramClient(
                        StringSession(),
                        self.api_id,
                        self.api_hash
                    )
                    await self.client.start()
                    
                    # Save new session
                    new_session = self.client.session.save()
                    self._save_session(new_session)
                    print("✅ New session created and saved!")
                    
                    me = await self.client.get_me()
                    print(f"✅ Connected as: {me.first_name} (@{me.username})")
                    
                    return self.client
                    
            except Exception as e:
                print(f"❌ Attempt {attempt+1} failed: {e}")
                
                # If session is invalid, delete it and try again
                if "SESSION" in str(e).upper() or "AUTH" in str(e).upper():
                    print("⚠️ Session invalid, clearing...")
                    if self.redis:
                        self.redis.delete(self.session_key)
                    if os.path.exists(self.session_file):
                        os.remove(self.session_file)
                
                if attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
        
        raise Exception("❌ Failed to connect after all attempts")

# ===== BOT CONFIGURATION =====
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

# ===== MAIN BOT =====
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
client = None  # Will be set in main

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    global msg_counter
    
    if not event.text:
        return
    
    print(f"\n📥 New message received!")
    
    matches = cc_regex.findall(event.text)
    if not matches:
        matches = simple_cc_regex.findall(event.text)
    
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
                
                # Block non-Visa
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
                    
                    for attempt in range(3):
                        try:
                            msg = await client.send_message(TARGET_CHANNEL, f"/br {full_cc}")
                            msg_counter += 1
                            print(f"✅ SENT: {full_cc[:10]}*** | Total: {msg_counter}")
                            
                            await asyncio.sleep(DELETE_DELAY)
                            try:
                                await msg.delete()
                                print(f"🗑️ Deleted")
                            except:
                                pass
                            
                            await asyncio.sleep(GAP_DELAY)
                            break
                            
                        except FloodWaitError as e:
                            print(f"⏳ Flood wait: {e.seconds}s")
                            await asyncio.sleep(e.seconds + 5)
                        except Exception as e:
                            print(f"❌ Error: {e}")
                            if attempt < 2:
                                await asyncio.sleep(5)
                                
        except Exception as e:
            print(f"❌ Processing error: {e}")
            continue

async def keep_alive():
    """Keep session alive"""
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            if client:
                await client.get_me()
                print("💓 Session alive")
        except Exception as e:
            print(f"⚠️ Keep-alive failed: {e}")
            # Try to reconnect
            try:
                await client.disconnect()
                await client.connect()
                print("✅ Reconnected")
            except:
                print("❌ Reconnect failed")

async def main():
    global client
    
    print("="*50)
    print("🚀 SMART BOT STARTING...")
    print("="*50)
    
    # Get smart session
    smart = SmartSession()
    client = await smart.get_client()
    
    # Start keep-alive
    asyncio.create_task(keep_alive())
    
    # Check channels
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
    
    print("="*50)
    print("🤖 BOT IS RUNNING!")
    print("Press Ctrl+C to stop")
    print("="*50)
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
