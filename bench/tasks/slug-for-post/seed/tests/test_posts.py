from blog.posts import PostStore


def test_create_and_get() -> None:
    store = PostStore()
    post = store.create("Hello", "First post")
    assert store.get(post.id) == post
