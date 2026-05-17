#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/update_homebrew_tap.sh [options]

Copy the release-generated Indexly formula into a local Homebrew tap repository,
then commit, tag, and optionally push the tap release tag.

Options:
  --tap-repo PATH  Path to the Homebrew tap repository root.
                   Default: /home/linuxbrew/.linuxbrew/Homebrew/Library/Taps/kimsgent/homebrew-indexly
  --dry-run        Update formula if needed, then skip commit, tag, and push.
  --push           Push the release tag to origin.
  --help           Show this help message.
USAGE
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

step() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

find_python() {
  if [[ -x "${PROJECT_ROOT}/.venv-codex/bin/python" ]]; then
    printf '%s\n' "${PROJECT_ROOT}/.venv-codex/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    fail "Required command not found: python, python3, or .venv-codex/bin/python"
  fi
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_TAP_REPO="/home/linuxbrew/.linuxbrew/Homebrew/Library/Taps/kimsgent/homebrew-indexly"

TAP_REPO="${DEFAULT_TAP_REPO}"
DRY_RUN=0
PUSH=0

while (($#)); do
  case "$1" in
    --tap-repo)
      (($# >= 2)) || fail "--tap-repo requires a path"
      TAP_REPO="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --push)
      PUSH=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

if ((DRY_RUN)) && ((PUSH)); then
  fail "--dry-run and --push cannot be used together"
fi

require_command git
PYTHON="$(find_python)"

SOURCE_FORMULA="${PROJECT_ROOT}/Formula/indexly.rb"
[[ -f "${SOURCE_FORMULA}" ]] || fail "Release formula not found: ${SOURCE_FORMULA}"

[[ -d "${TAP_REPO}" ]] || fail "Tap repository does not exist: ${TAP_REPO}"
TAP_REPO="$(cd -- "${TAP_REPO}" && pwd)"

git -C "${TAP_REPO}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || fail "Tap path is not inside a git repository: ${TAP_REPO}"
TAP_REPO="$(git -C "${TAP_REPO}" rev-parse --show-toplevel)"
TARGET_FORMULA="${TAP_REPO}/Formula/indexly.rb"

cd "${PROJECT_ROOT}"

step "Reading Indexly version"
VERSION="$("${PYTHON}" scripts/read_pyproject_version.py)"
[[ -n "${VERSION}" ]] || fail "Could not determine version from pyproject.toml"
VERSION_TAG="v${VERSION}"
printf 'Version: %s\n' "${VERSION_TAG}"

step "Checking release formula"
if grep -Fq "${VERSION_TAG}" "${SOURCE_FORMULA}"; then
  printf 'Formula references %s\n' "${VERSION_TAG}"
else
  fail "Formula does not reference ${VERSION_TAG}: ${SOURCE_FORMULA}"
fi

step "Syncing formula into tap repository"
mkdir -p "${TAP_REPO}/Formula"
if [[ -f "${TARGET_FORMULA}" ]] && cmp -s "${SOURCE_FORMULA}" "${TARGET_FORMULA}"; then
  printf 'Tap formula already matches %s\n' "${SOURCE_FORMULA}"
else
  cp "${SOURCE_FORMULA}" "${TARGET_FORMULA}"
  printf 'Formula copied to %s\n' "${TARGET_FORMULA}"
fi

step "Tap repository formula status"
STATUS_OUTPUT="$(git -C "${TAP_REPO}" status --short -- Formula/indexly.rb)"
if [[ -n "${STATUS_OUTPUT}" ]]; then
  printf '%s\n' "${STATUS_OUTPUT}"
else
  printf 'No formula changes detected.\n'
fi

if ((DRY_RUN)); then
  step "Dry run complete"
  printf 'Tap formula path: %s\n' "${TARGET_FORMULA}"
  printf 'No commit, tag, or push was performed.\n'
  exit 0
fi

if [[ -n "${STATUS_OUTPUT}" ]]; then
  step "Committing formula update in tap repository"
  git -C "${TAP_REPO}" add Formula/indexly.rb
  git -C "${TAP_REPO}" commit -m "brew: bump indexly to ${VERSION_TAG}"
else
  step "Skipping commit"
fi

if git -C "${TAP_REPO}" rev-parse -q --verify "refs/tags/${VERSION_TAG}" >/dev/null; then
  step "Tag already exists: ${VERSION_TAG}"
else
  step "Creating annotated tag: ${VERSION_TAG}"
  git -C "${TAP_REPO}" tag -a "${VERSION_TAG}" -m "Release ${VERSION_TAG}"
fi

if ((PUSH)); then
  step "Pushing tap release tag"
  git -C "${TAP_REPO}" push origin "${VERSION_TAG}"
else
  step "Push skipped"
  printf 'Use --push to push the tap release tag to origin.\n'
fi

step "Done"
