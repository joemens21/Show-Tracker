import requests
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


# ============== Configuration ==============
SHOWS_FILE = "shows.json"
MOVIES_FILE = "movies.json"
CONFIG_FILE = "config.json"

# TV Shows API (TVMaze)
TVMAZE_SEARCH_URL = "https://api.tvmaze.com/singlesearch/shows"
TVMAZE_EPISODES_URL = "https://api.tvmaze.com/shows/{}/episodes"

# Movies API (TMDb)
TMDB_API_KEY = "a913dafaf4d76f18dafd87b1847c5f8f"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_MOVIE_URL = "https://api.themoviedb.org/3/movie/{}"

# Load Email Configuration
def load_email_config():
    """Load email configuration from environment variables or config.json file."""
    config = {}
    
    # First, try to load from environment variables (for GitHub Actions)
    env_sender = os.environ.get("EMAIL_SENDER")
    env_password = os.environ.get("EMAIL_PASSWORD")
    env_receiver = os.environ.get("EMAIL_RECEIVER")
    
    if env_sender or env_password or env_receiver:
        config = {
            "sender_email": env_sender,
            "sender_password": env_password,
            "recipient_email": env_receiver,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587
        }
    # Fall back to config.json file (for local development)
    elif os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                file_config = json.load(f)
                config = file_config.get("email", {})
        except Exception as e:
            print(f"⚠️ Error loading config file: {e}")
    
    return config

EMAIL_CONFIG = load_email_config()

# ============== TV Show Functions ==============
def load_shows():
    if not os.path.exists(SHOWS_FILE):
        return []
    with open(SHOWS_FILE, "r") as f:
        return json.load(f).get("shows", [])

def save_shows(shows):
    with open(SHOWS_FILE, "w") as f:
        json.dump({"shows": shows}, f, indent=2)

def get_show_id(show_name):
    response = requests.get(TVMAZE_SEARCH_URL, params={"q": show_name})
    response.raise_for_status()
    return response.json()["id"]

def get_episodes(show_id):
    response = requests.get(TVMAZE_EPISODES_URL.format(show_id))
    response.raise_for_status()
    return response.json()

def is_aired(airdate):
    if airdate is None or airdate == "":
        return False
    return datetime.strptime(airdate, "%Y-%m-%d").date() <= datetime.today().date()

def check_new_episodes(show):
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

# ============== Movie Functions ==============
def load_movies():
    if not os.path.exists(MOVIES_FILE):
        return []
    with open(MOVIES_FILE, "r") as f:
        return json.load(f).get("movies", [])

def save_movies(movies):
    with open(MOVIES_FILE, "w") as f:
        json.dump({"movies": movies}, f, indent=2)

def search_movie(title):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title
    }
    response = requests.get(TMDB_SEARCH_URL, params=params)
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None

def get_movie_details(movie_id):
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(TMDB_MOVIE_URL.format(movie_id), params=params)
    response.raise_for_status()
    return response.json()

def check_movie_status(movie):
    details = get_movie_details(movie["tmdb_id"])
    release_date_str = details.get("release_date")
    
    if not release_date_str:
        return {
            "status": "unknown",
            "title": details["title"],
            "message": "No release date available"
        }
    
    release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
    today = datetime.today().date()
    days_until = (release_date - today).days
    
    if days_until < 0:
        return {
            "status": "released",
            "title": details["title"],
            "release_date": release_date_str,
            "days_ago": abs(days_until)
        }
    elif days_until == 0:
        return {
            "status": "today",
            "title": details["title"],
            "release_date": release_date_str
        }
    else:
        # All future movies now categorized as "upcoming" regardless of days
        return {
            "status": "upcoming",
            "title": details["title"],
            "release_date": release_date_str,
            "days_until": days_until
        }

