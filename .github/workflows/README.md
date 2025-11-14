# GitHub Actions Workflows

## Build and Push Docker Image

The `build-docker-image.yml` workflow automatically builds and publishes the Family Link Auth Docker image to GitHub Container Registry (GHCR).

### Triggers

The workflow runs on:
- **Push to main branch** - Builds and tags as `latest`
- **Git tags** starting with `v*` (e.g., `v1.2.3`) - Builds semantic versioned images
- **Published releases** - Builds and tags with version numbers
- **Manual trigger** - Via GitHub Actions UI

### What it does

1. **Multi-architecture build** - Builds for both `linux/amd64` and `linux/arm64`
2. **Automatic tagging** - Creates appropriate tags based on trigger type:
   - Latest tag for main branch
   - Semantic version tags (e.g., `1.2.3`, `1.2`, `1`) for releases
   - Branch names for feature branches
3. **Publishes to GHCR** - Pushes to `ghcr.io/noiwid/familylink-auth`
4. **Build caching** - Uses GitHub Actions cache for faster builds

### Usage

After the workflow runs, the image is available at:

```bash
# Pull latest version
docker pull ghcr.io/noiwid/familylink-auth:latest

# Pull specific version
docker pull ghcr.io/noiwid/familylink-auth:1.2.3
```

### Permissions

The workflow uses `GITHUB_TOKEN` which is automatically provided by GitHub Actions. No additional secrets are required.

### Making the image public

By default, GHCR images are private. To make it public:

1. Go to https://github.com/users/noiwid/packages/container/familylink-auth/settings
2. Under "Danger Zone", click "Change visibility"
3. Select "Public"
4. Confirm the change

Alternatively, you can make it public via GitHub CLI:

```bash
gh api --method PATCH /user/packages/container/familylink-auth \
  -f visibility=public
```

### Manual trigger

To manually trigger the workflow:

1. Go to https://github.com/noiwid/HAFamilyLink/actions/workflows/build-docker-image.yml
2. Click "Run workflow"
3. Select the branch to build from
4. Click "Run workflow"

### Troubleshooting

**Build fails with "buildx" error:**
- This is usually a temporary GitHub Actions issue
- Re-run the workflow

**Image not appearing in GHCR:**
- Check workflow logs for errors
- Ensure `GITHUB_TOKEN` has `packages: write` permission (it should by default)
- Check if the repository settings allow package publishing

**Multi-arch build fails:**
- QEMU setup might have failed
- Check the "Set up QEMU" step in workflow logs
- Re-run the workflow
