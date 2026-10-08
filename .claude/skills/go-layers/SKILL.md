---
name: go-layers
description: >-
  Go layer boundaries: the domain importing the standard library and other domain packages only,
  frameworks and drivers entering through adapters, depguard rules listing the denied imports per
  set of files, and fixing a violation by moving code or inverting the dependency rather than
  allowlisting it. Use when adding a depguard rule, arguing about which layer code belongs to, or
  when a domain package imports a framework, a driver or a sibling implementation.
---

# Layers

**Dependency direction is enforced by a linter, not by review vigilance.** Go already refuses import
cycles; what it does not refuse is the domain importing the database driver, or one notifier
importing another.

- **`depguard` lists, per set of files, the imports that are denied** — the domain packages may not
  import `database/sql`, `net/http` or any driver; an implementation package may not import its
  siblings. Every allowed exception carries its reason in the configuration.

  ```yaml
  # WRONG — no files: the rule covers every file, so the adapter that must import the driver fails
  domain:
    deny:
      - pkg: database/sql
        desc: the domain reaches storage through an interface it declares

  # CORRECT — the rule names the domain's files; the adapter in orders/postgres is not one of them
  domain:
    files:
      - "**/internal/orders/*.go"
    deny:
      - pkg: database/sql
        desc: the domain reaches storage through an interface it declares
  ```

  Both sit under `linters.settings.depguard.rules` in golangci-lint v2's configuration.
- **`internal/` is the boundary Go enforces by itself**: nothing outside the parent directory can
  import it. Use the nesting — `orders/internal/pricing` is invisible even to `payments`.
- **The domain imports the standard library and other domain packages only.** Frameworks, drivers
  and clients enter through adapters that implement interfaces the domain declares.
- **A boundary violation is fixed by moving code or inverting the dependency** — an interface plus
  an adapter — never by adding the import to an allowlist without a reason on the line.

```go
// WRONG — the domain imports the driver: no test of Place runs without a database
package orders

import "database/sql"

type Service struct {
	db *sql.DB
}

func (s *Service) Place(ctx context.Context, order Order) error {
	if _, err := s.db.ExecContext(ctx, insertOrder, order.ID, order.TotalCents); err != nil {
		return fmt.Errorf("place order %s: %w", order.ID, err)
	}
	return nil
}

// CORRECT — the domain declares what it needs; package orders/postgres implements it
package orders

type Saver interface {
	Save(ctx context.Context, order Order) error
}

type Service struct {
	saver Saver
}

func (s *Service) Place(ctx context.Context, order Order) error {
	if err := s.saver.Save(ctx, order); err != nil {
		return fmt.Errorf("place order %s: %w", order.ID, err)
	}
	return nil
}
```

How directories are named and nested is a project decision: it follows the domain, the team and
the deployment. A layout copied from a template is a layout nobody owns. What is fixed is which
way dependencies point, where construction happens, and that `main` stays thin.
