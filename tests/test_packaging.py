from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "windows" / "msix" / "AppxManifest.xml.in"
ASSETS = MANIFEST.parent / "Assets"
FOUNDATION = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP = "http://schemas.microsoft.com/appx/manifest/uap/windows10"


def test_msix_manifest_has_store_identity_and_language() -> None:
    root = ElementTree.parse(MANIFEST).getroot()

    identity = root.find(f"{{{FOUNDATION}}}Identity")
    publisher = root.find(f"{{{FOUNDATION}}}Properties/{{{FOUNDATION}}}PublisherDisplayName")
    resource = root.find(f"{{{FOUNDATION}}}Resources/{{{FOUNDATION}}}Resource")

    assert identity is not None
    assert identity.attrib["Name"] == "aldi-f.Shuttle"
    assert identity.attrib["Publisher"] == "CN=E5E5535B-183B-4772-B7F0-18BF7A66A90D"
    assert publisher is not None
    assert publisher.text == "aldi-f"
    assert resource is not None
    assert resource.attrib["Language"] == "en-us"


def test_msix_manifest_image_resources_exist() -> None:
    root = ElementTree.parse(MANIFEST).getroot()
    properties = root.find(f"{{{FOUNDATION}}}Properties")
    visual_elements = root.find(
        f"{{{FOUNDATION}}}Applications/"
        f"{{{FOUNDATION}}}Application/"
        f"{{{UAP}}}VisualElements"
    )
    default_tile = visual_elements.find(f"{{{UAP}}}DefaultTile")

    references = [properties.find(f"{{{FOUNDATION}}}Logo").text]
    references.extend(
        visual_elements.attrib[name]
        for name in ("Square150x150Logo", "Square44x44Logo")
    )
    references.extend(
        default_tile.attrib[name]
        for name in ("Wide310x150Logo", "Square310x310Logo")
    )

    for reference in references:
        relative = Path(reference.replace("\\", "/"))
        assert relative.parts[0] == "Assets"
        assert (MANIFEST.parent / relative).is_file()
