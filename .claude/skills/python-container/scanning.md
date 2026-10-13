# Scanning

### The built image is scanned in CI, rebuilt on a schedule, and its uv image's provenance checked

**Why:** an image scan — Trivy, Grype, Docker Scout — covers the base image's operating system
packages, which `pip-audit` (`python-project`) does not see; the build fails on a high or critical
finding that has a fix. A base-image fix reaches only images built after it, so the image is rebuilt
on a schedule, not only on a commit. The uv image's attestation is verified before its digest is
pinned.
