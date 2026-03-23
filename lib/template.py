"""Template directory management – ensures _template/ has all required repos."""

import logging
import os
import subprocess
from pathlib import Path

from lib.config import CLONE_REPOS, NPM_INSTALL_DIRS, REPO_PATH

logger = logging.getLogger("asana_poller")

TEMPLATE_DIR = Path(REPO_PATH) / "_template"


def ensure_template() -> None:
    """Clone missing repos and npm install into _template/."""
    if not CLONE_REPOS:
        logger.debug("CLONE_REPOS is empty, skipping template setup.")
        return

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    for repo_url in CLONE_REPOS:
        repo_name = os.path.basename(repo_url).removesuffix(".git")
        repo_dir = TEMPLATE_DIR / repo_name
        if not repo_dir.exists():
            logger.info("Template: cloning %s ...", repo_name)
            result = subprocess.run(
                ["git", "clone", repo_url],
                cwd=str(TEMPLATE_DIR),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("Template: clone failed for %s: %s", repo_name, result.stderr.strip())

    for dir_name in NPM_INSTALL_DIRS:
        package_json = TEMPLATE_DIR / dir_name / "package.json"
        if package_json.exists():
            logger.info("Template: npm install in %s ...", dir_name)
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(TEMPLATE_DIR / dir_name),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("Template: npm install failed for %s: %s", dir_name, result.stderr.strip())

    logger.info("Template setup complete: %s", TEMPLATE_DIR)
