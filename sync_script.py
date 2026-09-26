import os
import shutil
import subprocess
import requests

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GL_TOKEN = os.environ.get("GL_TOKEN", "")
GH_USER = os.environ.get("GH_USER", "nattomaki10000")
GL_NAMESPACE = os.environ.get("GL_NAMESPACE", "nattomaki10000")

def get_github_public_repos():
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    repos = []
    page = 1
    while True:
        r = requests.get(
            url,
            headers=headers,
            params={"visibility": "public", "affiliation": "owner", "per_page": 100, "page": page},
            timeout=30
        )
        if r.status_code != 200:
            raise Exception(f"GitHub API failed: {r.status_code} {r.text}")

        items = r.json()
        if not items:
            break

        for repo in items:
            if repo["owner"]["login"] != GH_USER:
                continue
            if repo["private"] or repo["fork"]:
                continue
            if repo["name"].startswith("."):
                continue
            repos.append(repo["full_name"])

        page += 1

    return repos

def create_gitlab_repo(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]

    # GitLabAPIで namespace の ID を探す
    ns_url = "https://gitlab.com/api/v4/namespaces"
    ns_headers = {"PRIVATE-TOKEN": GL_TOKEN}
    ns_resp = requests.get(ns_url, headers=ns_headers, timeout=30)
    if ns_resp.status_code != 200:
        raise Exception(f"GitLab namespace lookup failed: {ns_resp.status_code} {ns_resp.text}")

    namespace = None
    for item in ns_resp.json():
        if item.get("path") == GL_NAMESPACE:
            namespace = item
            break

    if namespace is None:
        raise Exception(f"GitLab namespace '{GL_NAMESPACE}' not found")

    api_url = "https://gitlab.com/api/v4/projects"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}

    existing = requests.get(f"{api_url}?search={repo_name}", headers=headers, timeout=30)
    if existing.status_code == 200:
        for p in existing.json():
            if p["path"] == repo_name and p["namespace"]["full_path"] == GL_NAMESPACE:
                print(f"Already exists: {GL_NAMESPACE}/{repo_name}")
                return

    payload = {
        "name": repo_name,
        "path": repo_name,
        "namespace_id": namespace["id"],
        "visibility": "public",
        "description": f"Synced from GitHub: {repo_full_name}",
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
    if resp.status_code not in (200, 201, 202):
        raise Exception(f"GitLab project create failed: {resp.status_code} {resp.text}")

    print(f"Created GitLab repo: {GL_NAMESPACE}/{repo_name}")

def mirror_push(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]
    gh_url = f"https://x-access-token:{GH_TOKEN}@github.com/{repo_full_name}.git"
    gl_url = f"https://oauth2:{GL_TOKEN}@gitlab.com/{GL_NAMESPACE}/{repo_name}.git"

    temp_dir = repo_name
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    # 1. 判定とファイル操作を行うため、通常のクローンを実行
    subprocess.run(["git", "clone", gh_url, temp_dir], check=True)
    try:
        # --- ★ここから：static.ymlの存在判定とGitLab Pages設定 ---
        
        # GitHub Pagesの自動公開設定（static.yml）のパス
        static_yml_path = os.path.join(temp_dir, ".github", "workflows", "static.yml")
        ci_file_path = os.path.join(temp_dir, ".gitlab-ci.yml")
        
        # .github/workflows/static.yml が存在する場合のみ処理を実行
        if os.path.exists(static_yml_path):
            print(f"-> GitHub Pages detected (.github/workflows/static.yml found)")
            
            # すでにGitLab用の設定ファイルがない場合だけ、自動生成する
            if not os.path.exists(ci_file_path):
                gitlab_ci_content = """pages:
  stage: deploy
  script:
    - mkdir .public
    - cp -r * .public/ 2>/dev/null || true
    - rm -rf .public/.git .public/.github
    - mv .public public
  artifacts:
    paths:
      - public
  only:
    - main
    - master
"""
                with open(ci_file_path, "w", encoding="utf-8") as f:
                    f.write(gitlab_ci_content)
                
                # 生成した設定ファイルをGitのコミットに含める
                subprocess.run(["git", "-C", temp_dir, "config", "user.name", "GitHub Actions"], check=True)
                subprocess.run(["git", "-C", temp_dir, "config", "user.email", "actions@github.com"], check=True)
                subprocess.run(["git", "-C", temp_dir, "add", ".gitlab-ci.yml"], check=True)
                subprocess.run(["git", "-C", temp_dir, "commit", "-m", "chore: add .gitlab-ci.yml for GitLab Pages [skip ci]"], check=True)
                print("-> Added .gitlab-ci.yml for GitLab Pages")
        else:
            print(f"-> Regular repository (No static.yml found). Skipping GitLab Pages setup.")
            
        # --- ★ここまで ---

        # 2. GitLabへ強制ミラープッシュ（変更内容をすべて同期）
        subprocess.run(["git", "-C", temp_dir, "push", "--force", gl_url, "--all"], check=True)
        subprocess.run(["git", "-C", temp_dir, "push", "--force", gl_url, "--tags"], check=True)
        
    finally:
        # 一時フォルダの完全削除
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    public_repos = get_github_public_repos()
    print(f"Found {len(public_repos)} repos")

    for repo in public_repos:
        try:
            create_gitlab_repo(repo)
            mirror_push(repo)
            print(f"Synced: {repo}")
        except Exception as e:
            print(f"Error syncing {repo}: {e}")
