"""Hidden checks for slug-for-post: slugs come from the title and find the post."""

import inspect


def _lookup(store: object):
    methods = [
        getattr(store, name)
        for name, _ in inspect.getmembers(type(store), inspect.isfunction)
        if "slug" in name and not name.startswith("_")
    ]
    assert methods, "the store has no public method about slugs"
    return methods[0]


def test_gate_slug_from_title() -> None:
    from blog.posts import PostStore

    assert PostStore().create("Hello, World!", "body").slug == "hello-world"


def test_gate_slug_handles_accents() -> None:
    from blog.posts import PostStore

    assert PostStore().create("Café déjà vu", "body").slug == "cafe-deja-vu"


def test_gate_lookup_by_slug() -> None:
    from blog.posts import PostStore

    store = PostStore()
    post = store.create("Hello, World!", "body")
    assert _lookup(store)("hello-world") == post


def test_same_title_gets_its_own_slug() -> None:
    from blog.posts import PostStore

    store = PostStore()
    first, second = store.create("Hello", "a"), store.create("Hello", "b")
    assert first.slug != second.slug
