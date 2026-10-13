# Migrations

### The migration is a deploy step run once from the release's image, not part of the start command

**Why:** every replica that migrates at start runs it concurrently, and a failing migration becomes
a crash loop. The deploy runs it once before the rollout — `docker run --rm IMAGE` with the
migration command, or a Kubernetes `Job` from the same image and tag; an init container runs once
per pod and is not that step. The old replicas keep serving meanwhile, which is why the migration is
expand-first.
