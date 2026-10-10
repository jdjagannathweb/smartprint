import subprocess
import threading
import time
import re
import os
from pathlib import Path

PUBLIC_URL = None
TUNNEL_PROC = None

def run_tunnel():
    global PUBLIC_URL, TUNNEL_PROC
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-R", "80:127.0.0.1:8000",
        "nokey@localhost.run"
    ]
    
    while True:
        try:
            TUNNEL_PROC = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in iter(TUNNEL_PROC.stdout.readline, ''):
                if not line:
                    break
                # Find URL like https://abc1234.lhr.life
                match = re.search(r"https://[a-zA-Z0-9-]+\.lhr\.life", line)
                if match:
                    PUBLIC_URL = match.group(0)
                    print(f"\n>>> [PUBLIC MOBILE URL]: {PUBLIC_URL} <<<\n")
            TUNNEL_PROC.wait()
        except Exception as e:
            print(f"Tunnel error: {e}")
        time.sleep(5)

def start_tunnel_thread():
    t = threading.Thread(target=run_tunnel, daemon=True)
    t.start()
    return t

def get_public_url():
    global PUBLIC_URL
    return PUBLIC_URL
