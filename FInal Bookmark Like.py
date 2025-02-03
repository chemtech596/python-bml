import logging
import cv2
import numpy as np
import hashlib
import os
import json
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext
)

# 🔹 Replace with your actual bot token
TOKEN = '7572122875:AAEWvIjM2Oz4PzrGd33qtdRByQATW9IKc6w'

# File to store video hashes
HASH_FILE = "video_hashes.json"

# Load existing hashes
def load_hashes():
    """Load video hashes from file to persist across restarts."""
    if os.path.exists(HASH_FILE):
        try:
            with open(HASH_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Error: JSON file corrupted. Resetting database.")
            return {}
    return {}

video_hashes = load_hashes()  # Load hashes at startup

# Store users' info, unique video IDs, and total link count
users_info = {}
video_database = {}  # Stores video IDs mapped to user IDs
total_links = 0  # Variable to count total links

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def save_hashes():
    """Save video hashes to file to persist across restarts."""
    with open(HASH_FILE, "w") as f:
        json.dump(video_hashes, f, indent=4)

def reset_hashes():
    """Reset (clear) all stored video hashes."""
    global video_hashes
    video_hashes = {}  # Clear dictionary
    save_hashes()
    logger.info("All stored video hashes have been reset.")

def get_video_hash(video_path):
    """Generate a hash for a given video file."""
    if not os.path.exists(video_path):
        print(f"Error: File {video_path} does not exist.")
        return None
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Unable to open video file {video_path}.")
        return None
    
    hasher = hashlib.sha256()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (64,64))  # Resize for consistency
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
        hasher.update(gray.tobytes())  # Add frame to hash
    
    cap.release()
    os.remove(video_path)  # Delete after processing
    return hasher.hexdigest()

async def start(update: Update, context: CallbackContext):
    """Handles the /start command."""
    await update.message.reply_text("Welcome! Send a link. Only one post per user.")

async def handle_message(update: Update, context: CallbackContext):
    """Processes user messages and tracks unsafe users or duplicate videos."""
    global total_links
    user = update.message.from_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    first_name = user.first_name  # Store the first name
    message_text = update.message.text.strip().lower() if update.message.text else None

    logger.info(f"User {username} ({user_id}) sent a message.")

    # Handle link messages
    if message_text and "http" in message_text:
        if user_id not in users_info:
            total_links += 1  # Increment link count
        
        users_info[user_id] = {
            "username": username, 
            "first_name": first_name,  # Store the first name
            "link": message_text, 
            "status": "unsafe"  # Initially unsafe
        }
        logger.info(f"User {username} stored with link: {message_text}")

    # Handle confirmation messages
    elif message_text and user_id in users_info:
        if message_text in ["ad", "all done", "done"]:
            users_info[user_id]["status"] = "safe"
            logger.info(f"User {username} marked as safe.")
            await update.message.reply_text("✅ Thank you! You are now marked as safe.")

    # Handle video messages
    elif update.message.video:
        video_id = update.message.video.file_unique_id  # Unique ID for the video
        file = await update.message.video.get_file()
        file_path = f"temp_{file.file_id}.mp4"
        await file.download_to_drive(file_path)  # Download video
        
        video_hash = get_video_hash(file_path)
        if video_hash is None:
            await update.message.reply_text("⚠️ Error processing the video. Please try again.")
            return

        # Check for duplicate videos
        if video_hash in video_hashes:
            original_user = video_hashes[video_hash]  # Get original sender's username
            if original_user != username:  # If a different user sends the same video
                await update.message.reply_text(f"🚨 Duplicate detected! This video was first sent by **{original_user}**.")
            else:
                await update.message.reply_text("⚠️ You have already sent this video before!")
        else:
            video_hashes[video_hash] = username  # Store only the first sender's username
            save_hashes()  # Save updated hashes
            await update.message.reply_text("✅ Video received. You are now marked as safe.")

        # Store the video globally and mark user as safe
        video_database[video_id] = user_id  
        users_info[user_id] = {
            "username": username, 
            "first_name": first_name,  # Store the first name
            "link": None, 
            "status": "safe"
        }
        logger.info(f"User {username} sent a video and is now marked as safe.")

async def show_unsafe_list(update: Update, context: CallbackContext):
    """Displays the list of unsafe users dynamically each time."""
    unsafe_list = []

    # Loop through all users and collect those who are marked as unsafe
    for user_id, user_data in users_info.items():
        if user_data["status"] == "unsafe":
            # Construct user info string (username and first name)
            username = user_data.get('username', '')
            first_name = user_data.get('first_name', '')

            # Show both username and first name, prioritizing username if both are available
            if username and first_name:
                user_info = f"@{username} ({first_name})"
            elif username:  # Fallback if only username is available
                user_info = f"@{username}"
            elif first_name:  # Fallback if only first name is available
                user_info = f"{first_name}"
            else:
                user_info = "Unknown"

            unsafe_list.append(user_info)
    
    logger.info(f"Current unsafe list: {unsafe_list}")

    # Respond with the unsafe users list
    if unsafe_list:
        await update.message.reply_text(f"🚨 Unsafe users: {', '.join(unsafe_list)}")
    else:
        await update.message.reply_text("✅ No users are in the unsafe list.")

async def reset_data(update: Update, context: CallbackContext):
    """Clears all stored user data and resets the total link count."""
    global users_info, video_database, total_links
    users_info.clear()
    video_database.clear()
    total_links = 0
    reset_hashes()
    logger.info("All user data has been cleared. Total link count reset.")
    await update.message.reply_text("🔄 All data has been reset. You can start a new session now!")

async def show_total_links(update: Update, context: CallbackContext):
    """Displays the total number of links received."""
    await update.message.reply_text(f"📊 Total links received: {total_links}")

def main():
    """Runs the bot."""
    app = Application.builder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unsafe", show_unsafe_list))
    app.add_handler(CommandHandler("reset", reset_data))  
    app.add_handler(CommandHandler("count", show_total_links))  

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))  
    app.add_handler(MessageHandler(filters.VIDEO, handle_message))  

    print("Bot is running... Press CTRL+C to stop.")
    
    # Start the bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
