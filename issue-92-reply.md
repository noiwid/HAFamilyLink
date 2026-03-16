Hi @alrassia,

Docker images are still being built and published for every release. The CI/CD pipeline ran successfully for v1.2.0, v1.2.1, and v1.2.2.

The latest images are available on GHCR:

```bash
# Home Assistant addon:
docker pull ghcr.io/noiwid/familylink-auth:1.2.2

# Standalone Docker (HA Container/Core):
docker pull ghcr.io/noiwid/familylink-auth:1.2.2-standalone
```

Both `linux/amd64` and `linux/arm64` architectures are supported. You can also use the `:latest` or `:standalone` tags to always get the newest version.

Could you share what specifically made you think the Docker image wasn't being updated? That way we can improve the release notes if needed.
