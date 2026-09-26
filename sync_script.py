import os
import shutil
import subprocess
import tempfile
import requests

GITHUB_USER = "nattomaki10000"

GITHUB_API_URL = "https://api.github.com"
GITLAB_API_URL = "https://gitlab.com/api/v4"

GITHUB_PAGES_DOMAIN = "nattomaki10000.github.io"
GITLAB_PAGES_DOMAIN = "nattomaki10000.gitlab.io"


def run_command(command, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(command)}")

    return result.stdout.strip()


def get_github_repos(github_token):
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    repos = []
    page = 1

    while True:
        url = (
            f"{GITHUB_API_URL}/users/{GITHUB_USER}/repos"
            f"?type=public&per_page=100&page={page}"
        )

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        if not data:
            break

        for repo in data:
            if not repo["fork"]:
                repos.append(repo)

        page += 1

    return repos


def get_gitlab_namespace_id(gitlab_token):
    headers = {
        "PRIVATE-TOKEN": gitlab_token
    }

    response = requests.get(
        f"{GITLAB_API_URL}/namespaces",
        headers=headers,
        params={"search": GITHUB_USER}
    )
    response.raise_for_status()

    for namespace in response.json():
        if namespace["name"] == GITHUB_USER:
            return namespace["id"]

    raise RuntimeError(
        f"GitLab namespace not found: {GITHUB_USER}"
    )


def create_gitlab_repo(repo_full_name, gitlab_token):
    original_repo_name = repo_full_name.split("/")[-1]

    if original_repo_name == GITHUB_PAGES_DOMAIN:
        repo_name = GITLAB_PAGES_DOMAIN
    else:
        repo_name = original_repo_name

    headers = {
        "PRIVATE-TOKEN": gitlab_token
    }

    response = requests.get(
        f"{GITLAB_API_URL}/projects",
        headers=headers,
        params={"search": repo_name}
    )
    response.raise_for_status()

    for project in response.json():
        if (
            project["path"] == repo_name
            and project["namespace"]["name"] == GITHUB_USER
        ):
            print(
                f"-> GitLab repository already exists: {repo_name}"
            )
            return project

    data = {
        "name": repo_name,
        "path": repo_name,
        "namespace_id": get_gitlab_namespace_id(gitlab_token),
        "visibility": "public"
    }

    response = requests.post(
        f"{GITLAB_API_URL}/projects",
        headers=headers,
        data=data
    )
    response.raise_for_status()

    project = response.json()

    print(f"-> Created GitLab repository: {repo_name}")

    return project


def replace_github_pages_domain(temp_dir):
    old_domain = GITHUB_PAGES_DOMAIN
    new_domain = GITLAB_PAGES_DOMAIN

    old_bytes = old_domain.encode("utf-8")
    new_bytes = new_domain.encode("utf-8")

    replaced_files = 0
    replaced_count = 0

    print(
        f"-> Replacing {old_domain} with {new_domain}..."
    )

    for root, dirs, files in os.walk(temp_dir):
        if ".git" in dirs:
            dirs.remove(".git")

        for filename in files:
            file_path = os.path.join(root, filename)

            try:
                with open(file_path, "rb") as f:
                    data = f.read()

                if b"\x00" in data:
                    continue

                if old_bytes not in data:
                    continue

                count = data.count(old_bytes)
                new_data = data.replace(
                    old_bytes,
                    new_bytes
                )

                with open(file_path, "wb") as f:
                    f.write(new_data)

                replaced_files += 1
                replaced_count += count

                print(
                    f"   -> {os.path.relpath(file_path, temp_dir)} "
                    f"({count} replacement(s))"
                )

            except (OSError, PermissionError) as e:
                print(
                    f"   -> Skipped: {file_path}: {e}"
                )

    print(
        f"-> Replaced {replaced_count} occurrence(s) "
        f"in {replaced_files} file(s)"
    )


