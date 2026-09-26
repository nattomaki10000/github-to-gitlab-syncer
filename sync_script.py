import os
import shutil
import subprocess
import requests

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GL_TOKEN = os.environ.get("GL_TOKEN", "")
GH_USER = os.environ.get("GH_USER", "")  # 例: nattomaki10000

def get_github_public_repos():
    if not GH_USER:
        raise RuntimeError("GH_USER is required. Example: GH_USER=nattomaki10000")

    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    repos = []
    page = 1

    while True:
        response = requests.get(
            url,
            headers=headers,
            params={"visibility": "public", "affiliation": "owner", "per_page": 100, "page": page},
            timeout=30,
        )
        if response.status_code != 200:
            raise Exception(f"GitHub API Failed: {response.status_code} {response.text}")

        page_repos = response.json()
        if not page_repos:
            break

        for repo in page_repos:
            name = repo["name"]
            full_name = repo["full_name"]

            # 自分の公開リポジトリだけ
            if repo["owner"]["login"] != GH_USER:
                continue
            if repo["private"] or repo["fork"]:
                continue

            # ローカルの .github などと競合しないよう除外
            if name.startswith("."):
                continue

            # この同期用リポジトリ自身は除外
            if full_name == "nattomaki10000/github-to-gitlab-syncer":
                continue

            repos.append(full_name)

        page += 1

    return repos


def create_gitlab_repo(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]
    url = "https://gitlab.com/api/v4/projects"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}

    # 既存チェック
    check_url = f"{url}?search={repo_name}"
    res = requests.get(check_url, headers=headers, timeout=30)
    if res.status_code != 200:
        raise Exception(f"GitLab check failed: {res.status_code} {res.text}")

    existing = res.json()
    if any(p["name"] == repo_name for p in existing):
        return

    data = {
        "name": repo_name,
        "visibility": "public",
        "description": f"Synced from GitHub: {repo_full_name}",
    }
    post_res = requests.post(url, headers=headers, json=data, timeout=30)
    if post_res.status_code not in (200, 201, 202):
        raise Exception(f"GitLab create failed: {post_res.status_code} {post_res.text}")

    print(f"Created GitLab repository: {repo_name}")


def mirror_push(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]
    gh_url = f"https://x-access-token:{GH_TOKEN}@github.com/{repo_full_name}.git"
    gl_url = f"https://oauth2:{GL_TOKEN}@gitlab.com/{repo_name}.git"

    temp_dir = repo_name

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    print(f"Syncing {repo_full_name}...")
    subprocess.run(["git", "clone", "--mirror", gh_url, temp_dir], check=True)

    try:
        subprocess.run(["git", "-C", temp_dir, "push", "--mirror", gl_url], check=True)
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    try:
        public_repos = get_github_public_repos()
        print(f"Found {len(public_repos)} public repositories on GitHub.")

        for repo in public_repos:
            try:
                create_gitlab_repo(repo)
                mirror_push(repo)
            except Exception as e:
                print(f"Error syncing {repo}: {e}")
    except Exception as e:
        print(f"Process stopped: {e}")
