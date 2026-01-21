import requests
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

SHOWS_FILE = "shows.json"
TVMAZE_SEARCH_URL = "https://api.tvmaze.com/singlesearch/shows"
TVMAZE_EPISODES_URL = "https://api.tvmaze.com/shows/{}/episodes"

# ---------------- Email Configuration ----------------
EMAIL_CONFIG = {
      "sender_email": os.environ.get("EMAIL_SENDER"),
    "sender_password": os.environ.get("EMAIL_PASSWORD"),
    "recipient_email": os.environ.get("EMAIL_RECEIVER"),
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587
}
# -----------------------------------------------------

def load_shows():
    """Load shows from JSON file."""
    if not os.path.exists(SHOWS_FILE):
        return []
    with open(SHOWS_FILE, "r") as f:
        return json.load(f).get("shows", [])

def save_shows(shows):
    """Save shows to JSON file."""
    with open(SHOWS_FILE, "w") as f:
        json.dump({"shows": shows}, f, indent=2)

def get_show_id(show_name):
    """Get TVMaze show ID by name."""
    response = requests.get(TVMAZE_SEARCH_URL, params={"q": show_name})
    response.raise_for_status()
    return response.json()["id"]

def get_episodes(show_id):
    """Get all episodes for a show ID."""
    response = requests.get(TVMAZE_EPISODES_URL.format(show_id))
    response.raise_for_status()
    return response.json()

def is_aired(airdate):
    """Check if episode has already aired."""
    if airdate is None or airdate == "":
        return False
    return datetime.strptime(airdate, "%Y-%m-%d").date() <= datetime.today().date()

def check_new_episodes(show):
    """Return list of new episodes for a show."""
    show_id = get_show_id(show["name"])
    episodes = get_episodes(show_id)
    new_episodes = []
    for ep in episodes:
        if not is_aired(ep["airdate"]):
            continue
        if ep["season"] > show["last_season"] or \
           (ep["season"] == show["last_season"] and ep["number"] > show["last_episode"]):
            new_episodes.append(ep)
    return new_episodes

