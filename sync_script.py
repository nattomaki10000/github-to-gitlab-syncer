import os
import shutil
import subprocess
import requests

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GL_TOKEN = os.environ.get("GL_TOKEN", "")
GH_USER = "nattomaki10000"
GL_NAMESPACE = "nattomaki10000"

def get_github_public_repos():
    chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'a', 'p', 'i', '.', 'g', 'i', 't', 'h', 'u', 'b', '.', 'c', 'o', 'm', '/', 'u', 's', 'e', 'r', 's', '/', 'n', 'a', 't', 't', 'o', 'm', 'a', 'k', 'i', '1', '0', '0', '0', '0', '/', 'r', 'e', 'p', 'o', 's']
    url = "".join(chars)

    repos = []
    page = 1
    while True:
        r = requests.get(
            url,
            params={"type": "owner", "per_page": 100, "page": page},
            timeout=30
        )
        if r.status_code != 200:
            raise Exception(f"GitHub API failed: {r.status_code} {r.text}")

        items = r.json()
        if not items:
            break

        for repo in items:
            if repo["private"] or repo["fork"]:
                continue
            if repo["name"].startswith("."):
                continue
            repos.append(repo["full_name"])

        page += 1

    return repos

def unprotect_gitlab_branch(project_id, branch_name="main"):
    p_chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'v', '4', '/', 'p', 'r', 'o', 'j', 'e', 'c', 't', 's', '/']
    base_url = "".join(p_chars)
    
    url_main = base_url + f"{project_id}/protected_branches/{branch_name}"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}
    requests.delete(url_main, headers=headers, timeout=30)
    
    url_master = base_url + f"{project_id}/protected_branches/master"
    requests.delete(url_master, headers=headers, timeout=30)

def fix_gitlab_pages_settings(project_id):
    """【新設】APIを叩いて一意のドメインを強制的に無効化し、綺麗URL（path-based）に変更する"""
    p_chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'v', '4', '/', 'p', 'r', 'o', 'j', 'e', 'c', 't', 's', '/']
    url = "".join(p_chars) + f"{project_id}/pages"
    
    headers = {"PRIVATE-TOKEN": GL_TOKEN}
    # is_unique_domain_enabled を False（オフ）にしてパッチを送信します
    payload = {"is_unique_domain_enabled": False}
    
    # 設定を強制的に更新（GitLab公式API）
    requests.patch(url, headers=headers, json=payload, timeout=30)
    print(f"-> GitLab Pages Settings: Disabled unique domain for project {project_id}")

def create_gitlab_repo(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]

    p_chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'v', '4', '/']
    base_url = "".join(p_chars)
    
    ns_url = base_url + "namespaces"
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

    api_url = base_url + "projects"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}

    existing = requests.get(f"{api_url}?search={repo_name}", headers=headers, timeout=30)
    if existing.status_code == 200:
        for p in existing.json():
            if p["path"] == repo_name and p["namespace"]["full_path"] == GL_NAMESPACE:
                print(f"Already exists: {GL_NAMESPACE}/{repo_name}")
                unprotect_gitlab_branch(p["id"])
                # ★ 既存リポジトリの設定も、実行時に自動で一意のドメインをオフに書き換える
                fix_gitlab_pages_settings(p["id"])
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

    new_project = resp.json()
    print(f"Created GitLab repo: {GL_NAMESPACE}/{repo_name}")
    unprotect_gitlab_branch(new_project["id"])
    # ★ 新規に作られたリポジトリも、作成直後に自動で一意のドメインをオフにする
    fix_gitlab_pages_settings(new_project["id"])

def mirror_push(repo_full_name):
    repo_name = repo_full_name.split("/")[-1]
    
    protocol = "".join(['h', 't', 't', 'p', 's', ':', '/', '/'])
    gh_domain = "".join(['g', 'i', 't', 'h', 'u', 'b', '.', 'c', 'o', 'm', '/'])
    gl_domain = "".join(['g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/'])
    
    gh_url = protocol + "x-access-token:" + GH_TOKEN + "@" + gh_domain + repo_full_name + ".git"
    gl_url = protocol + "oauth2:" + GL_TOKEN + "@" + gl_domain + GL_NAMESPACE + "/" + repo_name + ".git"

    temp_dir = repo_name
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    subprocess.run(["git", "clone", gh_url, temp_dir], check=True)
    try:
        static_yml_path = os.path.join(temp_dir, ".github", "workflows", "static.yml")
        ci_file_path = os.path.join(temp_dir, ".gitlab-ci.yml")
        
        if os.path.exists(static_yml_path):
            print(f"-> GitHub Pages detected (.github/workflows/static.yml found)")
            if not os.path.exists(ci_file_path):
                gitlab_ci_content = """image: alpine:latest

pages:
  stage: deploy
  script:
    - mkdir -p .public_tmp
    - cp -r * .public_tmp/ 2>/dev/null || true
    - rm -rf .public_tmp/.git .public_tmp/.github
    - mv .public_tmp public
  artifacts:
    paths:
      - public
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_COMMIT_BRANCH == "master"
"""
                with open(ci_file_path, "w", encoding="utf-8") as f:
                    f.write(gitlab_ci_content)
                
                subprocess.run(["git", "-C", temp_dir, "config", "user.name", "GitHub Actions"], check=True)
                subprocess.run(["git", "-C", temp_dir, "config", "user.email", "actions@github.com"], check=True)
                subprocess.run(["git", "-C", temp_dir, "add", ".gitlab-ci.yml"], check=True)
                subprocess.run(["git", "-C", temp_dir, "commit", "-m", "chore: add .gitlab-ci.yml for GitLab Pages"], check=True)
                print("-> Added .gitlab-ci.yml for GitLab Pages")
        else:
            print(f"-> Regular repository (No static.yml found). Skipping GitLab Pages setup.")
            
        subprocess.run(["git", "-C", temp_dir, "push", "--force", gl_url, "--all"], check=True)
        subprocess.run(["git", "-C", temp_dir, "push", "--force", gl_url, "--tags"], check=True)
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    public_repos = get_github_public_repos()
    print(f"Found {len(public_repos)} repos")

    for repo in public_repos:
        try:
            if repo.split("/")[-1] == "github-to-gitlab-syncer":
                continue
            create_gitlab_repo(repo)
            mirror_push(repo)
            print(f"Synced: {repo}")
        except Exception as e:
            print(f"Error syncing {repo}: {e}")
