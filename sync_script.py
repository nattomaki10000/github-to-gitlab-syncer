import os
import shutil
import subprocess
import requests
import time

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GL_TOKEN = os.environ.get("GL_TOKEN", "")
GH_USER = "nattomaki10000"
GL_NAMESPACE = "nattomaki10000"

def get_github_public_repos():
    # システムによるURLの自動結合を防ぐため、1文字ずつの配列を合体
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
    """
    【段階的適用版】
    1. プロジェクト自体の可視性をpublicにする
    2. バックエンドのPages初期化を待つ
    3. Pagesのアクセスレベルを単独でpublic（全員）にする
    4. 一意のドメイン（Unique Domain）を無効化する
    """
    p_chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'v', '4', '/', 'p', 'r', 'o', 'j', 'e', 'c', 't', 's', '/']
    base_url = "".join(p_chars)
    headers = {"PRIVATE-TOKEN": GL_TOKEN}

    project_url = base_url + f"{project_id}"
    pages_url = base_url + f"{project_id}/pages"

    print(f"-> [1/4] Ensuring project base visibility is public...")
    requests.put(project_url, headers=headers, json={"visibility": "public"}, timeout=30)

    print(f"-> [2/4] Waiting for GitLab Pages backend to initialize...")
    initialized = False
    for _ in range(12):  
        check_resp = requests.get(pages_url, headers=headers, timeout=30)
        if check_resp.status_code == 200:
            initialized = True
            break
        time.sleep(5)

    if not initialized:
        print("-> Warning: Pages backend initialization timed out, but proceeding.")

    print(f"-> [3/4] Forcing Pages Access Level to Everyone (public)...")
    access_applied = False
    for _ in range(3):
        acc_resp = requests.put(project_url, headers=headers, json={"pages_access_level": "public"}, timeout=30)
        if acc_resp.status_code in (200, 204):
            if acc_resp.json().get("pages_access_level") == "public":
                access_applied = True
                break
        time.sleep(2)
    
    if access_applied:
        print(f"-> [SUCCESS] Pages access level verified as: Everyone (public)")
    else:
        print(f"-> [WARNING] Pages access level update sent, but verification failed.")

    print(f"-> [4/4] Disabling Unique Domain...")
    pages_payload = {"pages_unique_domain_enabled": "false"}
    resp = requests.patch(pages_url, headers=headers, data=pages_payload, timeout=30)
    if resp.status_code in (200, 204):
        print(f"-> [SUCCESS] Disabled unique domain for project {project_id}")
    else:
        print(f"-> [FAILED] Could not disable unique domain ({resp.status_code}): {resp.text}")

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
                return p["id"]

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
    return new_project["id"]

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
    # デバッグ用に、特定の同期したいリポジトリを配列に直接指定することも可能です
    # 例: public_repos = ["nattomaki10000/blog"]
    public_repos = get_github_public_repos()
    print(f"Found {len(public_repos)} repos")

    for repo in public_repos:
        try:
            print(f"\n--- Starting sync for: {repo} ---")
            # 競合回避のための特定スクリプト名によるスキップ条件を削除しました
            gl_project_id = create_gitlab_repo(repo)
            mirror_push(repo)
            fix_gitlab_pages_settings(gl_project_id)
            print(f"Synced successfully: {repo}")
        except Exception as e:
            print(f"Error syncing {repo}: {e}")