def send_email_alert(new_episodes_dict, no_new_episodes_list=None):
    """Send an email alert for newly released episodes and status of other shows."""
    if not EMAIL_CONFIG["sender_email"] or not EMAIL_CONFIG["sender_password"] or not EMAIL_CONFIG["recipient_email"]:
        print("⚠️ Email configuration not set. Please configure EMAIL_CONFIG in the script.\n")
        return

    if no_new_episodes_list is None:
        no_new_episodes_list = []

    try:
        # Build email content
        subject = "Episode Tracker Update"
        body = "Episode Update:\n\n"
        
        if new_episodes_dict:
            body += "🔥 NEW EPISODES:\n\n"
            for show_name, episodes in new_episodes_dict.items():
                body += f"{show_name}:\n"
                for ep in episodes:
                    body += f"  • S{ep['season']:02}E{ep['number']:02} (aired {ep['airdate']}) — {ep['name']}\n"
                body += "\n"
        
        if no_new_episodes_list:
            body += "✅ NO NEW EPISODES:\n\n"
            for show_name in no_new_episodes_list:
                body += f"  • {show_name}\n"
            body += "\n"

        # Create email
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = EMAIL_CONFIG["recipient_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Send email
        server = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
        server.starttls()
        server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
        server.send_message(msg)
        server.quit()

        print("✅ Email alert sent successfully!\n")

    except Exception as e:
        print(f"⚠️ Error sending email: {e}\n")

def add_new_show():
    """Interactive function to add a new show (optional)."""
    shows = load_shows()
    print("\n➕ Add a new show")
    name = input("Show name: ").strip()
    for show in shows:
        if show["name"].lower() == name.lower():
            print("⚠️ This show already exists.\n")
            return
    try:
        season = int(input("Last watched season (use 0 if none): "))
        episode = int(input("Last watched episode (use 0 if none): "))
    except ValueError:
        print("⚠️ Season and episode must be numbers.\n")
        return
    shows.append({"name": name, "last_season": season, "last_episode": episode})
    save_shows(shows)
    print(f"✅ '{name}' added successfully!\n")

def remove_show():
    """Interactive function to remove a show."""
    shows = load_shows()
    
    if not shows:
        print("\n⚠️ No shows to remove.\n")
        return
    
    print("\n🗑️ Remove a show")
    print("Current shows:")
    for i, show in enumerate(shows, 1):
        print(f"  {i}) {show['name']}")
    
    try:
        choice = int(input("Enter the number of the show to remove: ").strip())
        if 1 <= choice <= len(shows):
            removed_show = shows.pop(choice - 1)
            save_shows(shows)
            print(f"✅ '{removed_show['name']}' removed successfully!\n")
        else:
            print("❌ Invalid selection.\n")
    except ValueError:
        print("⚠️ Please enter a valid number.\n")

def update_show():
    """Interactive function to update watched episodes for a show."""
    shows = load_shows()
    
    if not shows:
        print("\n⚠️ No shows to update.\n")
        return
    
    print("\n📝 Update watched episodes")
    print("Current shows:")
    for i, show in enumerate(shows, 1):
        print(f"  {i}) {show['name']} (S{show['last_season']}E{show['last_episode']})")
    
    try:
        choice = int(input("Enter the number of the show to update: ").strip())
        if 1 <= choice <= len(shows):
            show = shows[choice - 1]
            print(f"\nUpdating '{show['name']}'...")
            print(f"Current: Season {show['last_season']}, Episode {show['last_episode']}")
            
            try:
                new_season = int(input("New season number: ").strip())
                new_episode = int(input("New episode number: ").strip())
                
                show['last_season'] = new_season
                show['last_episode'] = new_episode
                save_shows(shows)
                print(f"✅ '{show['name']}' updated to S{new_season}E{new_episode}!\n")
            except ValueError:
                print("⚠️ Season and episode must be numbers.\n")
        else:
            print("❌ Invalid selection.\n")
    except ValueError:
        print("⚠️ Please enter a valid number.\n")

def check_all_shows_and_email():
    """Check all shows and send email alerts automatically."""
    shows = load_shows()
    if not shows:
        print("⚠️ No shows found in shows.json. Add shows first.\n")
        return
    
    print("\n🔍 Checking for new episodes...\n")
    
    new_episodes_dict = {}
    no_new_episodes = []
    
    for show in shows:
        try:
            new_eps = check_new_episodes(show)
            if new_eps:
                print(f"🔥 New episodes for {show['name']}:")
                for ep in new_eps:
                    print(f"  • S{ep['season']:02}E{ep['number']:02} (aired {ep['airdate']}) — {ep['name']}")
                print()
                new_episodes_dict[show['name']] = new_eps
            else:
                no_new_episodes.append(show['name'])
        except Exception as e:
            print(f"⚠️ Error checking {show['name']}: {e}\n")
    
    # Display shows with no new episodes together
    if no_new_episodes:
        print(f"✅ No new episodes: {', '.join(no_new_episodes)}\n")
    
    send_email_alert(new_episodes_dict, no_new_episodes)

def main():
    """Optional interactive menu."""
    while True:
        print("📺 TV Episode Tracker")
        print("1) Check for new episodes (auto email)")
        print("2) Add a new show")
        print("3) Remove a show")
        print("4) Update watched episodes")
        print("5) Exit")
        choice = input("Select an option: ").strip()
        if choice == "1":
            check_all_shows_and_email()
        elif choice == "2":
            add_new_show()
        elif choice == "3":
            remove_show()
        elif choice == "4":
            update_show()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid option.\n")

if __name__ == "__main__":
    # For Task Scheduler: run automatically without user input
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        check_all_shows_and_email()
    else:
        main()
