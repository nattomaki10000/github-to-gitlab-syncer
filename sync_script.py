def fix_gitlab_pages_settings(project_id):
    """
    【最終決定版】
    1. 段階的に設定を適用。まずプロジェクト全体のベース可視性をpublicにする。
    2. バックエンドがPagesを認識するまで待機（ポーリング）。
    3. プロジェクトAPIでPagesのアクセスレベルを個別に「public」へと強制適用する。
    4. 最後にPages専用APIを叩き、一意のドメイン（Unique Domain）を無効化する。
    """
    p_chars = ['h', 't', 't', 'p', 's', ':', '/', '/', 'g', 'i', 't', 'l', 'a', 'b', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'v', '4', '/', 'p', 'r', 'o', 'j', 'e', 'c', 't', 's', '/']
    base_url = "".join(p_chars)
    headers = {"PRIVATE-TOKEN": GL_TOKEN}

    project_url = base_url + f"{project_id}"
    pages_url = base_url + f"{project_id}/pages"

    # ステップ1: 大元のプロジェクト自体の可視性を確実に public に独立して設定
    print(f"-> 1. Ensuring project base visibility is set to public for project {project_id}")
    requests.put(project_url, headers=headers, json={"visibility": "public"}, timeout=30)

    # ステップ2: GitLab PagesのバックエンドがPushを検知して初期化されるのを待つ
    print(f"-> 2. Waiting for GitLab Pages backend to initialize...")
    initialized = False
    for _ in range(12):  # 5秒おきに最大60秒待機
        check_resp = requests.get(pages_url, headers=headers, timeout=30)
        if check_resp.status_code == 200:
            initialized = True
            break
        time.sleep(5)

    if not initialized:
        print("-> Warning: Pages backend initialization timed out, but proceeding with configuration update.")

    # ステップ3: 【重要】ベースが安定した状態で、Pagesのアクセス制限を単独で全員（public）に変更
    print(f"-> 3. Forcing Pages Access Level to Everyone (public)...")
    access_applied = False
    for _ in range(3): # 稀に即時反映されないため最大3回トライ
        acc_resp = requests.put(project_url, headers=headers, json={"pages_access_level": "public"}, timeout=30)
        if acc_resp.status_code in (200, 204):
            # 設定が実際に書き換わったかレスポンスデータを確認
            if acc_resp.json().get("pages_access_level") == "public":
                access_applied = True
                break
        time.sleep(2)
    
    if access_applied:
        print(f"-> [SUCCESS] Pages access level verified as: Everyone (public)")
    else:
        print(f"-> [WARNING] Pages access level update responded OK, but verified failed. Please check UI.")

    # ステップ4: 最後に、一意のドメイン（Unique Domain）を確実に無効化する
    print(f"-> 4. Disabling Unique Domain...")
    pages_payload = {"pages_unique_domain_enabled": "false"}
    resp = requests.patch(pages_url, headers=headers, data=pages_payload, timeout=30)
    if resp.status_code in (200, 204):
        print(f"-> [SUCCESS] Disabled unique domain for project {project_id}")
    else:
        print(f"-> [FAILED] Could not disable unique domain ({resp.status_code}): {resp.text}")
