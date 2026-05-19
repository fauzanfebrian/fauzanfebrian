import urllib.request
import json
import os
import re
from datetime import datetime

USERNAME = "fauzanfebrian"
PROFILE_REPO = f"{USERNAME}/{USERNAME}"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
MAX_LOGS = 5


def api_request(url):
    """Handles GitHub API requests with authentication."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Fauzan-Profile-Updater",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"API Request Failed for {url}: {e}")
        return None


def fetch_commit_message(repo_name, sha):
    """Fallback to fetch commit message if omitted from the event payload."""
    data = api_request(f"https://api.github.com/repos/{repo_name}/commits/{sha}")
    if data and "commit" in data:
        return data["commit"]["message"].split("\n")[0]
    return "Updated repository"


def filter_and_format_events(events):
    logs = []
    repo_counts = {}

    for event in events:
        if len(logs) >= MAX_LOGS:
            break

        repo_name = event["repo"]["name"]

        # Anti-Loop: Never log activity from the profile repository itself
        if repo_name == PROFILE_REPO:
            continue

        event_type = event["type"]
        date_str = datetime.strptime(
            event["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).strftime("%b %d")

        # Keep feed diverse: max 2 entries per repository
        if repo_counts.get(repo_name, 0) >= 2:
            continue

        log_entry = None

        if event_type == "PushEvent":
            head_sha = event["payload"].get("head")
            if not head_sha:
                continue

            commits = event["payload"].get("commits", [])

            # If payload has commits, use the latest one. Otherwise, fetch it via API.
            if commits:
                latest_commit = commits[-1]
                msg = latest_commit["message"].split("\n")[0]
                author_name = latest_commit["author"]["name"].lower()
            else:
                msg = fetch_commit_message(repo_name, head_sha)
                author_name = USERNAME  # Assume user if fetching fallback

            # Noise filters: Drop automated syncs and bot commits
            if "[skip ci]" in msg.lower() or "auto-sync" in msg.lower():
                continue
            if "bot" in author_name:
                continue

            commit_url = f"https://github.com/{repo_name}/commit/{head_sha}"
            log_entry = f"- **[@{USERNAME}](https://github.com/{USERNAME})** pushed to [{repo_name}](https://github.com/{repo_name}) ({date_str}) — {msg} [`{head_sha[:7]}`]({commit_url})"

        elif (
            event_type == "CreateEvent"
            and event["payload"].get("ref_type") == "repository"
        ):
            log_entry = f"- **[@{USERNAME}](https://github.com/{USERNAME})** created repository [{repo_name}](https://github.com/{repo_name}) ({date_str})"

        elif event_type == "PullRequestEvent":
            action = event["payload"]["action"]
            pr = event["payload"]["pull_request"]
            if action in ["opened", "closed"]:
                status = "Merged" if pr.get("merged") else action.capitalize()

                # Skip closed but unmerged PRs
                if status == "Closed":
                    continue

                log_entry = f"- **[@{USERNAME}](https://github.com/{USERNAME})** {status.lower()} PR in [{repo_name}](https://github.com/{repo_name}) ({date_str}) — {pr['title']} [#{pr['number']}]({pr['html_url']})"

        elif event_type == "IssuesEvent" and event["payload"].get("action") == "opened":
            issue = event["payload"]["issue"]
            log_entry = f"- **[@{USERNAME}](https://github.com/{USERNAME})** opened issue in [{repo_name}](https://github.com/{repo_name}) ({date_str}) — {issue['title']} [#{issue['number']}]({issue['html_url']})"

        elif (
            event_type == "ReleaseEvent"
            and event["payload"].get("action") == "published"
        ):
            release = event["payload"]["release"]
            log_entry = f"- **[@{USERNAME}](https://github.com/{USERNAME})** published [{release['name'] or release['tag_name']}]({release['html_url']}) in [{repo_name}](https://github.com/{repo_name}) ({date_str})"

        if log_entry:
            logs.append(log_entry)
            repo_counts[repo_name] = repo_counts.get(repo_name, 0) + 1

    return logs


def main():
    events = api_request(f"https://api.github.com/users/{USERNAME}/events/public")
    if not events:
        print("No events found or API failed.")
        return

    logs = filter_and_format_events(events)

    if logs:
        # Add a "Last Updated" timestamp for transparency
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        markdown_logs = "\n".join(logs) + f"\n\n> 🕒 *Last updated: {timestamp}*" + "\n"
    else:
        markdown_logs = "_No recent high-signal activity found._\n"

    try:
        with open("README.md", "r") as f:
            readme = f.read()

        # Targets the exact HTML comments in your README to inject the logs
        pattern = (
            r"(<!--START_SECTION:system_logs-->\n).*?(<!--END_SECTION:system_logs-->)"
        )
        replacement = f"\\1{markdown_logs}\\2"
        new_readme = re.sub(pattern, replacement, readme, flags=re.DOTALL)

        with open("README.md", "w") as f:
            f.write(new_readme)

        print("System logs updated successfully.")
    except Exception as e:
        print(f"Failed to update README.md: {e}")


if __name__ == "__main__":
    main()
