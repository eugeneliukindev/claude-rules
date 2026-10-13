# Processes and Workers

### One process per container, and the worker count is a number chosen beside the CPU limit

**Why:** a supervisor, a `&` or a cron beside the server hides the others' crashes from the
orchestrator; a second process is a second container from the same image with another command.
`os.cpu_count()`, `os.process_cpu_count()` and `nproc` report the node's CPUs, not the container's
limit — one CPU on a sixteen-core node reads 16, and gunicorn's (2 × cores) + 1 then means 33
processes sharing one CPU. Under an orchestrator the default is one worker per container, scaled by
replicas; otherwise `--workers` or `WEB_CONCURRENCY`. From 3.13 `PYTHON_CPU_COUNT` also overrides
what library defaults such as executor sizes see.

**Example:**
```dockerfile
# WRONG — workers derived from the node's CPU count, not the container's limit
CMD ["sh", "-c", "exec tracker-server --workers $(( $(nproc) * 2 + 1 ))"]

# CORRECT — one worker; the orchestrator scales by replicas
CMD ["tracker-server", "--workers", "1"]
```
