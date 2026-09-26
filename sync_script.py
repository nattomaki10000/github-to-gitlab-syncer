import os
import subprocess
import requests

GH_TOKEN = os.environ.get('GH_TOKEN', '')
GL_TOKEN = os.environ.get('GL_TOKEN', '')

def get_github_public_repos():
    url = "https://api.github.com/user/repos"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"GitHub API Failed: {response.status_code}")
    return [repo['name'] for repo in response.json() if not repo['fork'] and not repo['private']]

def create_gitlab_repo(repo_name):
    url = "https://gitlab.com/api/v4/projects"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}
    
    # 既存プロジェクトのチェック
    check_url = f"{url}?search={repo_name}"
    res = requests.get(check_url, headers=headers)
    res_json = res.json() if res.status_code == 200 else []
    
    if any(p['name'] == repo_name for p in res_json):
        return
        
    data = {"name": repo_name, "visibility": "public", "description": "Synced from GitHub automatically."}
    requests.post(url, headers=headers, json=data)
    print(f"Created GitLab repository: {repo_name}")

def mirror_push(repo_name):
    print(f"Syncing {repo_name}...")
    
    gh_url = f"https://x-access-token:{GH_TOKEN}@github.com/{repo_name}.git"
    gl_url = f"https://oauth2:{GL_TOKEN}@gitlab.com/{repo_name}.git"
    
    subprocess.run(["git", "clone", "--mirror", gh_url, repo_name], check=True)
    os.chdir(repo_name)
    subprocess.run(["git", "push", "--mirror", gl_url], check=True)
    os.chdir("..")
    subprocess.run(["rm", "-rf", repo_name], check=True)

if __name__ == "__main__":
    try:
        public_repos = get_github_public_repos()
        print(f"Found {len(public_repos)} public repositories on GitHub.")
        for repo in public_repos:
            if repo == "github-to-gitlab-syncer":
                continue
            try:
                create_gitlab_repo(repo)
                mirror_push(repo)
            except Exception as e:
                print(f"Error syncing {repo}: {e}")
    except Exception as e:
        print(f"Process stopped: {e}")
