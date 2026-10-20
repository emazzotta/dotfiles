import pytest


@pytest.fixture
def article(load_module):
    return load_module("scrapelib.article")


def should_name_folders_without_unsafe_characters_and_cut_them_at_a_word(article):
    title = "Marseille: Proteste gehen in Krawalle über, und die Stadt bereitet sich auf weitere Unruhen vor"

    name = article.safe_filename(title)

    assert (
        name
        == "Marseille - Proteste gehen in Krawalle über, und die Stadt bereitet sich auf"
    )
    assert len(name) <= article.MAX_NAME_LENGTH


def should_number_files_per_folder_and_reuse_the_asset_of_a_repeated_url(article):
    namer = article.AssetNamer()

    first = namer.image("https://x.example/a.png")
    clip = namer.clip(
        article.ClipKind.VIDEO,
        "https://x.example/v.m3u8",
        "Clip: eins",
        article.Transfer.HLS,
    )
    second = namer.image("https://x.example/b")
    repeat = namer.image("https://x.example/a.png")

    assert [first.local_path.as_posix(), second.local_path.as_posix()] == [
        "images/01.png",
        "images/02.jpg",
    ]
    assert clip.local_path.as_posix() == "video/01 Clip - eins.mp4"
    assert repeat is first
