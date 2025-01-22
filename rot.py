import os
import subprocess
import threading
import psutil
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv
from time import time
import re

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "").split(",")))

# Pyrogram Client
app = Client("encoder_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Global variables for CPU monitoring
monitor_flag = True


def monitor_cpu_usage():
    """Monitors CPU usage in a separate thread."""
    while monitor_flag:
        cpu_usage = psutil.cpu_percent(interval=1, percpu=False)
        print(f"Current CPU Usage: {cpu_usage}%")


def sanitize_filename(filename):
    """Sanitize the filename to remove unsafe characters."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def download_video_with_actual_name(url, progress_message):
    """Downloads a video file from a URL while preserving the actual filename."""
    try:
        progress_message.edit("📥 Starting download...")

        wget_command = [
            "wget", "--content-disposition", url, "--progress=dot:mega"
        ]

        process = subprocess.Popen(wget_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        output = ""
        last_update_time = time()

        for line in process.stderr:
            output += line
            current_time = time()

            if "saved" in line or "%" in line and (current_time - last_update_time > 5):
                progress_message.edit(f"📥 Downloading...\n{line.strip()}")
                last_update_time = current_time

        process.wait()
        if process.returncode == 0:
            for line in output.splitlines():
                if "‘" in line and "’ saved" in line:
                    raw_filename = line.split("‘")[1].split("’")[0]
                    filename = sanitize_filename(raw_filename)
                    progress_message.edit(f"✅ Download completed: {filename}")
                    return os.path.abspath(filename)
            progress_message.edit("✅ Download completed, but filename could not be determined.")
            return None
        else:
            raise RuntimeError("Download failed")
    except Exception as e:
        progress_message.edit(f"❌ Error during download: {e}")
        return None


def encode_video(input_file, output_file, progress_message):
    """Encodes a video using FFmpeg with reduced progress updates."""
    global monitor_flag
    monitor_flag = True

    # Start the CPU monitoring thread
    cpu_thread = threading.Thread(target=monitor_cpu_usage)
    cpu_thread.start()

    ffmpeg_command = [
        "ffmpeg", "-i", input_file, "-preset", "faster", "-c:v", "libx265",
        "-crf", "20", "-tune", "animation", "-pix_fmt", "yuv420p10le",
        "-threads", "16", "-metadata", "title=Encoded By @THECIDANIME",
        "-metadata:s:v", "title=@THECIDANIME", "-metadata:s:a", "title=@THECIDANIME",
        "-metadata:s:s", "title=@THECIDANIME", "-map", "0:v", "-c:a", "aac", "-map", "0:a",
        "-c:s", "copy", "-map", "0:s?", output_file
    ]

    process = subprocess.Popen(
        ffmpeg_command, stderr=subprocess.PIPE, universal_newlines=True
    )

    last_update_time = time()
    try:
        for line in process.stderr:
            current_time = time()

            # Update progress every 10 seconds
            if "frame=" in line and (current_time - last_update_time > 10):
                progress_message.edit(f"⚙️ Encoding in progress...\n{line.strip()}")
                last_update_time = current_time

        process.wait()
        if process.returncode == 0:
            progress_message.edit("✅ Encoding completed successfully!")
        else:
            raise RuntimeError("Encoding failed")
    finally:
        monitor_flag = False
        cpu_thread.join()


@app.on_message(filters.private & filters.text)
def handle_message(client, message):
    """Handles video downloads and encodings via URL."""
    if message.from_user.id not in OWNER_IDS:
        message.reply_text("❌ You do not have permission to use this bot!")
        return

    progress_message = message.reply_text("📥 Processing your request...")
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        progress_message.edit("❌ Please provide a valid URL!")
        return

    # Download the file from the URL
    file_path = download_video_with_actual_name(url, progress_message)
    if not file_path:
        return

    # Prepare output file path
    input_name, ext = os.path.splitext(file_path)
    output_file = f"{input_name}_encoded_{int(time())}.mkv"

    # Encode the video
    try:
        progress_message.edit("⚙️ Encoding the video, please wait...")
        encode_video(file_path, output_file, progress_message)
    except Exception as e:
        progress_message.edit(f"❌ Error during encoding: {e}")
        return

    # Upload the encoded file
    progress_message.edit("📤 Uploading the encoded file...")

    try:
        client.send_document(
            chat_id=message.chat.id,
            document=output_file,
            caption="Here is your encoded video! Encoded by @THECIDANIME"
        )
        progress_message.edit("✅ Upload completed!")
    except Exception as e:
        progress_message.edit(f"❌ Error during upload: {e}")

    # Clean up files
    if os.path.exists(file_path):
        os.remove(file_path)
    else:
        print(f"File not found: {file_path}")

    if os.path.exists(output_file):
        os.remove(output_file)
    else:
        print(f"Output file not found: {output_file}")


@app.on_message(filters.private & filters.document)
def handle_file_upload(client, message):
    """Handles video file uploads from users."""
    if message.from_user.id not in OWNER_IDS:
        message.reply_text("❌ You do not have permission to use this bot!")
        return

    progress_message = message.reply_text("📥 Processing your file...")

    # Download the file sent by the user
    file = message.document
    file_path = client.download_media(file.file_id, file_name=file.file_name)

    # Prepare output file path
    input_name, ext = os.path.splitext(file_path)
    output_file = f"{input_name}_encoded_{int(time())}.mkv"

    # Encode the video
    try:
        progress_message.edit("⚙️ Encoding the video, please wait...")
        encode_video(file_path, output_file, progress_message)
    except Exception as e:
        progress_message.edit(f"❌ Error during encoding: {e}")
        return

    # Upload the encoded file
    progress_message.edit("📤 Uploading the encoded file...")

    try:
        client.send_document(
            chat_id=message.chat.id,
            document=output_file,
            caption="Here is your encoded video! Encoded by @THECIDANIME"
        )
        progress_message.edit("✅ Upload completed!")
    except Exception as e:
        progress_message.edit(f"❌ Error during upload: {e}")

    # Clean up files
    if os.path.exists(file_path):
        os.remove(file_path)
    else:
        print(f"File not found: {file_path}")

    if os.path.exists(output_file):
        os.remove(output_file)
    else:
        print(f"Output file not found: {output_file}")


if __name__ == "__main__":
    print("Bot is running...")
    app.run()
