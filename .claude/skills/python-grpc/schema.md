# Changing the Schema

### A removed field is reserved by number and by name, and a number is never reused

**Why:** a field's number is its wire identity and its name its JSON identity. An old client still
sending its remarks as field 6 to a server that reads 6 as `comment` gets a successful call with the
wrong meaning.

**Example:**
```protobuf
// WRONG — the deleted remark's number reused: old clients' remarks arrive as comments
message Flight {
  string comment = 6;
}

// CORRECT — the number and the name reserved, the new field numbered after them
message Flight {
  reserved 6;
  reserved "remark";
  string comment = 7;
}
```

### A breaking change is a new package, served beside the old one until the last client moves

**Why:** a field's type changed in place breaks every client compiled against the old schema at
once, and the deploy order of server and clients cannot fix it. A new package — `airapis.flights.v2`
— is a new service name; `v1` keeps answering until nobody calls it.

**Example:**
```protobuf
// WRONG — v1's fare changed from Money to an int64 of cents, under every existing client
package airapis.flights.v1;

message Flight {
  int64 fare_cents = 3;
}

// CORRECT — the new shape in v2, served beside v1
package airapis.flights.v2;

message Flight {
  int64 fare_cents = 3;
}
```

### `buf breaking` and `buf lint` run in CI against the main branch

**Why:** a reviewer misses a reused number; buf does not.
`buf breaking --against '.git#branch=main'` needs `main` fetched. The default category, `FILE`,
reported the deletion above even when reserved — right for a package whose generated modules other
code imports. `WIRE_JSON` accepted it only once number and name were both reserved — right for a
service whose clients generate their own code.

**Example:**
```bash
# WRONG — style is checked, and a reused field number merges unseen
buf lint

# CORRECT — the schema compared with main's, failing on a breaking change
git fetch origin main:main
buf lint
buf breaking --against '.git#branch=main'
```