# ============== Email Function ==============
def send_combined_email(tv_data, movie_data):
    """Send email with both TV episodes and movie updates."""
    if not EMAIL_CONFIG["sender_email"] or not EMAIL_CONFIG["sender_password"] or not EMAIL_CONFIG["recipient_email"]:
        print("⚠️ Email configuration not set.\n")
        return

    new_episodes = tv_data.get("new_episodes", {})
    no_new_episodes = tv_data.get("no_new_episodes", [])
    
    released_movies = movie_data.get("released", [])
    today_movies = movie_data.get("today", [])
    upcoming_movies = movie_data.get("upcoming", [])

    try:
        subject = "Episode Tracker Update"
        body = "Episode Update:\n\n"
        
        # TV Shows section
        if new_episodes:
            body += "🔥 NEW EPISODES:\n\n"
            for show_name, episodes in new_episodes.items():
                body += f"{show_name}:\n"
                for ep in episodes:
                    body += f"  • S{ep['season']:02}E{ep['number']:02} (aired {ep['airdate']}) — {ep['name']}\n"
                body += "\n"
        
        if no_new_episodes:
            body += "✅ NO NEW EPISODES:\n\n"
            for show_name in no_new_episodes:
                body += f"  • {show_name}\n"
            body += "\n"
        
        # Movies section
        if today_movies:
            body += "🎉 RELEASING TODAY:\n\n"
            for movie in today_movies:
                body += f"  • {movie['title']}\n"
            body += "\n"
        
        if upcoming_movies:
            body += "🔥 UPCOMING RELEASES:\n\n"
            for movie in sorted(upcoming_movies, key=lambda x: x['days_until']):
                body += f"  • {movie['title']} - {movie['release_date']} ({movie['days_until']} days)\n"
            body += "\n"
        
        if released_movies:
            body += "✅ RECENTLY RELEASED:\n\n"
            for movie in released_movies:
                if movie['days_ago'] <= 7:  # Only show releases within last week
                    body += f"  • {movie['title']} - {movie['release_date']} ({movie['days_ago']} days ago)\n"
            body += "\n"

        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = EMAIL_CONFIG["recipient_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
        server.starttls()
        server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
        server.send_message(msg)
        server.quit()

        print("✅ Email alert sent successfully!\n")

    except Exception as e:
        print(f"⚠️ Error sending email: {e}\n")

# ============== Check All Function ==============
def check_all_and_email():
    """Check both TV shows and movies, then send combined email."""
    print("\n🔍 Checking TV shows and movies...\n")
    
    # Check TV Shows
    shows = load_shows()
    tv_new_episodes = {}
    tv_no_new = []
    
    if shows:
        print("📺 Checking TV Shows:")
        for show in shows:
            try:
                new_eps = check_new_episodes(show)
                if new_eps:
                    print(f"  🔥 {show['name']}: {len(new_eps)} new episode(s)")
                    tv_new_episodes[show['name']] = new_eps
                else:
                    tv_no_new.append(show['name'])
            except Exception as e:
                print(f"  ⚠️ Error checking {show['name']}: {e}")
        print()
    
    # Check Movies
    movies = load_movies()
    movie_released = []
    movie_today = []
    movie_upcoming = []
    
    if movies:
        print("🎬 Checking Movies:")
        for movie in movies:
            try:
                status = check_movie_status(movie)
                if status["status"] == "released":
                    if status['days_ago'] <= 7:
                        print(f"  ✅ {status['title']}: Released {status['days_ago']} days ago")
                    movie_released.append(status)
                elif status["status"] == "today":
                    print(f"  🎉 {status['title']}: RELEASING TODAY!")
                    movie_today.append(status)
                elif status["status"] == "upcoming":
                    print(f"  🔥 {status['title']}: {status['days_until']} days away")
                    movie_upcoming.append(status)
            except Exception as e:
                print(f"  ⚠️ Error checking {movie['title']}: {e}")
        print()
    
    # Send combined email
    tv_data = {
        "new_episodes": tv_new_episodes,
        "no_new_episodes": tv_no_new
    }
    movie_data = {
        "released": movie_released,
        "today": movie_today,
        "upcoming": movie_upcoming
    }
    
    send_combined_email(tv_data, movie_data)

# ============== Management Functions ==============
def add_show():
    shows = load_shows()
    print("\n➕ Add a TV show")
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

def add_movie():
    movies = load_movies()
    print("\n➕ Add a movie to track")
    title = input("Movie title: ").strip()
    
    print(f"🔍 Searching for '{title}'...")
    result = search_movie(title)
    
    if not result:
        print("❌ Movie not found. Try a different search term.\n")
        return
    
    for movie in movies:
        if movie["tmdb_id"] == result["id"]:
            print(f"⚠️ Already tracking '{result['title']}'.\n")
            return
    
    movies.append({
        "title": result["title"],
        "tmdb_id": result["id"],
        "added_date": datetime.today().strftime("%Y-%m-%d")
    })
    save_movies(movies)
    
    release_date = result.get("release_date", "Unknown")
    print(f"✅ Added '{result['title']}' (Release: {release_date})\n")

def remove_show():
    shows = load_shows()
    if not shows:
        print("\n⚠️ No shows to remove.\n")
        return
    print("\n🗑️ Remove a TV show")
    for i, show in enumerate(shows, 1):
        print(f"  {i}) {show['name']}")
    try:
        choice = int(input("Enter number: ").strip())
        if 1 <= choice <= len(shows):
            removed = shows.pop(choice - 1)
            save_shows(shows)
            print(f"✅ Removed '{removed['name']}'!\n")
        else:
            print("❌ Invalid selection.\n")
    except ValueError:
        print("⚠️ Please enter a valid number.\n")

def remove_movie():
    movies = load_movies()
    if not movies:
        print("\n⚠️ No movies to remove.\n")
        return
    print("\n🗑️ Remove a movie")
    for i, movie in enumerate(movies, 1):
        print(f"  {i}) {movie['title']}")
    try:
        choice = int(input("Enter number: ").strip())
        if 1 <= choice <= len(movies):
            removed = movies.pop(choice - 1)
            save_movies(movies)
            print(f"✅ Removed '{removed['title']}'!\n")
        else:
            print("❌ Invalid selection.\n")
    except ValueError:
        print("⚠️ Please enter a valid number.\n")

def update_show():
    shows = load_shows()
    if not shows:
        print("\n⚠️ No shows to update.\n")
        return
    print("\n📝 Update watched episodes")
    for i, show in enumerate(shows, 1):
        print(f"  {i}) {show['name']} (S{show['last_season']}E{show['last_episode']})")
    try:
        choice = int(input("Enter number: ").strip())
        if 1 <= choice <= len(shows):
            show = shows[choice - 1]
            new_season = int(input("New season: ").strip())
            new_episode = int(input("New episode: ").strip())
            show['last_season'] = new_season
            show['last_episode'] = new_episode
            save_shows(shows)
            print(f"✅ Updated to S{new_season}E{new_episode}!\n")
        else:
            print("❌ Invalid selection.\n")
    except ValueError:
        print("⚠️ Invalid input.\n")

# ============== Main Menu ==============
def main():
    while True:
        print("📺🎬 TV & Movie Tracker")
        print("1) Check all (TV + Movies) and send email")
        print("2) Add TV show")
        print("3) Add movie")
        print("4) Remove TV show")
        print("5) Remove movie")
        print("6) Update watched episodes")
        print("7) Exit")
        choice = input("Select option: ").strip()
        
        if choice == "1":
            check_all_and_email()
        elif choice == "2":
            add_show()
        elif choice == "3":
            add_movie()
        elif choice == "4":
            remove_show()
        elif choice == "5":
            remove_movie()
        elif choice == "6":
            update_show()
        elif choice == "7":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid option.\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        check_all_and_email()
    else:
        main()