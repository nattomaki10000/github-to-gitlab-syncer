import os
import subprocess
import requests

GH_TOKEN = os.environ.get('GH_TOKEN', '')
GL_TOKEN = os.environ.get('GL_TOKEN', '')
GH_USER = 'nattomaki10000'
GL_USER = 'nattomaki10000'

def get_github_public_repos():
    # トークン不要で100%確実に公開リポジトリ一覧を取得できるURL
    url = f"https://github.com{GH_USER}/repos?per_page=100"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("GitHub API Failed")
    return [repo['name'] for repo in response.json() if not repo['fork'] and not repo['private']]

def create_gitlab_repo(repo_name):
    url = "https://gitlab.com"
    headers = {"PRIVATE-TOKEN": GL_TOKEN}
    check_url = f"https://gitlab.com{GL_USER}/projects?search={repo_name}"
    res = requests.get(check_url, headers=headers)
    res_json = res.json() if res.status_code == 200 else []
    if any(p['name'] == repo_name for p in res_json):
        return
    data = {"name": repo_name, "visibility": "public", "description": "Synced from GitHub automatically."}
    requests.post(url, headers=headers, data=data)
    print(f"Created GitLab repository: {repo_name}")

def mirror_push(repo_name):
    print(f"Syncing {repo_name}...")
    gh_url = f"https://x-access-token:{GH_TOKEN}@://github.com{GH_USER}/{repo_name}.git"
    gl_url = f"https://oauth2:{GL_TOKEN}@://gitlab.com{GL_USER}/{repo_name}.git"
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
