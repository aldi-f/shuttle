# Microsoft Store assets

These images use fictional AWS profiles, buckets, paths, and files. They are safe
to upload to the public Microsoft Store listing.

## Listing artwork

- `box-art-1x1.png` — required 1:1 Store box art
- `poster-art-2x3.png` — optional 2:3 Store poster art

## Desktop screenshots

Upload the screenshots in this order with the corresponding captions:

1. `screenshots/01-choose-profile.png` —
   **Sign in with your existing AWS IAM Identity Center profile**
2. `screenshots/02-browse-s3.png` —
   **Browse and search your accessible S3 buckets**
3. `screenshots/03-select-downloads.png` —
   **Select files and folders to download**
4. `screenshots/04-mirror-preview.png` —
   **Preview mirror changes before modifying local files**

The screenshots are 1366 × 768 PNG files. Do not replace their fictional data
with screenshots containing real account IDs, SSO URLs, bucket names, file
names, email addresses, or credentials.

## Regenerating assets

Install the development dependencies and run:

```shell
python scripts/generate_store_assets.py
```

The editable vector reference is `assets/branding/shuttle-icon.svg`. Keep its
geometry in sync with the generator when changing the icon. The generator
recreates the PNG, ICO, MSIX, Store-art, and screenshot files.