def create_gitlab_ci(temp_dir):
    ci_file_path = os.path.join(
        temp_dir,
        ".gitlab-ci.yml"
    )

    gitlab_ci_content = """image: alpine:latest

pages:
  stage: deploy
  script:
    - mkdir -p .public_tmp
    - cp -r * .public_tmp/ 2>/dev/null || true
    - cp -r .[^.]* .public_tmp/ 2>/dev/null || true
    - rm -rf .public_tmp/.git .public_tmp/.github .public_tmp/public
    - mv .public_tmp public
  artifacts:
    paths:
      - public
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_COMMIT_BRANCH == "master"
"""

    with open(
        ci_file_path,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(gitlab_ci_content)

    print(
        "-> Added .gitlab-ci.yml for GitLab Pages"
    )


def mirror_push(repo, gitlab_token):
    original_repo_name = repo["name"]

    if original_repo_name == GITHUB_PAGES_DOMAIN:
        repo_name = GITLAB_PAGES_DOMAIN
    else:
        repo_name = original_repo_name

    github_clone_url = repo["clone_url"]

    gitlab_clone_url = (
        f"https://oauth2:{gitlab_token}"
        f"@gitlab.com/{GITHUB_USER}/{repo_name}.git"
    )

    temp_dir = tempfile.mkdtemp(
        prefix="github_to_gitlab_"
    )

    try:
        print(f"\n=== {original_repo_name} ===")
        print("-> Cloning GitHub repository...")

        run_command(
            [
                "git",
                "clone",
                github_clone_url,
                temp_dir
            ]
        )

        replace_github_pages_domain(temp_dir)

        static_yml = os.path.join(
            temp_dir,
            ".github",
            "workflows",
            "static.yml"
        )

        is_pages_repo = (
            os.path.exists(static_yml)
            or original_repo_name == GITHUB_PAGES_DOMAIN
        )

        if is_pages_repo:
            ci_file_path = os.path.join(
                temp_dir,
                ".gitlab-ci.yml"
            )

            if not os.path.exists(ci_file_path):
                create_gitlab_ci(temp_dir)

        run_command(
            [
                "git",
                "config",
                "user.name",
                "GitHub to GitLab Syncer"
            ],
            cwd=temp_dir
        )

        run_command(
            [
                "git",
                "config",
                "user.email",
                "syncer@nattomaki10000.github.io"
            ],
            cwd=temp_dir
        )

        status = run_command(
            [
                "git",
                "status",
                "--porcelain"
            ],
            cwd=temp_dir
        )

        if status:
            run_command(
                [
                    "git",
                    "add",
                    "-A"
                ],
                cwd=temp_dir
            )

            run_command(
                [
                    "git",
                    "commit",
                    "-m",
                    "Sync GitHub repository to GitLab"
                ],
                cwd=temp_dir
            )

        print("-> Adding GitLab remote...")

        run_command(
            [
                "git",
                "remote",
                "add",
                "gitlab",
                gitlab_clone_url
            ],
            cwd=temp_dir
        )

        print("-> Pushing branches...")

        run_command(
            [
                "git",
                "push",
                "gitlab",
                "--all",
                "--force"
            ],
            cwd=temp_dir
        )

        print("-> Pushing tags...")

        run_command(
            [
                "git",
                "push",
                "gitlab",
                "--tags",
                "--force"
            ],
            cwd=temp_dir
        )

        return is_pages_repo

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


def fix_gitlab_pages_settings(
    project_id,
    gitlab_token
):
    headers = {
        "PRIVATE-TOKEN": gitlab_token
    }

    print("-> Configuring GitLab Pages...")

    data = {
        "pages_access_level": "enabled"
    }

    response = requests.put(
        f"{GITLAB_API_URL}/projects/{project_id}",
        headers=headers,
        data=data
    )

    if response.ok:
        print("-> GitLab Pages enabled")
    else:
        print(
            f"-> Failed to enable GitLab Pages: "
            f"{response.status_code} {response.text}"
        )


def main():
    github_token = os.environ.get("GITHUB_TOKEN")
    gitlab_token = os.environ.get("GITLAB_TOKEN")

    if not github_token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set."
        )

    if not gitlab_token:
        raise RuntimeError(
            "GITLAB_TOKEN is not set."
        )

    print(
        "-> Getting GitHub repositories..."
    )

    repos = get_github_repos(
        github_token
    )

    print(
        f"-> Found {len(repos)} repositories"
    )

    for repo in repos:
        try:
            gl_project = create_gitlab_repo(
                repo["full_name"],
                gitlab_token
            )

            is_pages_repo = mirror_push(
                repo,
                gitlab_token
            )

            if is_pages_repo:
                fix_gitlab_pages_settings(
                    gl_project["id"],
                    gitlab_token
                )

        except Exception as e:
            print(
                f"-> ERROR: {repo['name']}: {e}"
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
